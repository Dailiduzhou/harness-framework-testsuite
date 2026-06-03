# harness-framework-testsuite

Test suite for AI coding harness frameworks (OpenCode, Pi). Evaluates both tools against SWE-Bench Lite and RepoBench in Docker-sandboxed, non-interactive mode with structured metrics collection and publication-ready analysis.

## Quick Start

```bash
# 1. Setup
cp .env.example .env            # edit LLM_API_KEY
make install-all                # uv sync with all extras

# 2. Download benchmark datasets
make download-swebench          # SWE-Bench Lite (300 instances)

# 3. Run tests (Docker container, pinned harness versions)
make test-opencode OPENCODE_VERSION=1.15.13 PI_VERSION=0.78.0

# 4. View results
make metrics
```

## Development Environment

### Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Docker (for running tests in sandboxed containers)

### Setup

```bash
make install                  # core dependencies only
make install-download         # + datasets for downloading benchmarks
make install-paper            # + scipy, matplotlib, seaborn for paper analysis
make install-all              # everything
```

Configuration is layered: `.env` for secrets, `config/default.yaml` for defaults, `config/local.yaml` for overrides.

## Datasets

### Via download script (recommended)

```bash
make download-swebench          # SWE-Bench Lite dev split (300 instances)
make download-swebench-test      # SWE-Bench Lite test split (23 instances)
make download-repobench          # RepoBench
make download-datasets           # all datasets
```

Or with custom limits:

```bash
uv run python scripts/download_datasets.py --dataset swebench-lite --max-instances 50 --split test
```

The script pulls from HuggingFace and writes JSONL files directly to `data/<dataset>/`.

### Manual (JSON/JSONL)

Place `.json` or `.jsonl` files under `data/<dataset-name>/`. Each record:

```json
{
  "instance_id": "unique-id",
  "repo": "owner/repo-name",
  "problem_statement": "Fix the null pointer exception in ...",
  "base_commit": "abc123",
  "test_patch": "diff --git ..."
}
```

Field aliases: `instance_id` ↔ `id`, `problem_statement` ↔ `prompt` ↔ `task_description`, `repo` ↔ `repository`.

Configure path and `max_instances` limits in `config/default.yaml` → `datasets`.

Sample data: `data/swebench-lite/sample.json` (3 instances), `data/repobench/sample.json` (2 instances).

## Running Tests

All tests run inside a Docker container. The harness tools (OpenCode, Pi) are installed at fixed versions during image build via a multi-stage Dockerfile.

```bash
# Build image with pinned harness versions
make build OPENCODE_VERSION=1.15.13 PI_VERSION=0.78.0

# Run tests (builds automatically if needed)
make test                                 # all harnesses, SWE-Bench Lite
make test-opencode                        # OpenCode only
make test-pi                              # Pi only
make test-repobench                       # RepoBench dataset

# Override defaults
make test DATASET=repobench HARNESS=pi MAX_WORKERS=8 TIMEOUT=7200 CONFIG=config/local.yaml
```

### Multi-run for statistical rigor

Run each harness × dataset combination at least 3 times to reduce LLM non-determinism bias:

```bash
make test-opencode   # run 1
make test-opencode   # run 2
make test-opencode   # run 3
make test-pi         # run 1
make test-pi         # run 2
make test-pi         # run 3
```

Results accumulate in `results/` as timestamped JSON files. The paper analysis script detects and aggregates multiple runs automatically.

## Results & Metrics

### Output format

Each run produces `results/results_<dataset>_<timestamp>.json`:

```json
{
  "run_info": { "dataset": "swebench-lite", "harness": "all", "timestamp": "..." },
  "results": [
    { "harness": "opencode", "total": 300, "passed": 120, "pass@1": 0.4, ... }
  ],
  "tasks": [
    { "instance_id": "django__django-12345", "harness": "opencode", "passed": true,
      "token_count": 18500, "execution_time_s": 23.5, ... }
  ]
}
```

