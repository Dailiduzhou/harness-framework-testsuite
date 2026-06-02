FROM python:3.11-slim-bookworm

LABEL org.opencontainers.image.title="harness-framework-testsuite"
LABEL org.opencontainers.image.description="Test suite for harness frameworks (OpenCode, Pi) on SWE-Bench Lite and RepoBench"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    curl \
    jq \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config/ ./config/
COPY scripts/ ./scripts/
COPY data/ ./data/

RUN mkdir -p /app/results

ENV PYTHONPATH=/app
ENV HARVEST_CONFIG_PATH=/app/config/default.yaml

CMD ["python", "-m", "scripts.run_test", "--help"]
