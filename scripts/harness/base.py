"""Base harness adapter interface."""

from __future__ import annotations

import subprocess
import tempfile
import time
from abc import ABC, abstractmethod
from pathlib import Path

from scripts.metrics import TaskMetrics


class HarnessAdapter(ABC):
    """Abstract harness adapter — wrap OpenCode / Pi in non-interactive mode."""

    def __init__(self, name: str, config: dict) -> None:
        self.name = name
        self.hconfig = config.get("harness", {}).get(name, {})
        self.llm_config = config.get("llm", {})

    @abstractmethod
    def prepare_command(self, prompt: str, repo_path: Path, output_file: Path) -> list[str]:
        """Build the non-interactive CLI invocation."""
        ...

    @abstractmethod
    def parse_output(self, raw: str) -> dict:
        """Extract structured data from harness stdout."""
        ...

    def run(self, instance_id: str, prompt: str, repo_path: Path, work_dir: Path) -> TaskMetrics:
        metrics = TaskMetrics(
            instance_id=instance_id,
            harness=self.name,
            dataset="",
        )
        metrics.start_time = time.time()

        output_file = work_dir / f"output_{instance_id}.txt"

        cmd = self.prepare_command(prompt, repo_path, output_file)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.hconfig.get("timeout_per_task", 600),
                cwd=str(work_dir),
                env={
                    **__import__("os").environ,
                    "LLM_API_KEY": self.llm_config.get("api_key", ""),
                    "LLM_API_BASE": self.llm_config.get("api_base", ""),
                    "LLM_MODEL": self.llm_config.get("model", ""),
                },
            )

            metrics.raw_output = result.stdout + "\n" + result.stderr
            parsed = self.parse_output(metrics.raw_output)

            metrics.passed = parsed.get("passed", result.returncode == 0)
            metrics.resolved = parsed.get("resolved", False)
            metrics.token_count = parsed.get("token_count", 0)
            metrics.prompt_tokens = parsed.get("prompt_tokens", 0)
            metrics.completion_tokens = parsed.get("completion_tokens", 0)
            metrics.api_calls = parsed.get("api_calls", 0)
            metrics.build_passed = parsed.get("build_passed", False)

            if not metrics.passed and result.returncode != 0:
                metrics.error = result.stderr[:500]

        except subprocess.TimeoutExpired:
            metrics.error = f"Timeout after {self.hconfig.get('timeout_per_task', 600)}s"
        except Exception as exc:
            metrics.error = str(exc)

        metrics.end_time = time.time()
        metrics.execution_time_s = metrics.end_time - metrics.start_time

        return metrics
