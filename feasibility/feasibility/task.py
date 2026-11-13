"""Read task folders. The answer is not loaded: it must not affect the verdict."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Task:
    task_id: str
    task_type: str
    instruction: str
    directory: Path

    @property
    def work_dir(self) -> Path:
        workspace = self.directory / "workspace"
        return workspace if workspace.is_dir() else self.directory


def load_tasks(tasks_dir: Path) -> list[Task]:
    root = tasks_dir.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"нет папки задач: {root}")

    folders = [root] if (root / "task.json").is_file() else sorted(path for path in root.iterdir() if path.is_dir())
    tasks: list[Task] = []
    for folder in folders:
        spec_path = folder / "task.json"
        if not spec_path.is_file():
            continue
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        tasks.append(
            Task(
                task_id=str(spec.get("task_id") or folder.name),
                task_type=str(spec.get("task_type") or "unknown"),
                instruction=str(spec.get("instruction") or ""),
                directory=folder,
            )
        )
    return tasks
