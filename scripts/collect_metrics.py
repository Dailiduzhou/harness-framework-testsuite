"""Metrics collection and reporting — reads result JSON files and prints summaries."""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table


@click.command()
@click.option("--summary", is_flag=True, help="Print summary of latest results")
@click.option(
    "--history", is_flag=True, help="Print full history from results directory"
)
@click.option("--results-dir", default="results", help="Path to results directory")
@click.option(
    "--file", "result_file", default=None, help="Specific result file to analyze"
)
def main(summary: bool, history: bool, results_dir: str, result_file: str | None):
    console = Console()

    if result_file:
        _print_result(console, Path(result_file))
        return

    results_path = Path(results_dir)
    if not results_path.exists():
        console.print("[red]No results directory found.[/red] Run tests first.")
        return

    json_files = sorted(
        results_path.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )

    if not json_files:
        console.print("[yellow]No result files found.[/yellow]")
        return

    if summary:
        _print_result(console, json_files[0])
    elif history:
        _print_history(console, json_files)
    else:
        _print_result(console, json_files[0])


def _print_result(console: Console, filepath: Path) -> None:
    data = json.loads(filepath.read_text())
    run_info = data.get("run_info", {})
    results = data.get("results", [])

    console.print(f"\n[bold]Results: {filepath.name}[/bold]")
    console.print(
        f"Dataset: {run_info.get('dataset')} | Harness: {run_info.get('harness')} | Time: {run_info.get('timestamp')}"
    )

    table = Table(title="Metrics Summary")
    table.add_column("Harness", style="cyan")
    table.add_column("Pass@1", justify="right")
    table.add_column("Resolve", justify="right")
    table.add_column("Build Rate", justify="right")
    table.add_column("Tokens", justify="right")
    table.add_column("API Calls", justify="right")
    table.add_column("Time (s)", justify="right")
    table.add_column("Avg Time", justify="right")

    for r in results:
        table.add_row(
            r.get("harness", ""),
            str(r.get("pass@1", "-")),
            str(r.get("resolve_rate", "-")),
            str(r.get("build_rate", "-")),
            str(r.get("total_tokens", 0)),
            str(r.get("total_api_calls", 0)),
            str(r.get("total_time_s", 0)),
            f"{r.get('avg_time_per_task', 0):.1f}",
        )

    console.print(table)

    # Per-task detail
    tasks = data.get("tasks", [])
    if tasks:
        detail = Table(title=f"Task Details ({len(tasks)} tasks)")
        detail.add_column("Instance", style="dim")
        detail.add_column("Harness")
        detail.add_column("Result", justify="center")
        detail.add_column("Tokens", justify="right")
        detail.add_column("Time (s)", justify="right")

        for t in tasks:
            status = "[green]PASS[/green]" if t.get("passed") else "[red]FAIL[/red]"
            detail.add_row(
                t.get("instance_id", "")[:40],
                t.get("harness", ""),
                status,
                str(t.get("token_count", 0)),
                str(t.get("execution_time_s", 0)),
            )

        console.print(detail)


def _print_history(console: Console, files: list[Path]) -> None:
    console.print(f"\n[bold]Metrics History ({len(files)} runs)[/bold]\n")

    table = Table(title="Run History")
    table.add_column("Timestamp", style="dim")
    table.add_column("Dataset")
    table.add_column("Harness")
    table.add_column("Pass@1", justify="right")
    table.add_column("Resolve", justify="right")
    table.add_column("Build", justify="right")
    table.add_column("Tokens", justify="right")
    table.add_column("Time (s)", justify="right")

    for fp in files:
        data = json.loads(fp.read_text())
        run = data.get("run_info", {})
        for r in data.get("results", []):
            table.add_row(
                run.get("timestamp", "")[:16],
                run.get("dataset", ""),
                r.get("harness", ""),
                str(r.get("pass@1", "-")),
                str(r.get("resolve_rate", "-")),
                str(r.get("build_rate", "-")),
                str(r.get("total_tokens", 0)),
                str(r.get("total_time_s", 0)),
            )

    console.print(table)


if __name__ == "__main__":
    main()