### Quick metrics

```bash
make metrics                    # latest run summary (rich table)
make metrics-history            # all historical runs
```

### Metrics collected

| Metric | Key | Description |
|--------|-----|-------------|
| Pass@1 | `pass@1` | Fraction of tasks where tests pass |
| Resolve rate | `resolve_rate` | Fraction of tasks fully resolved |
| Build rate | `build_rate` | Fraction of non-error tasks that compile |
| Token usage | `total_tokens`, `prompt_tokens`, `completion_tokens` | LLM token consumption |
| API calls | `total_api_calls` | Number of LLM API requests |
| Execution time | `execution_time_s` | Wall time per task |
| Cost | computed by paper analysis | $ based on model pricing |

## Paper Analysis Pipeline

The `scripts/paper_analysis.py` script transforms raw `results/*.json` into publication-ready artifacts: tables with Wilson confidence intervals, McNemar significance tests, cost breakdowns, and PDF figures.

### Usage

```bash
# Installation
make install-paper

# Basic analysis (pool mode, plots + LaTeX)
make paper-analyze

# Majority-vote aggregation (recommended for academic papers)
make paper-analyze-majority

# Per-run mean ± std (shows variance across runs)
make paper-analyze-runstats

# Custom pricing model
uv run python scripts/paper_analysis.py --pricing deepseek-chat
```

### Aggregation modes

When multiple runs exist in `results/`, choose how to combine them:

| Mode | N count | Pass@1 | CI method | When to use |
|------|---------|--------|-----------|-------------|
| `--aggregation pool` (default) | Inflated | Sum/Total | Wilson | Quick preview |
| `--aggregation majority` | Deduplicated | Per-instance majority vote | Wilson | **Recommended for papers** |
| `--aggregation run-stats` | Deduplicated | Mean ± std across runs | t-dist / bootstrap | Show variance / stability |

The `majority` mode eliminates LLM non-determinism: an instance is "passed" only if the majority of runs (>50%) passed it.

### Output files

```
paper_output/
├── main_results.tex              # LaTeX main results table → \input{main_results}
├── significance.tex              # LaTeX significance table → \input{significance}
├── pass_at_1.pdf                 # Bar chart with CI error bars
├── cost_vs_pass.pdf              # Cost vs Pass@1 scatter
├── token_distribution.pdf        # Token usage violin plot
└── time_distribution.pdf         # Execution time violin plot
```

### Statistical methods

| Method | Use |
|--------|-----|
| Wilson score interval | 95% CI for Pass@1, Resolve, Build rate (robust for small N) |
| McNemar test (continuity-corrected) | Pairwise significance between harnesses on paired instances |
| t-distribution CI | Pass@1 CI for run-stats mode with ≥3 runs |
| Bootstrap CI | Fallback for run-stats with <3 runs |

### Model pricing presets

Built-in pricing for 18 models. Override with `--pricing`:

```
gpt-4o, gpt-4o-mini, gpt-4.1, o3, o4-mini,
claude-3.5-sonnet, claude-sonnet-4,
deepseek-chat, deepseek-reasoner, deepseek-v4-flash,
gemini-2.5-flash, gemini-2.5-pro,
llama-4-maverick, qwen3-coder, ...
```

Add new models by editing `PRICING` dict in `scripts/paper_analysis.py`.

## Harness Adapters

Each harness is a thin adapter that wraps the CLI tool in non-interactive mode. Adapters inherit from `HarnessAdapter` (`scripts/harness/base.py`) which provides `run()` via `subprocess`.

### OpenCode

```
opencode --non-interactive --model gpt-4o --max-tokens 4096 \
  --temperature 0.0 --output /tmp/out.txt --workspace /path/to/repo \
  "<prompt>"
```

### Pi

