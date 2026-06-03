# Stage 1: Install harness CLI tools (Node.js)
FROM node:22-bookworm-slim AS harness-deps

ARG OPENCODE_VERSION=1.15.3
ARG PI_VERSION=0.78.0

RUN npm install -g opencode-ai@${OPENCODE_VERSION}
RUN npm i @earendil-works/pi-coding-agent@${PI_VERSION}
# Stage 2: Runtime
FROM python:3.11-slim-bookworm

LABEL org.opencontainers.image.title="harness-framework-testsuite"
LABEL org.opencontainers.image.description="Test suite for harness frameworks (OpenCode, Pi) on SWE-Bench Lite and RepoBench"

ENV DEBIAN_FRONTEND=noninteractive \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  PIP_NO_CACHE_DIR=1 \
  PIP_DISABLE_PIP_VERSION_CHECK=1

ARG APT_MIRROR=mirrors.aliyun.com
ARG PIP_INDEX=https://mirrors.aliyun.com/pypi/simple/

RUN if [ -n "${APT_MIRROR}" ]; then \
  sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
  sed -i "s|http[s]*://deb.debian.org|http://${APT_MIRROR}|g" /etc/apt/sources.list 2>/dev/null || \
  sed -i "s|http[s]*://[^/]*/debian|http://${APT_MIRROR}/debian|g" /etc/apt/sources.list 2>/dev/null || true; \
  fi \
  && apt-get update && apt-get install -y --no-install-recommends \
  git \
  build-essential \
  curl \
  jq \
  ca-certificates \
  nodejs \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=harness-deps /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=harness-deps /usr/local/bin/opencode /usr/local/bin/
COPY --from=harness-deps /usr/local/bin/pi /usr/local/bin/

RUN opencode --version && pi --version

COPY requirements.txt .
RUN pip install --no-cache-dir -i ${PIP_INDEX} -r requirements.txt

COPY config/ ./config/
COPY scripts/ ./scripts/
COPY data/ ./data/

RUN mkdir -p /app/results

ENV PYTHONPATH=/app
ENV HARVEST_CONFIG_PATH=/app/config/default.yaml

CMD ["python", "-m", "scripts.run_test", "--help"]
