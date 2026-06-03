"""Evaluator interface — determines pass/fail of a harness agent's output.

Evaluators are called after the harness agent finishes.  They receive the
agent's output, the original task instance, and the working directory
(which may contain the agent's modifications).  An evaluator may override
metrics.passed, metrics.resolved, and metrics.build_passed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from scripts.metrics import TaskMetrics


class Evaluator(ABC):
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    @abstractmethod
    def evaluate(
        self,
        metrics: TaskMetrics,
        repo_path: Path,
        work_dir: Path,
    ) -> TaskMetrics:
        ...


_EVALUATORS: dict[str, type[Evaluator]] = {}


def register_evaluator(name: str):
    def dec(cls: type[Evaluator]):
        _EVALUATORS[name] = cls
        return cls

    return dec


def get_evaluator(name: str, config: dict[str, Any]) -> Evaluator:
    cls = _EVALUATORS.get(name)
    if cls is None:
        available = list(_EVALUATORS.keys())
        raise ValueError(
            f"Unknown evaluator: {name}. Available: {available}"
        )
    return cls(config)
