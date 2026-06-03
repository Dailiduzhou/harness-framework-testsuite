"""Base harness adapter interface — CLI-flag or stdin-driven invocation.

Each harness is invoked as a subprocess.  The prompt is delivered via one of
two channels, controlled by the ``args`` template in config:

* **CLI-flag mode**   — template contains ``{prompt}`` (e.g. ``--prompt "{prompt}"``)
* **stdin mode**      — template does NOT contain ``{prompt}``; the prompt is
  piped to subprocess stdin.

Supported template placeholders: ``{model}`` ``{provider}`` ``{max_tokens}``
``{temperature}`` ``{workspace}`` ``{repo}`` ``{output}``.
"""

from __future__ import annotations

import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path

from scripts.metrics import TaskMetrics


class HarnessAdapter(ABC):
    def __init__(self, name: str, config: dict) -> None:
        self.name = name
        self.hconfig = config.get("harness", {}).get(name, {})
        self.llm_config = config.get("llm", {})

    def _template_ctx(self, repo_path: Path, output_file: Path) -> dict[str, str]:
        return {
            "model": self.llm_config.get("model", "gpt-4o"),
            "provider": self.llm_config.get("provider", "openai"),
            "max_tokens": str(self.llm_config.get("max_tokens", 4096)),
            "temperature": str(self.llm_config.get("temperature", 0.0)),
            "workspace": str(repo_path),
            "repo": str(repo_path),
            "output": str(output_file),
            "prompt": "{prompt}",  # self-reference — survives first format, resolved in run()
        }

    def _resolve_args(
        self, repo_path: Path, output_file: Path
    ) -> tuple[list[str], bool]:
        """Resolve the arguments list from config or default.

        Returns (args, prompt_consumed).  ``prompt_consumed`` is True when
        the template already includes ``{prompt}``, meaning the caller should
        NOT pipe the prompt on stdin.
        """
        raw: list[str] | None = self.hconfig.get("args")
        if raw is None:
            return self._default_args(repo_path, output_file), False

        prompt_consumed = any("{prompt}" in a for a in raw)

        ctx = self._template_ctx(repo_path, output_file)
        resolved = [a.format(**ctx) for a in raw]
        return resolved, prompt_consumed

    def _default_args(self, repo_path: Path, output_file: Path) -> list[str]:
        """Subclass overrides this when config has no args template."""
        return []

    def command(self, repo_path: Path, output_file: Path) -> list[str]:
        """Full argv including entrypoint (before prompt injection)."""
        entries, _ = self._resolve_args(repo_path, output_file)
        return [self.hconfig.get("entrypoint", self.name)] + entries

    @abstractmethod
    def parse_output(self, raw: str) -> dict:
        """Extract structured metrics from stdout+stderr."""
        ...

    def run(
        self, instance_id: str, prompt: str, repo_path: Path, work_dir: Path
    ) -> TaskMetrics:
        metrics = TaskMetrics(
            instance_id=instance_id,
            harness=self.name,
            dataset="",
        )
        metrics.start_time = time.time()

        output_file = work_dir / f"output_{instance_id}.txt"

        args, prompt_consumed = self._resolve_args(repo_path, output_file)
        cmd = [self.hconfig.get("entrypoint", self.name)] + args

        # Inject prompt into the args if template consumed it via --prompt
        if prompt_consumed:
            resolved = [a.format(prompt=prompt) for a in args]
            cmd = [self.hconfig.get("entrypoint", self.name)] + resolved

        try:
            cwd_mode = self.hconfig.get("cwd", "work_dir")
            cwd = repo_path if cwd_mode == "repo" else work_dir

            result = subprocess.run(
                cmd,
                input=None if prompt_consumed else prompt,
                capture_output=True,
                text=True,
                timeout=self.hconfig.get("timeout_per_task", 600),
                cwd=str(cwd),
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
            metrics.error = (
                f"Timeout after {self.hconfig.get('timeout_per_task', 600)}s"
            )
        except Exception as exc:
            metrics.error = str(exc)

        metrics.end_time = time.time()
        metrics.execution_time_s = metrics.end_time - metrics.start_time

        return metrics
