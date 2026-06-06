"""OpenCode harness adapter — stdin-driven invocation."""

import json as _json
from pathlib import Path

from scripts.harness.base import HarnessAdapter

ACTION_INDICATORS = ("> ", "\u2715 ", "\u2192 ", "\u2717 ", "! ")


class OpenCodeAdapter(HarnessAdapter):
    def __init__(self, config: dict) -> None:
        super().__init__("opencode", config)

    def _default_args(self, repo_path: Path, output_file: Path) -> list[str]:
        return [
            "--model", self.llm_config.get("model", "gpt-4o"),
            "--max-tokens", str(self.llm_config.get("max_tokens", 4096)),
            "--temperature", str(self.llm_config.get("temperature", 0.0)),
            "--output", str(output_file),
            "--workspace", str(repo_path),
        ]

    def parse_output(self, raw: str) -> dict:
        token_count = 0
        prompt_tokens = 0
        completion_tokens = 0
        api_calls = 0
        build_passed = False
        passed: bool | None = None
        has_error = False

        for line in raw.split("\n"):
            line = line.strip()
            if not line:
                continue

            # JSON-format lines from --format json
            if line.startswith("{"):
                try:
                    ev = _json.loads(line)
                except (_json.JSONDecodeError, ValueError):
                    pass
                else:
                    etype = ev.get("type", "")
                    if etype in ("step_start", "step_finish", "tool_use", "text"):
                        api_calls += 1
                    if etype == "step_finish":
                        toks = ev.get("part", {}).get("tokens", {})
                        if toks:
                            prompt_tokens += int(toks.get("input", 0))
                            completion_tokens += int(toks.get("output", 0))
                            token_count += int(toks.get("total", 0))
                    continue

            # Text-format fallback
            if line.startswith("tokens:"):
                for p in line.split():
                    if p.startswith("total="):
                        token_count = int(p.split("=")[1])
                    elif p.startswith("prompt="):
                        prompt_tokens = int(p.split("=")[1])
                    elif p.startswith("completion="):
                        completion_tokens = int(p.split("=")[1])

            if line.startswith("api_calls:"):
                parts = line.split()
                if len(parts) > 1:
                    try:
                        api_calls = int(parts[1])
                    except ValueError:
                        pass

            if "build: success" in line.lower() or "build: passed" in line.lower():
                build_passed = True

            if "result: pass" in line.lower() or "all tests passed" in line.lower():
                passed = True

            for pre in ACTION_INDICATORS:
                if pre in line or line.startswith(pre):
                    api_calls += 1
                    break

            if "Error:" in line or "error:" in line.lower():
                has_error = True

        result = {
            "token_count": token_count,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "api_calls": api_calls,
            "build_passed": build_passed,
            "resolved": bool(passed),
        }

        if passed is not None:
            result["passed"] = passed

        return result
