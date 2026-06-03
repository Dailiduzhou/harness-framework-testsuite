.PHONY: build test clean shell metrics help

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

# ——— Local dev (uv) ——————————————————————————————————————

install: ## Install project + dev dependencies via uv
	uv sync
	uv sync --extra download
	uv sync --extra paper

download-swebench: ## Download SWE-Bench Lite dataset
	uv run python scripts/download_datasets.py --dataset swebench-lite

download-repobench: ## Download RepoBench dataset
	uv run python scripts/download_datasets.py --dataset repobench

download-datasets: ## Download all benchmark datasets
	uv run python scripts/download_datasets.py --dataset all

# ——— Paper Analysis ——————————————————————————————————————

paper-analyze: ## Run paper analysis (default: results/ -> paper_output/)
	uv run python scripts/paper_analysis.py

paper-analyze-all: ## Paper analysis with all extras
	uv run python scripts/paper_analysis.py --plots --latex

paper-analyze-noplot: ## Paper analysis without plots
	uv run python scripts/paper_analysis.py --no-plots

# ——— Build ——————————————————————————————————————————————

build: ## Build the Docker image
	docker build \
		--build-arg APT_MIRROR=$(APT_MIRROR) \
		--build-arg PIP_INDEX=$(PIP_INDEX) \
		--build-arg OPENCODE_VERSION=$(OPENCODE_VERSION) \
		--build-arg PI_VERSION=$(PI_VERSION) \
		-t $(IMAGE_NAME):$(IMAGE_TAG) .

build-nocache: ## Build without cache
	docker build --no-cache \
		--build-arg APT_MIRROR=$(APT_MIRROR) \
		--build-arg PIP_INDEX=$(PIP_INDEX) \
		--build-arg OPENCODE_VERSION=$(OPENCODE_VERSION) \
		--build-arg PI_VERSION=$(PI_VERSION) \
		-t $(IMAGE_NAME):$(IMAGE_TAG) .

# ——— Test ————————————————————————————————————————————————

test: build ## Run full test suite (default: all harnesses, SWE-Bench Lite)
	docker run --rm \
		--name $(CONTAINER_NAME) \
		-v $(PWD)/results:/app/results \
		-v $(PWD)/config:/app/config:ro \
		-v $(PWD)/data:/app/data:ro \
		-e HARVEST_CONFIG_PATH=/app/$(CONFIG) \
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
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
