"""Metrics data models for test results."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskMetrics:
    """Per-task execution metrics."""

    instance_id: str
    harness: str
    dataset: str
    repo: str = ""

    # Core metrics
    passed: bool = False
    resolved: bool = False

    # Resource metrics
    token_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    api_calls: int = 0
    execution_time_s: float = 0.0
    build_passed: bool = False

    # Timing breakdown
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0

    # Raw data
    raw_output: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "harness": self.harness,
            "dataset": self.dataset,
            "repo": self.repo,
            "passed": self.passed,
            "resolved": self.resolved,
            "token_count": self.token_count,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "api_calls": self.api_calls,
            "execution_time_s": round(self.execution_time_s, 3),
            "build_passed": self.build_passed,
            "error": self.error,
        }


@dataclass
class SuiteResult:
    """Aggregate result for a full test suite run."""

    harness: str
    dataset: str
    total: int = 0
    passed: int = 0
    resolved: int = 0
    build_errors: int = 0
    errors: int = 0
    total_tokens: int = 0
    total_api_calls: int = 0
    total_time_s: float = 0.0
    tasks: list[TaskMetrics] = field(default_factory=list)

    @property
    def pass_at_1(self) -> float:
        if self.total == 0:
            return 0.0
        return self.passed / self.total

    @property
    def resolve_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.resolved / self.total

    @property
    def build_rate(self) -> float:
        total_non_error = self.total - self.errors
        if total_non_error == 0:
            return 0.0
        return (total_non_error - self.build_errors) / total_non_error

    @property
    def avg_tokens_per_task(self) -> float:
        if self.total == 0:
            return 0.0
        return self.total_tokens / self.total

    @property
    def avg_api_calls_per_task(self) -> float:
        if self.total == 0:
            return 0.0
        return self.total_api_calls / self.total

    @property
    def avg_time_per_task(self) -> float:
        if self.total == 0:
            return 0.0
        return self.total_time_s / self.total

    def summary(self) -> dict[str, Any]:
        return {
            "harness": self.harness,
            "dataset": self.dataset,
            "total": self.total,
            "passed": self.passed,
            "resolved": self.resolved,
            "build_errors": self.build_errors,
            "errors": self.errors,
            "pass@1": round(self.pass_at_1, 4),
            "resolve_rate": round(self.resolve_rate, 4),
            "build_rate": round(self.build_rate, 4),
            "total_tokens": self.total_tokens,
            "total_api_calls": self.total_api_calls,
            "total_time_s": round(self.total_time_s, 1),
            "avg_tokens_per_task": round(self.avg_tokens_per_task, 1),
            "avg_api_calls_per_task": round(self.avg_api_calls_per_task, 1),
            "avg_time_per_task": round(self.avg_time_per_task, 1),
        }
