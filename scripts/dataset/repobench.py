"""RepoBench dataset loader."""

import json
from pathlib import Path

from scripts.dataset.base import DatasetLoader, TaskInstance


class RepoBenchLoader(DatasetLoader):
    def name(self) -> str:
        return "repobench"

    def load(self, data_path: str) -> list[TaskInstance]:
        path = Path(data_path)
        instances: list[TaskInstance] = []

        if not path.exists():
            return instances

        json_files = list(path.glob("*.json")) + list(path.glob("*.jsonl"))
        for jf in json_files:
            with open(jf) as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    f.seek(0)
                    data = [json.loads(line) for line in f if line.strip()]

            entries = data if isinstance(data, list) else [data]
            for entry in entries:
                instances.append(
                    TaskInstance(
                        instance_id=entry.get("instance_id", entry.get("id", "")),
                        repo=entry.get("repo", entry.get("repository", "")),
                        prompt=entry.get("prompt", entry.get("task_description", "")),
                        base_commit=entry.get("base_commit", ""),
                        test_patch=entry.get("test_patch", ""),
                        metadata=entry.get("metadata"),
                    )
                )

        return self._limit(instances)
