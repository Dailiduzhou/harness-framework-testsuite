"""Pi harness adapter — stdin-driven invocation."""

import json as _json
from pathlib import Path

from scripts.harness.base import HarnessAdapter


class PiAdapter(HarnessAdapter):
    def __init__(self, config: dict) -> None:
        super().__init__("pi", config)

    def _default_args(self, repo_path: Path, output_file: Path) -> list[str]:
        return [
            "--model", self.llm_config.get("model", "gpt-4o"),
            "--max-tokens", str(self.llm_config.get("max_tokens", 4096)),
            "--temperature", str(self.llm_config.get("temperature", 0.0)),
            "--output-file", str(output_file),
            "--repo", str(repo_path),
        ]

    def parse_output(self, raw: str) -> dict:
        token_count = 0
        prompt_tokens = 0
        completion_tokens = 0
        api_calls = 0
        build_passed = False
        passed: bool | None = None
        last_usage: dict = {}

        for line in raw.split("\n"):
            line = line.strip()
            if not line:
                continue

            # JSON-format lines from --mode json
            if line.startswith("{"):
                try:
                    ev = _json.loads(line)
                except (_json.JSONDecodeError, ValueError):
                    pass
                else:
                    etype = ev.get("type", "")
                    if etype in ("message_start",):
                        api_calls += 1
                    if etype in ("message_end", "turn_end"):
                        msg = ev.get("message", {})
                        usage = msg.get("usage", {})
                        if usage:
                            last_usage = usage
                    continue

            # Text-format fallback
            if line.startswith("tokens:"):
                parts = line.split()
                for p in parts:
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

            if "build: success" in line.lower() or "build: ok" in line.lower():
                build_passed = True

            if "status: pass" in line.lower() or "verdict: pass" in line.lower():
                passed = True

        if last_usage:
            token_count = int(last_usage.get("totalTokens", 0))
            prompt_tokens = int(last_usage.get("input", 0))
            completion_tokens = int(last_usage.get("output", 0))

        result: dict = {
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
