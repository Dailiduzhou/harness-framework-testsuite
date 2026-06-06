"""Sandbox evaluator — run tests inside a Docker container for ground-truth verification.

Supports two modes:
  * **container** — full Docker sandbox with git clone, patch application, and pytest
  * **command**  — runs a configurable shell command in the agent's workspace

For SWE-Bench evaluation, the test_patch contains the official test cases.
This evaluator applies the patch and runs the test suite in an isolated
environment to produce an objective pass/fail verdict.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from scripts.evaluators.base import Evaluator, register_evaluator
from scripts.metrics import TaskMetrics

logger = logging.getLogger(__name__)


@register_evaluator("sandbox")
class SandboxEvaluator(Evaluator):
    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        ecfg = config.get("evaluation", {})
        self.mode = ecfg.get("mode", "command")
        self.command = ecfg.get("command")
        self.timeout = ecfg.get("timeout", 600)
        self.image = ecfg.get("sandbox_image", "python:3.11-slim")

    def evaluate(
        self,
        metrics: TaskMetrics,
        repo_path: Path,
        work_dir: Path,
    ) -> TaskMetrics:
        if self.mode == "command" and self.command:
            return self._eval_command(metrics, repo_path, work_dir)
        if self.mode == "container":
            return self._eval_container(metrics, repo_path, work_dir)
        return metrics

    def _eval_command(
        self,
        metrics: TaskMetrics,
        repo_path: Path,
        work_dir: Path,
    ) -> TaskMetrics:
        logger.info("Running evaluation command in sandbox...")
        try:
            result = subprocess.run(
                self.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(repo_path),
                env={**os.environ, **{k: str(v) for k, v in os.environ.items()}},
            )
            ok = result.returncode == 0
            if not metrics.passed:
                ok = False   # adapter already failed — preserve that verdict

            if not ok:
                metrics.passed = False
                metrics.resolved = False
                metrics.build_passed = False
                msg = result.stderr[:500] if result.stderr else "evaluation failed"
                if metrics.error:
                    metrics.error += "\n[eval] " + msg[:300]
                else:
                    metrics.error = msg
            else:
                output = (result.stdout + "\n" + result.stderr).strip()
                if output and not metrics.raw_output.endswith(output):
                    metrics.raw_output += f"\n\n[eval] {output}"
        except subprocess.TimeoutExpired:
            metrics.passed = False
            metrics.resolved = False
            metrics.error = f"Evaluation timeout after {self.timeout}s"
        except Exception as exc:
            metrics.passed = False
            metrics.resolved = False
            metrics.error = f"Evaluation error: {exc}"

        return metrics

    def _eval_container(
        self,
        metrics: TaskMetrics,
        repo_path: Path,
        work_dir: Path,
    ) -> TaskMetrics:
        logger.info("Running container-based evaluation...")
        repo_abs = repo_path.resolve()
        work_abs = work_dir.resolve()

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".sh",
            prefix="eval_",
            delete=False,
        ) as sf:
            eval_script = self._build_eval_script(str(repo_abs))
            sf.write(eval_script)
            eval_script_path = sf.name

        try:
            docker_cmd = [
                "docker", "run", "--rm",
                "--network", "none",
                "-v", f"{repo_abs}:/app/repo:ro",
                "-v", f"{work_abs}:/app/work:ro",
                "-v", f"{eval_script_path}:/app/eval.sh:ro",
                "-w", "/app/repo",
                self.image,
                "bash", "/app/eval.sh",
            ]

            start_ts = time.time()
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            elapsed = time.time() - start_ts

            ok = result.returncode == 0
            metrics.passed = ok
            metrics.resolved = ok
            metrics.build_passed = ok

            output = (result.stdout + "\n" + result.stderr).strip()
            if output:
                metrics.raw_output += f"\n\n[sandbox-eval ({elapsed:.1f}s)] {output}"
            if not ok:
                metrics.error = result.stderr[:500]

        except subprocess.TimeoutExpired:
            metrics.passed = False
            metrics.resolved = False
            metrics.error = f"Sandbox evaluation timeout after {self.timeout}s"
        except Exception as exc:
            metrics.passed = False
            metrics.resolved = False
            metrics.error = f"Sandbox eval error: {exc}"
        finally:
            Path(eval_script_path).unlink(missing_ok=True)

        return metrics

    def _build_eval_script(self, repo_path: str) -> str:
        return f"""#!/bin/bash
set -eo pipefail

pip install --quiet -r /app/repo/requirements.txt 2>/dev/null || true
pip install pytest --quiet 2>/dev/null || true

cd /app/repo

echo "Running tests..."
python -m pytest -x --tb=short 2>&1
"""
