"""Self-report evaluator — trusts agent's own parse_output result.

This is the default evaluator.  It returns metrics unchanged — whatever
the harness adapter reported via parse_output is accepted at face value.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.evaluators.base import Evaluator, register_evaluator
from scripts.metrics import TaskMetrics


@register_evaluator("self_report")
class SelfReportEvaluator(Evaluator):
    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)

    def evaluate(
        self,
        metrics: TaskMetrics,
        repo_path: Path,
        work_dir: Path,
    ) -> TaskMetrics:
        return metrics