```
pi --batch --model gpt-4o --max-tokens 4096 --temperature 0.0 \
  --output-file /tmp/out.txt --repo /path/to/repo "<prompt>"
```

### Adding a new harness

1. Create `scripts/harness/<name>.py` inheriting `HarnessAdapter` with `prepare_command()` and `parse_output()`.
2. Register in `scripts/run_test.py` → `HARNESS_ADAPTERS` dict.
3. Add harness config block in `config/default.yaml`.

## Docker Build

Multi-stage build pins CLI tool versions:

```
┌─ Stage 1: node:22-bookworm-slim ──────────────────────┐
│  npm install -g opencode-ai@VER pi@VER                 │
│  cp -d /usr/local/bin/{opencode,pi} → /export-bins/    │  (preserve symlinks)
└──────────────────────────┬────────────────────────────┘
                           │ COPY node_modules, /export-bins/, node binary
┌─ Stage 2: python:3.11-slim-bookworm ──────────────────┐
│  + nodejs, git, build-essential, ...                   │
│  + Node 22 binary overrides Debian's Node 18           │
│  + opencode --version && pi --version (build-time test)│
└────────────────────────────────────────────────────────┘
```

## Makefile Reference

```
Development:
  make install               Core dependencies (uv sync)
  make install-download      + datasets download extras
  make install-paper         + paper analysis extras (scipy, matplotlib, seaborn)
  make install-all           All extras

Datasets (local):
  make download-swebench     SWE-Bench Lite dev split (300 instances)
  make download-repobench    RepoBench
  make download-datasets     All datasets

Testing (Docker):
  make build                 Build Docker image
  make test                  Full suite
  make test-opencode         OpenCode only
  make test-pi               Pi only
  make test-repobench        RepoBench dataset

Paper Analysis (local):
  make paper-analyze         Pool mode, plots + LaTeX
  make paper-analyze-majority  Majority-vote (recommended)
  make paper-analyze-runstats  Per-run mean ± std

Metrics:
  make metrics               Latest result summary (rich table)
  make metrics-history       All historical runs

Debug:
  make shell                 Bash shell inside test container
  make clean                 Remove results + Docker image
  make help                  Print all targets
```

Override variables: `make test HARNESS=pi DATASET=repobench OPENCODE_VERSION=1.15.13`.

## Project Structure

```
├── Dockerfile                 # Multi-stage: npm install harness tools → copy to runtime
├── Makefile                   # All targets: build, test, paper-analyze, etc.
├── pyproject.toml             # uv project config, optional deps: download, paper
├── requirements.txt           # pip fallback (used inside Docker)
├── .env.example               # LLM_API_KEY template
├── config/
│   └── default.yaml           # Main configuration (LLM, harness, dataset, execution)
├── scripts/
│   ├── run_test.py            # Entry point: orchestration
│   ├── collect_metrics.py     # Metrics CLI (quick terminal summaries)
│   ├── config.py              # YAML + env var resolver
│   ├── metrics.py             # TaskMetrics, SuiteResult data models
│   ├── download_datasets.py   # HuggingFace → JSONL dataset downloader
│   ├── paper_analysis.py      # Paper pipeline: CI, McNemar, cost, plots, LaTeX
│   ├── harness/
│   │   ├── base.py            # Abstract HarnessAdapter (subprocess.run)
│   │   ├── opencode.py        # OpenCode adapter
│   │   └── pi.py              # Pi adapter
│   └── dataset/
│       ├── base.py            # TaskInstance model + DatasetLoader ABC
│       ├── swebench_lite.py   # SWE-Bench Lite JSON/JSONL loader
│       └── repobench.py       # RepoBench JSON/JSONL loader
├── data/
│   ├── swebench-lite/         # .json/.jsonl (gitignored)
│   └── repobench/             # .json/.jsonl (gitignored)
├── results/                   # Test output .json (gitignored)
└── paper_output/              # Paper tables & figures (gitignored)
```
