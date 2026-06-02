"""Configuration loader — resolves YAML config with env var interpolation."""

import os
import re
from pathlib import Path
from typing import Any

import yaml


_ENV_RE = re.compile(r"\$\{(\w+)(?::-(.*?))?\}")


def _resolve_env(value: str) -> str:
    def _repl(m: re.Match) -> str:
        var = m.group(1)
        default = m.group(2)
        return os.environ.get(var, default or "")

    return _ENV_RE.sub(_repl, value)


def _walk(obj: Any) -> Any:
    if isinstance(obj, str):
        return _resolve_env(obj)
    if isinstance(obj, dict):
        return {k: _walk(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk(v) for v in obj]
    return obj


def load_config(path: str | Path | None = None) -> dict:
    if path is None:
        path = os.environ.get("HARVEST_CONFIG_PATH", "config/default.yaml")

    with open(path) as f:
        raw = yaml.safe_load(f)

    return _walk(raw)
