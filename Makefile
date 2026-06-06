.PHONY: install install-download install-paper install-all \
        download-swebench download-swebench-test download-repobench download-datasets \
        paper-analyze paper-analyze-majority paper-analyze-runstats \
        build build-nocache test test-opencode test-pi test-repobench \
        metrics metrics-history shell clean clean-containers help

IMAGE_NAME ?= harness-testsuite
IMAGE_TAG ?= latest
CONTAINER_NAME ?= harness-test-run
CONFIG ?= config/default.yaml
DATASET ?= swebench-lite
HARNESS ?= all
MAX_WORKERS ?= 4
TIMEOUT ?= 3600
APT_MIRROR ?= mirrors.aliyun.com
PIP_INDEX ?= https://mirrors.aliyun.com/pypi/simple/
OPENCODE_VERSION ?= 1.15.13
PI_VERSION ?= 0.78.0
DEEPSEEK_API_KEY ?=
DEEPSEEK_BASE_URL ?= https://api.deepseek.com/v1

# ——— Local dev (uv) ——————————————————————————————————————

install: ## Install core dependencies via uv
	uv sync

install-download: install ## + datasets download extras
	uv sync --extra download

install-paper: install ## + paper analysis extras (scipy, matplotlib, seaborn)
	uv sync --extra paper

install-all: install ## All extras
	uv sync --extra download --extra paper

download-swebench: ## Download SWE-Bench Lite (dev split, 300 instances)
	uv run python scripts/download_datasets.py --dataset swebench-lite

download-swebench-test: ## Download SWE-Bench Lite test split (23 instances)
	uv run python scripts/download_datasets.py --dataset swebench-lite --split test

download-repobench: ## Download RepoBench dataset
	uv run python scripts/download_datasets.py --dataset repobench

download-datasets: ## Download all benchmark datasets
	uv run python scripts/download_datasets.py --dataset all

# ——— Paper Analysis ——————————————————————————————————————

paper-analyze: ## Run paper analysis (pool mode, plots + LaTeX)
	uv run python scripts/paper_analysis.py --plots --latex

paper-analyze-majority: ## Paper analysis with majority-vote aggregation (recommended for paper)
	uv run python scripts/paper_analysis.py --aggregation majority --plots --latex

paper-analyze-runstats: ## Paper analysis with per-run mean ± std (shows variance)
	uv run python scripts/paper_analysis.py --aggregation run-stats --plots --latex

# ——— Build ——————————————————————————————————————————————

build: ## Build the Docker image
	docker build \
		--build-arg APT_MIRROR=$(APT_MIRROR) \
		--build-arg PIP_INDEX=$(PIP_INDEX) \
		--build-arg OPENCODE_VERSION=$(OPENCODE_VERSION) \
		--build-arg PI_VERSION=$(PI_VERSION) \
		--build-arg DEEPSEEK_API_KEY=$(DEEPSEEK_API_KEY) \
		--build-arg DEEPSEEK_BASE_URL=$(DEEPSEEK_BASE_URL) \
		-t $(IMAGE_NAME):$(IMAGE_TAG) .

build-nocache: ## Build without cache
	docker build --no-cache \
		--build-arg APT_MIRROR=$(APT_MIRROR) \
		--build-arg PIP_INDEX=$(PIP_INDEX) \
		--build-arg OPENCODE_VERSION=$(OPENCODE_VERSION) \
		--build-arg PI_VERSION=$(PI_VERSION) \
		--build-arg DEEPSEEK_API_KEY=$(DEEPSEEK_API_KEY) \
		--build-arg DEEPSEEK_BASE_URL=$(DEEPSEEK_BASE_URL) \
		-t $(IMAGE_NAME):$(IMAGE_TAG) .

# ——— Test ————————————————————————————————————————————————

