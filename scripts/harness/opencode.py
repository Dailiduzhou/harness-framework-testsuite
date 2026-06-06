"""OpenCode harness adapter — stdin-driven invocation.

Prompt is piped via stdin.  CLI args are taken from ``config.yaml``
(harness.opencode.args) or the default below.
"""

from pathlib import Path

from scripts.harness.base import HarnessAdapter

# Tool action indicators opencode emits during a run.
# Each line starting with one of these counts as an API interaction.
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
        passed = False
        has_output = False
        has_error = False

        for line in raw.split("\n"):
            line_stripped = line.strip()

            if line_stripped:
                has_output = True

            if line_stripped.startswith("tokens:"):
                parts = line_stripped.split()
                for p in parts:
                    if p.startswith("total="):
                        token_count = int(p.split("=")[1])
                    elif p.startswith("prompt="):
                        prompt_tokens = int(p.split("=")[1])
                    elif p.startswith("completion="):
                        completion_tokens = int(p.split("=")[1])

            if line_stripped.startswith("api_calls:"):
                parts = line_stripped.split()
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
                if pre in line_stripped or line_stripped.startswith(pre):
                    api_calls += 1
                    break

            if "Error:" in line_stripped or "error:" in line_stripped.lower():
                has_error = True

        # Fallback: if opencode produced output without explicit pass/fail markers,
        # treat it as completed (pass/fail determined by exit code in base.py).
        result: dict = {
            "token_count": token_count,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "api_calls": api_calls,
            "build_passed": build_passed,
            "resolved": passed,
        }

        if passed or (has_output and not has_error):
            pass
        else:
            result["passed"] = False
            result["resolved"] = False

        # Only override passed if we have a definitive signal
        if has_error:
            result["passed"] = False
            result["resolved"] = False

        return result
