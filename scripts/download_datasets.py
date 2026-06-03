"""Download benchmark datasets from Hugging Face and save as JSONL."""

from __future__ import annotations

import json
from pathlib import Path

import click
from datasets import load_dataset

SWE_BENCH_LITE = "princeton-nlp/SWE-bench_Lite"
REPO_BENCH = "kohjingyu/repobench"


@click.command()
@click.option(
    "--dataset",
    "-d",
    default="all",
    type=click.Choice(["swebench-lite", "repobench", "all"]),
    help="Which dataset to download",
)
@click.option(
    "--output-dir",
    "-o",
    default="data",
    type=click.Path(path_type=Path),
    help="Output directory (default: data/)",
)
@click.option(
    "--split",
    "-s",
    default=None,
    help="HuggingFace dataset split (default: auto-detect — dev for SWE-bench, train for RepoBench)",
)
@click.option(
    "--max-instances",
    type=int,
    default=0,
    show_default=True,
    help="Max instances to download (0 = all)",
)
def main(dataset: str, output_dir: Path, split: str | None, max_instances: int):
    targets = []
    defaults: dict[str, str] = {
        "swebench-lite": "dev",
        "repobench": "train",
    }
    if dataset in ("swebench-lite", "all"):
        targets.append(("swebench-lite", SWE_BENCH_LITE))
    if dataset in ("repobench", "all"):
        targets.append(("repobench", REPO_BENCH))

    for ds_name, hf_id in targets:
        use_split = split or defaults.get(ds_name, "train")
        ds_output = output_dir / ds_name
        ds_output.mkdir(parents=True, exist_ok=True)

        click.echo(f"Downloading {hf_id} (split={use_split}) ...")
        ds = load_dataset(hf_id, split=use_split)

        if max_instances and max_instances > 0:
            ds = ds.select(range(min(max_instances, len(ds))))

        out_file = ds_output / f"{ds_name}.jsonl"
        records = []
        for row in ds:
            record = {}
            for field in (
                "instance_id",
                "repo",
                "problem_statement",
                "base_commit",
                "test_patch",
            ):
                value = row.get(field, "")
                if value is None:
                    value = ""
                record[field] = value
            records.append(record)

        out_file.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
        )
        click.echo(f"  -> {len(records)} instances saved to {out_file}")


if __name__ == "__main__":
    main()