test: build ## Run full test suite (all harnesses, SWE-Bench Lite)
	docker run --rm \
		--name $(CONTAINER_NAME) \
		-v $(PWD)/results:/app/results \
		-v $(PWD)/config:/app/config:ro \
		-v $(PWD)/data:/app/data:ro \
		-e HARVEST_CONFIG_PATH=/app/$(CONFIG) \
		-e DEEPSEEK_API_KEY \
		-e DEEPSEEK_BASE_URL \
		$(IMAGE_NAME):$(IMAGE_TAG) \
		python -m scripts.run_test \
			--dataset $(DATASET) \
			--harness $(HARNESS) \
			--max-workers $(MAX_WORKERS) \
			--timeout $(TIMEOUT)

test-opencode: build ## Test only OpenCode harness
	docker run --rm \
		--name $(CONTAINER_NAME) \
		-v $(PWD)/results:/app/results \
		-v $(PWD)/config:/app/config:ro \
		-v $(PWD)/data:/app/data:ro \
		-e HARVEST_CONFIG_PATH=/app/$(CONFIG) \
		-e DEEPSEEK_API_KEY \
		-e DEEPSEEK_BASE_URL \
		$(IMAGE_NAME):$(IMAGE_TAG) \
		python -m scripts.run_test \
			--dataset $(DATASET) \
			--harness opencode \
			--max-workers $(MAX_WORKERS) \
			--timeout $(TIMEOUT)

test-pi: build ## Test only Pi harness
	docker run --rm \
		--name $(CONTAINER_NAME) \
		-v $(PWD)/results:/app/results \
		-v $(PWD)/config:/app/config:ro \
		-v $(PWD)/data:/app/data:ro \
		-e HARVEST_CONFIG_PATH=/app/$(CONFIG) \
		-e DEEPSEEK_API_KEY \
		-e DEEPSEEK_BASE_URL \
		$(IMAGE_NAME):$(IMAGE_TAG) \
		python -m scripts.run_test \
			--dataset $(DATASET) \
			--harness pi \
			--max-workers $(MAX_WORKERS) \
			--timeout $(TIMEOUT)

test-repobench: build ## Test on RepoBench dataset
	docker run --rm \
		--name $(CONTAINER_NAME) \
		-v $(PWD)/results:/app/results \
		-v $(PWD)/config:/app/config:ro \
		-v $(PWD)/data:/app/data:ro \
		-e HARVEST_CONFIG_PATH=/app/$(CONFIG) \
		-e DEEPSEEK_API_KEY \
		-e DEEPSEEK_BASE_URL \
		$(IMAGE_NAME):$(IMAGE_TAG) \
		python -m scripts.run_test \
			--dataset repobench \
			--harness $(HARNESS) \
			--max-workers $(MAX_WORKERS) \
			--timeout $(TIMEOUT)

# ——— Metrics —————————————————————————————————————————————

metrics: ## Print metrics summary from latest results
	@ls -t results/*.json 2>/dev/null | head -1 | xargs python -m scripts.collect_metrics --summary

metrics-history: ## Print full metrics history
	python -m scripts.collect_metrics --history --results-dir results/

# ——— Shell / Debug ———————————————————————————————————————

shell: build ## Open a shell in the test container
	docker run --rm -it \
		--name $(CONTAINER_NAME) \
		-v $(PWD)/results:/app/results \
		-v $(PWD)/config:/app/config:ro \
		-v $(PWD)/data:/app/data:ro \
		-e HARVEST_CONFIG_PATH=/app/$(CONFIG) \
		-e DEEPSEEK_API_KEY \
		-e DEEPSEEK_BASE_URL \
		$(IMAGE_NAME):$(IMAGE_TAG) \
		/bin/bash

# ——— Housekeeping ————————————————————————————————————————

clean: ## Remove build artifacts and results
	rm -rf results/*.json results/*.csv
	-docker rmi $(IMAGE_NAME):$(IMAGE_TAG) 2>/dev/null || true

clean-containers: ## Remove dangling containers
	docker container prune -f

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-25s\033[0m %s\n", $$1, $$2}'
