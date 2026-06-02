# harness-framework-testsuite

Test suite for harness frameworks (OpenCode, Pi). SWE-Bench Lite + RepoBench. Docker sandboxed, non-interactive harness invocation, structured metrics collection.

## Quick Start

```bash
cp .env.example .env          # edit LLM_API_KEY
make build                    # build Docker image
make test                     # run full suite (all harnesses, SWE-Bench Lite)
make metrics                  # print latest result summary
```

## Configuration

### Environment

Copy `.env.example` to `.env` and set your LLM credentials:

```env
LLM_API_KEY=sk-your-api-key-here
LLM_API_BASE=https://api.openai.com/v1
LLM_MODEL=gpt-4o
```

### config/default.yaml

All settings in one file. Copy to `config/local.yaml` to override:

```yaml
llm:
  provider: openai
  api_key: ${LLM_API_KEY}          # resolved from env var
  api_base: ${LLM_API_BASE:-}      # :- means empty default
  model: gpt-4o
  max_tokens: 4096
  temperature: 0.0                 # deterministic for benchmarking
  request_delay: 0.1               # seconds between API calls (reduce cache bias)

harness:
  opencode:
    enabled: true
    entrypoint: opencode            # CLI binary name
    timeout_per_task: 600           # seconds per task
  pi:
    enabled: true
    entrypoint: pi
    timeout_per_task: 600

datasets:
  swebench-lite:
    path: data/swebench-lite
    max_instances: 0               # 0 = all
  repobench:
    path: data/repobench
    max_instances: 0

execution:
  max_workers: 4
  retry_count: 2
  retry_delay: 5

output:
  results_dir: results
  format: json
```

`${VAR}` values resolve from environment. `${VAR:-default}` falls back to `default` when the env var is unset.

## Datasets

Place `.json` or `.jsonl` files under `data/<dataset-name>/`. Each record:

```json
{
  "instance_id": "unique-id",
  "repo": "owner/repo-name",
  "problem_statement": "Fix the bug in UserService.getUser() ...",
  "base_commit": "abc123",
  "test_patch": "diff --git ..."
}
```

Field aliases: `instance_id` ↔ `id`, `problem_statement` ↔ `prompt` ↔ `task_description`, `repo` ↔ `repository`.

Configure path and limits in `config/default.yaml` → `datasets`.

Sample data is included under `data/swebench-lite/sample.json` and `data/repobench/sample.json`.

## Harness Adapters

Each harness is a thin adapter that wraps the CLI tool in non-interactive mode.

### OpenCode

Invoked as (`scripts/harness/opencode.py`):

```
opencode --non-interactive --model gpt-4o --max-tokens 4096 \
  --temperature 0.0 --output /tmp/out.txt --workspace /path/to/repo \
  "<prompt>"
```

### Pi

Invoked as (`scripts/harness/pi.py`):

```
pi --batch --model gpt-4o --max-tokens 4096 --temperature 0.0 \
  --output-file /tmp/out.txt --repo /path/to/repo "<prompt>"
```

### Adding a new harness

1. Create `scripts/harness/<name>.py` with `prepare_command()` and `parse_output()`.
2. Register in `scripts/run_test.py` → `HARNESS_ADAPTERS` dict.
3. Add harness config block in `config/default.yaml`.

## Metrics Collected

| Metric | Key |
|--------|-----|
| Pass@1 | `pass@1` |
| Token usage (total/prompt/completion) | `total_tokens` / per-task `token_count` |
| API call count | `total_api_calls` / per-task `api_calls` |
| Execution time | `total_time_s` / per-task `execution_time_s` |
| Build/Compilation rate | `build_rate` |
| Resolve rate | `resolve_rate` |

All metrics saved to `results/results_<dataset>_<timestamp>.json`.

## Makefile Reference

```
make build                 Build Docker image
make test                  Full suite (all harnesses, SWE-Bench Lite)
make test-opencode         OpenCode only
make test-pi               Pi only
make test-repobench        On RepoBench dataset
make metrics               Latest result summary (rich table)
make metrics-history       All historical runs
make shell                 Bash shell inside test container (debugging)
make clean                 Remove results + image
make help                  Print all targets
```

Override defaults:

```bash
make test DATASET=repobench HARNESS=pi MAX_WORKERS=8 TIMEOUT=7200 CONFIG=config/local.yaml
```

## Project Structure

```
├── Dockerfile
├── Makefile
├── requirements.txt
├── config/
│   └── default.yaml        # main configuration
├── scripts/
│   ├── run_test.py          # entry point (orchestration)
│   ├── collect_metrics.py   # metrics CLI
│   ├── config.py            # YAML + env var resolver
│   ├── metrics.py           # data models
│   ├── harness/
│   │   ├── opencode.py      # OpenCode adapter
│   │   └── pi.py            # Pi adapter
│   └── dataset/
│       ├── base.py           # dataset loader interface
│       ├── swebench_lite.py  # SWE-Bench Lite loader
│       └── repobench.py      # RepoBench loader
├── data/
│   ├── swebench-lite/        # SWE-Bench Lite .json/.jsonl
│   └── repobench/            # RepoBench .json/.jsonl
└── results/                  # test output (gitignored)
```
