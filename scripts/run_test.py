"""Test suite entry point — orchestrates dataset loading, harness execution, and metrics collection."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import click

from scripts.config import load_config
from scripts.dataset.base import TaskInstance
from scripts.dataset.repobench import RepoBenchLoader
from scripts.dataset.swebench_lite import SWEBenchLiteLoader
from scripts.harness.opencode import OpenCodeAdapter
from scripts.harness.pi import PiAdapter
from scripts.metrics import SuiteResult, TaskMetrics

DATASET_LOADERS = {
    "swebench-lite": SWEBenchLiteLoader,
    "repobench": RepoBenchLoader,
}

HARNESS_ADAPTERS = {
    "opencode": OpenCodeAdapter,
    "pi": PiAdapter,
}


def _get_harness_adapters(harness_arg: str, config: dict) -> list:
    """Resolve harness argument to list of adapter instances."""
    if harness_arg == "all":
        names = [
            k for k, v in config.get("harness", {}).items() if v.get("enabled", True)
        ]
    else:
        names = [h.strip() for h in harness_arg.split(",")]

    adapters = []
    for name in names:
        cls = HARNESS_ADAPTERS.get(name)
        if cls is None:
            click.echo(f"Unknown harness: {name}", err=True)
            continue
        adapters.append(cls(config))
    return adapters


def _run_task(task: TaskInstance, adapter, config: dict) -> TaskMetrics:
    """Execute single task with single harness in isolated temp dir."""
    with tempfile.TemporaryDirectory(prefix=f"ht_{task.instance_id}_") as tmp:
        work_dir = Path(tmp)
        repo_path = work_dir / "repo"
        repo_path.mkdir()

        task.dataset = task.metadata.get("dataset", "") if task.metadata else ""
        return adapter.run(
            instance_id=task.instance_id,
            prompt=task.prompt,
            repo_path=repo_path,
            work_dir=work_dir,
        )


@click.command()
@click.option("--dataset", default="swebench-lite", help="Dataset name")
@click.option("--harness", default="all", help="Harness name or comma-separated list")
@click.option("--max-workers", default=4, type=int, help="Parallel workers")
@click.option("--timeout", default=3600, type=int, help="Total timeout in seconds")
@click.option("--data-dir", default=None, help="Override dataset data directory")
@click.option("--output-dir", default=None, help="Override results output directory")
def main(
    dataset: str,
    harness: str,
    max_workers: int,
    timeout: int,
    data_dir: str | None,
    output_dir: str | None,
):
    config = load_config()

    output_cfg = config.get("output", {})
    results_dir = Path(output_dir or output_cfg.get("results_dir", "results"))
    results_dir.mkdir(parents=True, exist_ok=True)

    ds_config = config.get("datasets", {}).get(dataset, {})
    ds_path = data_dir or ds_config.get("path", f"data/{dataset}")

    loader_cls = DATASET_LOADERS.get(dataset)
    if loader_cls is None:
        click.echo(
            f"Unknown dataset: {dataset}. Available: {list(DATASET_LOADERS)}", err=True
        )
        sys.exit(1)

    loader = loader_cls(ds_config)
    instances = loader.load(ds_path)

    if not instances:
        click.echo(f"No instances found for dataset '{dataset}' at {ds_path}", err=True)
        click.echo(
            "Add .json/.jsonl files to the data directory or use --data-dir to override."
        )
        sys.exit(1)

    click.echo(f"Loaded {len(instances)} instances from {dataset}")

    adapters = _get_harness_adapters(harness, config)
    if not adapters:
        click.echo(f"No harness adapters matched '{harness}'", err=True)
        sys.exit(1)

    click.echo(f"Harnesses: {', '.join(a.name for a in adapters)}")

    suite_results: list[SuiteResult] = []
    start_ts = time.time()

    for adapter in adapters:
        click.echo(f"\n--- Running {adapter.name} on {dataset} ---")

        tasks_metrics: list[TaskMetrics] = []
        total = len(instances)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_run_task, inst, adapter, config): inst
                for inst in instances
            }

            completed = 0
            for future in as_completed(futures, timeout=timeout):
                inst = futures[future]
                try:
                    m = future.result()
                    m.dataset = dataset
                    tasks_metrics.append(m)
                    completed += 1
                    status = "PASS" if m.passed else "FAIL"
                    click.echo(
                        f"  [{completed}/{total}] {inst.instance_id} "
                        f"-> {status} "
                        f"(tokens={m.token_count}, api_calls={m.api_calls}, "
                        f"time={m.execution_time_s:.1f}s)"
                    )
                except Exception as exc:
                    click.echo(
                        f"  [{completed}/{total}] {inst.instance_id} -> ERROR: {exc}"
                    )

        result = SuiteResult(
            harness=adapter.name,
            dataset=dataset,
            total=total,
            tasks=tasks_metrics,
        )
        for m in tasks_metrics:
            if m.passed:
                result.passed += 1
            if m.resolved:
                result.resolved += 1
            if m.error:
                result.errors += 1
            if not m.build_passed and not m.error:
                result.build_errors += 1
            result.total_tokens += m.token_count
            result.total_api_calls += m.api_calls

        result.total_time_s = time.time() - start_ts
        suite_results.append(result)

        s = result.summary()
        click.echo(f"\n  {adapter.name} summary:")
        for k in [
            "total",
            "passed",
            "resolved",
            "errors",
            "build_errors",
            "pass@1",
            "resolve_rate",
            "build_rate",
            "total_tokens",
            "total_api_calls",
            "total_time_s",
            "avg_tokens_per_task",
            "avg_api_calls_per_task",
            "avg_time_per_task",
        ]:
            click.echo(f"    {k}: {s[k]}")

    # Write results
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    output_file = results_dir / f"results_{dataset}_{ts}.json"
    output_data = {
        "run_info": {
            "dataset": dataset,
            "harness": harness,
            "timestamp": ts,
            "config": {k: v for k, v in config.items() if k != "llm"},
        },
        "results": [r.summary() for r in suite_results],
        "tasks": [t.to_dict() for r in suite_results for t in r.tasks],
    }
    output_file.write_text(json.dumps(output_data, indent=2))
    click.echo(f"\nResults written to {output_file}")


if __name__ == "__main__":
    main()
