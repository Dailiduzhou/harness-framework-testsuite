"""Pi harness adapter — non-interactive CLI invocation."""

from pathlib import Path


class PiAdapter:
    def __init__(self, config: dict) -> None:
        self.name = "pi"
        self.hconfig = config.get("harness", {}).get("pi", {})
        self.llm_config = config.get("llm", {})

    def prepare_command(self, prompt: str, repo_path: Path, output_file: Path) -> list[str]:
        return [
            self.hconfig.get("entrypoint", "pi"),
            "--batch",
            "--model", self.llm_config.get("model", "gpt-4o"),
            "--max-tokens", str(self.llm_config.get("max_tokens", 4096)),
            "--temperature", str(self.llm_config.get("temperature", 0.0)),
            "--output-file", str(output_file),
            "--repo", str(repo_path),
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

            if "token_usage" in line.lower():
                try:
                    import json

                    data = json.loads(line)
                    usage = data.get("token_usage", data)
                    token_count = usage.get("total", 0)
                    prompt_tokens = usage.get("prompt", 0)
                    completion_tokens = usage.get("completion", 0)
                except (json.JSONDecodeError, KeyError):
                    pass

            if "api_calls" in line.lower():
                parts = line.split(":")
                if len(parts) > 1:
                    try:
                        api_calls = int(parts[1].strip())
                    except ValueError:
                        pass

            if "build_status: success" in line.lower() or "build: ok" in line.lower():
                build_passed = True

            if "status: pass" in line.lower() or "verdict: pass" in line.lower():
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
