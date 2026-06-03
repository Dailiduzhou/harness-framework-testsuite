#!/usr/bin/env python3
"""Academic paper analysis pipeline for harness benchmark results.

Produces:
  1. Aggregate metrics with 95% Wilson confidence intervals (terminal + LaTeX)
  2. Pairwise McNemar significance tests between harnesses
  3. Cost analysis ($ per task, based on model pricing)
  4. Publication-quality figures (bar, violin, scatter)
  5. LaTeX `.tex` tables ready for \\input{} in a paper

Usage:
  uv run python scripts/paper_analysis.py
  uv run python scripts/paper_analysis.py --pricing gpt-4o --output-dir paper_output
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import click
import numpy as np
import pandas as pd
from rich.console import Console
from rich.table import Table
from scipy import stats

console = Console()

VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# Model pricing presets  ($ / 1M tokens)
# ---------------------------------------------------------------------------

PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"prompt": 2.50, "completion": 10.00},
    "gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
    "gpt-4.1": {"prompt": 2.00, "completion": 8.00},
    "gpt-4.1-mini": {"prompt": 0.40, "completion": 1.60},
    "gpt-4.1-nano": {"prompt": 0.10, "completion": 0.40},
    "o3": {"prompt": 10.00, "completion": 40.00},
    "o4-mini": {"prompt": 1.10, "completion": 4.40},
    "claude-3.5-sonnet": {"prompt": 3.00, "completion": 15.00},
    "claude-3.5-haiku": {"prompt": 0.80, "completion": 4.00},
    "claude-sonnet-4": {"prompt": 3.00, "completion": 15.00},
    "deepseek-chat": {"prompt": 0.27, "completion": 1.10},
    "deepseek-reasoner": {"prompt": 0.55, "completion": 2.19},
    "gemini-2.5-flash": {"prompt": 0.15, "completion": 0.60},
    "gemini-2.5-pro": {"prompt": 1.25, "completion": 10.00},
    "llama-4-maverick": {"prompt": 0.20, "completion": 0.60},
    "llama-4-scout": {"prompt": 0.10, "completion": 0.30},
    "qwq-32b": {"prompt": 0.20, "completion": 0.80},
    "qwen3-coder": {"prompt": 0.10, "completion": 1.00},
    "deepseek-v4-flash": {"prompt": 0.1477, "completion": 0.2954},
}


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------


def wilson_ci(count: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    z = stats.norm.ppf(1 - alpha / 2)
    p = count / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    lo = center - margin
    hi = center + margin
    return (max(0.0, lo), min(1.0, hi))


def mcnemar_paired(test_a: pd.Series, test_b: pd.Series) -> dict[str, float]:
    """McNemar test on paired binary outcomes.  Each series must be aligned
    by index (instance_id)."""
    mask = test_a.notna() & test_b.notna()
    a = test_a[mask].astype(int)
    b = test_b[mask].astype(int)
    n_both = int(((a == 1) & (b == 1)).sum())
    n_a_only = int(((a == 1) & (b == 0)).sum())
    n_b_only = int(((a == 0) & (b == 1)).sum())
    n_neither = int(((a == 0) & (b == 0)).sum())
    total = n_a_only + n_b_only
    if total == 0:
        p_value = 1.0
        stat = 0.0
    else:
        # Continuity-corrected McNemar
        stat = (abs(n_a_only - n_b_only) - 1) ** 2 / total
        p_value = 1 - stats.chi2.cdf(stat, 1)
    return {
        "n": int(len(mask)),
        "both": n_both,
        "a_only": n_a_only,
        "b_only": n_b_only,
        "neither": n_neither,
        "statistic": round(stat, 3),
        "p_value": round(p_value, 6),
        "significant": p_value < 0.05,
    }


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_results(results_dir: str) -> pd.DataFrame:
    """Load all result JSONs and return a flat DataFrame of task-level rows."""
    results_path = Path(results_dir)
    files = sorted(results_path.glob("*.json"))
    if not files:
        console.print(f"[yellow]No result files found in {results_dir}[/yellow]")
        return pd.DataFrame()

    records: list[dict] = []
    for fp in files:
        data = json.loads(fp.read_text())
        run_info = data.get("run_info", {})
        for t in data.get("tasks", []):
            record = {
                "run_timestamp": run_info.get("timestamp", fp.stem),
                "run_dataset": run_info.get("dataset", t.get("dataset", "")),
                **t,
            }
            records.append(record)

    df = pd.DataFrame(records)
    console.print(
        f"[green]Loaded {len(records)} task records from {len(files)} run(s)[/green]"
    )
    return df


# ---------------------------------------------------------------------------
# Aggregate table
# ---------------------------------------------------------------------------


def build_aggregate(
    df: pd.DataFrame, pricing_name: str, alpha: float, aggregation: str, n_runs: int
) -> pd.DataFrame:
    """Build per-harness per-dataset aggregate with CIs.

    aggregation:
      - pool: raw pool all records (simple; note N will be inflated by repeated runs)
      - run-stats: per-run pass@1 → mean ± stddev; CI from t-dist if >=3 runs else bootstrap
      - majority: per-instance majority vote across runs → single deduplicated pass@1
    """
    pricing = PRICING.get(pricing_name, PRICING["gpt-4o"])
    rows: list[dict] = []

    for (harness, ds), g in df.groupby(["harness", "dataset"]):
        unique_instances = g["instance_id"].nunique()

        if aggregation == "majority" and n_runs > 1:
            majority = g.groupby("instance_id")["passed"].mean()
            majority = (majority > 0.5).astype(int)
            n = len(majority)
            passed = int(majority.sum())

            res_maj = g.groupby("instance_id")["resolved"].mean()
            res_maj = (res_maj > 0.5).astype(int)
            resolved = int(res_maj.sum())

            lo, hi = wilson_ci(passed, n, alpha)
            res_lo, res_hi = wilson_ci(resolved, n, alpha)
            build_ok = int(
                (
                    ~g.groupby("instance_id")["error"].first().astype(bool)
                    & g.groupby("instance_id")["build_passed"].first()
                ).sum()
            )
            build_total = n - int(
                g.groupby("instance_id")["error"].first().astype(bool).sum()
            )

        elif aggregation == "run-stats" and n_runs > 1:
            run_pass_rates = []
            run_resolve_rates = []
            for _, rg in g.groupby("run_timestamp"):
                rn = len(rg)
                if rn == 0:
                    continue
                run_pass_rates.append(rg["passed"].sum() / rn)
                run_resolve_rates.append(rg["resolved"].sum() / rn)

            mean_p = np.mean(run_pass_rates)
            std_p = np.std(run_pass_rates, ddof=1) if len(run_pass_rates) > 1 else 0.0

            if len(run_pass_rates) >= 3:
                t_crit = stats.t.ppf(1 - alpha / 2, len(run_pass_rates) - 1)
                margin = t_crit * std_p / np.sqrt(len(run_pass_rates))
                lo, hi = mean_p - margin, mean_p + margin
            else:
                lo, hi = np.percentile(
                    np.random.choice(
                        run_pass_rates, size=(2000, len(run_pass_rates)), replace=True
                    ).mean(axis=1),
                    [alpha / 2 * 100, (1 - alpha / 2) * 100],
                )

            lo = max(0.0, float(lo))
            hi = min(1.0, float(hi))

            mean_r = np.mean(run_resolve_rates)
            res_lo, res_hi = lo, hi

            n = unique_instances
            passed = int(round(mean_p * n))
            resolved = int(round(mean_r * n))
            build_ok = n
            build_total = n

        else:
            n = len(g)
            passed = int(g["passed"].sum())
            resolved = int(g["resolved"].sum())
            lo, hi = wilson_ci(passed, n, alpha)
            res_lo, res_hi = wilson_ci(resolved, n, alpha)
            build_ok = int((~g["error"].astype(bool) & g["build_passed"]).sum())
            build_total = n - int(g["error"].astype(bool).sum())

        prompt_tokens = int(g["prompt_tokens"].sum())
        completion_tokens = int(g["completion_tokens"].sum())
        prompt_cost = prompt_tokens * pricing["prompt"] / 1_000_000
        completion_cost = completion_tokens * pricing["completion"] / 1_000_000
        total_cost = prompt_cost + completion_cost

        rows.append(
            {
                "harness": harness,
                "dataset": ds,
                "n_tasks": n,
                "n_unique": unique_instances,
                "n_runs": n_runs,
                "passed": passed,
                "resolved": resolved,
                "build_ok": build_ok,
                "build_total": build_total,
                "pass@1": round(passed / n, 4) if n else 0,
                "pass_lo": round(lo, 4),
                "pass_hi": round(hi, 4),
                "resolve_rate": round(resolved / n, 4) if n else 0,
                "resolve_lo": round(res_lo, 4),
                "resolve_hi": round(res_hi, 4),
                "build_rate": round(build_ok / build_total, 4) if build_total else 0.0,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "total_cost": round(total_cost, 4),
                "avg_tokens": round((prompt_tokens + completion_tokens) / len(g), 1)
                if len(g)
                else 0,
                "avg_time_s": round(g["execution_time_s"].mean(), 1),
                "avg_api_calls": round(g["api_calls"].mean(), 1),
                "avg_cost": round(total_cost / len(g), 4) if len(g) else 0,
            }
        )

    return pd.DataFrame(rows).sort_values(["dataset", "harness"])


def print_aggregate(
    agg: pd.DataFrame, pricing_name: str, alpha: float, aggregation: str
) -> None:
    """Pretty-print the aggregate table to terminal."""
    ci_label = f"{int(100 * (1 - alpha))}%"

    table = Table(
        title=f"Aggregate Results (pricing={pricing_name}, aggregation={aggregation}, CI={ci_label})"
    )
    table.add_column("Harness", style="cyan")
    table.add_column("Dataset")
    table.add_column("N (unique)", justify="right")
    table.add_column("Runs", justify="right")
    table.add_column(f"Pass@1 [{ci_label} CI]", justify="right")
    table.add_column("Resolve", justify="right")
    table.add_column("Build", justify="right")
    table.add_column("Avg Tokens", justify="right")
    table.add_column("Avg Time (s)", justify="right")
    table.add_column("Avg Cost ($)", justify="right")

    for _, r in agg.iterrows():
        pass_str = f"{r['pass@1']:.4f} [{r['pass_lo']:.4f}, {r['pass_hi']:.4f}]"
        table.add_row(
            r["harness"],
            r["dataset"],
            str(int(r.get("n_unique", r["n_tasks"]))),
            str(int(r.get("n_runs", 1))),
            pass_str,
            f"{r['resolve_rate']:.4f}",
            f"{r['build_rate']:.4f}",
            str(int(r["avg_tokens"])),
            f"{r['avg_time_s']:.1f}",
            f"${r['avg_cost']:.4f}",
        )

    console.print(table)


# ---------------------------------------------------------------------------
# Significance testing
# ---------------------------------------------------------------------------


def build_significance(df: pd.DataFrame, aggregation: str = "pool") -> pd.DataFrame:
    """Pairwise McNemar tests between harnesses, per dataset."""
    rows: list[dict] = []
    datasets = sorted(df["dataset"].unique())
    harnesses = sorted(df["harness"].unique())

    for ds in datasets:
        ds_df = df[df["dataset"] == ds]

        if (
            aggregation in ("majority", "run-stats")
            and ds_df["run_timestamp"].nunique() > 1
        ):
            ds_df = ds_df.groupby(["instance_id", "harness"])["passed"].mean()
            ds_df = (ds_df > 0.5).astype(int).reset_index()

        pivoted = ds_df.pivot_table(
            index="instance_id",
            columns="harness",
            values="passed",
            aggfunc="first",
        )
        for i, ha in enumerate(harnesses):
            for hb in harnesses[i + 1 :]:
                if ha not in pivoted.columns or hb not in pivoted.columns:
                    continue
                r = mcnemar_paired(pivoted[ha], pivoted[hb])
                rows.append(
                    {
                        "dataset": ds,
                        "harness_a": ha,
                        "harness_b": hb,
                        **r,
                    }
                )

    return pd.DataFrame(rows)


def print_significance(sig: pd.DataFrame, alpha: float = 0.05) -> None:
    if sig.empty:
        console.print(
            "[yellow]Need >=2 harnesses per dataset for significance tests[/yellow]"
        )
        return

    table = Table(title="Pairwise Significance (McNemar, continuity-corrected)")
    table.add_column("Dataset")
    table.add_column("A vs B")
    table.add_column("N", justify="right")
    table.add_column("Both", justify="right")
    table.add_column("A only", justify="right")
    table.add_column("B only", justify="right")
    table.add_column("p-value", justify="right")
    table.add_column("Signif?", justify="center")

    for _, r in sig.iterrows():
        sig_str = "** YES **" if r["significant"] else "no"
        sig_style = "[bold green]** YES **[/bold green]" if r["significant"] else "no"
        table.add_row(
            r["dataset"],
            f"{r['harness_a']} vs {r['harness_b']}",
            str(int(r["n"])),
            str(int(r["both"])),
            str(int(r["a_only"])),
            str(int(r["b_only"])),
            f"{r['p_value']:.6f}",
            sig_style,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# LaTeX export
# ---------------------------------------------------------------------------


def export_latex(
    agg: pd.DataFrame, sig: pd.DataFrame, output_dir: Path, alpha: float
) -> None:
    ci_label = f"{int(100 * (1 - alpha))}%"

    # --- Main results table ---
    tex_cols = {
        "Harness": lambda r: r["harness"],
        "Dataset": lambda r: r["dataset"],
        "N": lambda r: str(int(r["n_tasks"])),
        f"Pass@1 ({ci_label} CI)": lambda r: (
            f"${r['pass@1']:.3f}$ $[{r['pass_lo']:.3f}, {r['pass_hi']:.3f}]$"
        ),
        "Resolve": lambda r: f"${r['resolve_rate']:.3f}$",
        "Build": lambda r: f"${r['build_rate']:.3f}$",
        "Tokens/Task": lambda r: str(int(r["avg_tokens"])),
        "Time (s)": lambda r: f"{r['avg_time_s']:.1f}",
        "Cost ($)": lambda r: f"\\${r['avg_cost']:.4f}",
    }

    lines: list[str] = []
    lines.append(r"\begin{table}[htbp]")
    lines.append(r"  \centering")
    lines.append(r"  \caption{Benchmark results with Wilson confidence intervals.}")
    col_spec = "l" + "l" + "r" * (len(tex_cols) - 2)
    lines.append(r"  \begin{tabular}{" + col_spec + "}")
    lines.append(r"    \toprule")
    header = " & ".join(tex_cols.keys())
    lines.append(f"    {header} \\\\")
    lines.append(r"    \midrule")

    for _, r in agg.iterrows():
        vals = [fn(r) for fn in tex_cols.values()]
        lines.append(f"    {' & '.join(vals)} \\\\")

    lines.append(r"    \bottomrule")
    lines.append(r"  \end{tabular}")
    lines.append(r"  \label{tab:main-results}")
    lines.append(r"\end{table}")

    tex_file = output_dir / "main_results.tex"
    tex_file.write_text("\n".join(lines))
    console.print(f"[green]LaTeX table written to {tex_file}[/green]")

    # --- Significance table ---
    if not sig.empty:
        sig_lines: list[str] = []
        sig_lines.append(r"\begin{table}[htbp]")
        sig_lines.append(r"  \centering")
        sig_lines.append(
            r"  \caption{Pairwise McNemar significance tests (continuity-corrected).}"
        )
        sig_lines.append(r"  \begin{tabular}{lllrrrc}")
        sig_lines.append(r"    \toprule")
        sig_lines.append(r"    Dataset & A & B & N & A-only & B-only & $p$ \\")
        sig_lines.append(r"    \midrule")

        for _, r in sig.iterrows():
            p_str = r"$<0.001$" if r["p_value"] < 0.001 else f"${r['p_value']:.4f}$"
            sig_lines.append(
                f"    {r['dataset']} & {r['harness_a']} & {r['harness_b']} & "
                f"{int(r['n'])} & {int(r['a_only'])} & {int(r['b_only'])} & {p_str} \\\\"
            )

        sig_lines.append(r"    \bottomrule")
        sig_lines.append(r"  \end{tabular}")
        sig_lines.append(r"  \label{tab:significance}")
        sig_lines.append(r"\end{table}")

        tex_file = output_dir / "significance.tex"
        tex_file.write_text("\n".join(sig_lines))
        console.print(f"[green]LaTeX table written to {tex_file}[/green]")


# ---------------------------------------------------------------------------
# Plots
# ---------------------------------------------------------------------------


def generate_plots(
    agg: pd.DataFrame, df: pd.DataFrame, output_dir: Path, pricing_name: str
) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import seaborn as sns
    except ImportError:
        console.print("[red]matplotlib/seaborn not installed; skipping plots[/red]")
        return

    sns.set_theme(context="paper", style="whitegrid", font_scale=1.15)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ---- 1. Pass@1 bar chart with CI error bars ----
    fig, ax = plt.subplots(figsize=(8, 5))
    harnesses = list(agg["harness"].unique())
    x = np.arange(len(harnesses))
    widths = 0.35

    for ds_i, (ds_name, ds_agg) in enumerate(agg.groupby("dataset")):
        ds_agg = ds_agg.set_index("harness").reindex(harnesses)
        offset = (ds_i - 0.5) * widths
        err = np.array(
            [
                [
                    ds_agg.loc[h, "pass@1"] - ds_agg.loc[h, "pass_lo"]
                    if h in ds_agg.index
                    else 0
                    for h in harnesses
                ],
                [
                    ds_agg.loc[h, "pass_hi"] - ds_agg.loc[h, "pass@1"]
                    if h in ds_agg.index
                    else 0
                    for h in harnesses
                ],
            ]
        )
        vals = [ds_agg.loc[h, "pass@1"] if h in ds_agg.index else 0 for h in harnesses]
        ax.bar(x + offset, vals, widths, yerr=err, capsize=4, label=ds_name)

    ax.set_ylabel("Pass@1")
    ax.set_xticks(x)
    ax.set_xticklabels(harnesses)
    ax.legend(loc="lower right")
    ax.set_ylim(0, 1)
    fig.tight_layout()
    fig.savefig(output_dir / "pass_at_1.pdf", dpi=150)
    plt.close(fig)

    # ---- 2. Cost vs Pass@1 scatter ----
    fig, ax = plt.subplots(figsize=(7, 5))
    for _, r in agg.iterrows():
        ax.scatter(
            r["avg_cost"], r["pass@1"], s=120, label=f"{r['harness']}-{r['dataset']}"
        )
        ax.errorbar(
            r["avg_cost"],
            r["pass@1"],
            xerr=0,
            yerr=[[r["pass@1"] - r["pass_lo"]], [r["pass_hi"] - r["pass@1"]]],
            capsize=3,
            alpha=0.4,
        )
    ax.set_xlabel("Avg Cost per Task ($)")
    ax.set_ylabel("Pass@1")
    ax.legend(fontsize=7, loc="lower right")
    fig.tight_layout()
    fig.savefig(output_dir / "cost_vs_pass.pdf", dpi=150)
    plt.close(fig)

    # ---- 3. Token distribution (violin) ----
    if not df.empty:
        df_plot = df[df["harness"].isin(harnesses)].copy()
        df_plot["tokens_k"] = df_plot["token_count"] / 1000
        fig, ax = plt.subplots(figsize=(8, 5))
        sns.violinplot(
            data=df_plot,
            x="harness",
            y="tokens_k",
            hue="dataset",
            split=True,
            inner="quart",
            cut=0,
            ax=ax,
        )
        ax.set_ylabel("Tokens per Task (k)")
        ax.set_xlabel("")
        fig.tight_layout()
        fig.savefig(output_dir / "token_distribution.pdf", dpi=150)
        plt.close(fig)

    # ---- 4. Time distribution (violin) ----
    if not df.empty:
        fig, ax = plt.subplots(figsize=(8, 5))
        sns.violinplot(
            data=df,
            x="harness",
            y="execution_time_s",
            hue="dataset",
            split=True,
            inner="quart",
            cut=0,
            ax=ax,
        )
        ax.set_ylabel("Execution Time (s)")
        ax.set_xlabel("")
        fig.tight_layout()
        fig.savefig(output_dir / "time_distribution.pdf", dpi=150)
        plt.close(fig)

    console.print(f"[green]Plots written to {output_dir}/ (PDF, 150 dpi)[/green]")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.option(
    "--results-dir",
    "-r",
    default="results",
    type=click.Path(exists=True, path_type=Path),
    help="Directory containing results/*.json files",
)
@click.option(
    "--output-dir",
    "-o",
    default="paper_output",
    type=click.Path(path_type=Path),
    help="Output directory for tables and figures",
)
@click.option(
    "--pricing",
    "-p",
    default="gpt-4o",
    type=click.Choice(sorted(PRICING.keys())),
    show_default=True,
    help="Model pricing preset for cost calculation",
)
@click.option(
    "--alpha",
    type=float,
    default=0.05,
    show_default=True,
    help="Significance level for confidence intervals and tests",
)
@click.option("--plots/--no-plots", default=True, help="Generate plots")
@click.option("--latex/--no-latex", default=True, help="Export LaTeX .tex tables")
@click.option(
    "--aggregation",
    "-a",
    default="pool",
    type=click.Choice(["pool", "run-stats", "majority"]),
    show_default=True,
    help="Multi-run aggregation: pool (raw, N inflated) | run-stats (per-run mean±std) | majority (per-instance vote)",
)
def main(
    results_dir: Path,
    output_dir: Path,
    pricing: str,
    alpha: float,
    plots: bool,
    latex: bool,
    aggregation: str,
) -> None:
    df = load_results(str(results_dir))
    if df.empty:
        console.print(
            "[red]No data loaded. Run tests to populate results/ first.[/red]"
        )
        return

    # Check for required columns
    required = {
        "harness",
        "dataset",
        "passed",
        "resolved",
        "instance_id",
        "prompt_tokens",
        "completion_tokens",
        "execution_time_s",
        "api_calls",
    }
    missing = required - set(df.columns)
    if missing:
        console.print(f"[red]Missing columns in data: {missing}[/red]")
        return

    n_runs = df["run_timestamp"].nunique()
    if n_runs > 1:
        console.print(
            f"[bold cyan]Detected {n_runs} runs. Aggregation mode: {aggregation}[/bold cyan]"
        )
        if aggregation == "pool":
            console.print(
                "[yellow]  Note: 'pool' inflates N by repeated instances. "
                "Use --aggregation majority or run-stats for rigor.[/yellow]"
            )

    output_dir.mkdir(parents=True, exist_ok=True)

    console.print()
    console.rule("[bold]Aggregate Results[/bold]")
    agg = build_aggregate(df, pricing, alpha, aggregation, n_runs)
    print_aggregate(agg, pricing, alpha, aggregation)

    console.print()
    console.rule("[bold]Significance Tests[/bold]")
    sig = build_significance(df, aggregation)
    print_significance(sig, alpha)

    if latex:
        console.print()
        console.rule("[bold]LaTeX Export[/bold]")
        export_latex(agg, sig, output_dir, alpha)

    if plots:
        console.print()
        console.rule("[bold]Plots[/bold]")
        generate_plots(agg, df, output_dir, pricing)

    console.print(f"\n[bold green]Done. Output: {output_dir.resolve()}/[/bold green]")


if __name__ == "__main__":
    main()
