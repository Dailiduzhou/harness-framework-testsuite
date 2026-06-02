"""Base dataset loader interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class TaskInstance:
    """Single benchmark task instance."""

    instance_id: str
    repo: str
    prompt: str
    base_commit: str = ""
    test_patch: str = ""
    metadata: dict | None = None


class DatasetLoader(ABC):
    """Abstract dataset loader for benchmark data."""

    def __init__(self, config: dict) -> None:
        self.config = config
        self.max_instances = config.get("max_instances", 0)

    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def load(self, data_path: str) -> list[TaskInstance]:
        ...

    def _limit(self, instances: list[TaskInstance]) -> list[TaskInstance]:
        if self.max_instances and self.max_instances > 0:
            return instances[: self.max_instances]
        return instances
