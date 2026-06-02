"""OpenCode harness adapter — non-interactive CLI invocation."""

from pathlib import Path


class OpenCodeAdapter:
    def __init__(self, config: dict) -> None:
        self.name = "opencode"
        self.hconfig = config.get("harness", {}).get("opencode", {})
        self.llm_config = config.get("llm", {})

    def prepare_command(
        self, prompt: str, repo_path: Path, output_file: Path
    ) -> list[str]:
        return [
            self.hconfig.get("entrypoint", "opencode"),
            "--non-interactive",
            "--model",
            self.llm_config.get("model", "gpt-4o"),
            "--max-tokens",
            str(self.llm_config.get("max_tokens", 4096)),
            "--temperature",
            str(self.llm_config.get("temperature", 0.0)),
            "--output",
            str(output_file),
            "--workspace",
            str(repo_path),
            prompt,
        ]

    def parse_output(self, raw: str) -> dict:
        token_count = 0
        prompt_tokens = 0
        completion_tokens = 0
        api_calls = 0
        build_passed = False
        passed = False

        for line in raw.split("\n"):
            line = line.strip()

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

            if "build: success" in line.lower() or "build: passed" in line.lower():
                build_passed = True

            if "result: pass" in line.lower() or "all tests passed" in line.lower():
                passed = True

        return {
            "token_count": token_count,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "api_calls": api_calls,
            "build_passed": build_passed,
            "passed": passed,
            "resolved": passed,
        }
