"""Load task directories. ``answer.txt`` is written next to ``task.json``."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Task:
    task_id: str
    task_type: str
    instruction: str
    reward: int
    check: str
    directory: Path

    @property
    def work_dir(self) -> Path:
        workspace = self.directory / "workspace"
        return workspace if workspace.is_dir() else self.directory

    @property
    def answer_path(self) -> Path:
        return self.directory / "answer.txt"

    def write_answer(self, answer: str) -> None:
        text = answer.strip() + "\n"
        temporary = self.answer_path.with_suffix(".txt.tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(self.answer_path)

    def clear_answer(self) -> None:
        if self.answer_path.exists():
            self.answer_path.unlink()


def load_tasks(tasks_dir: Path) -> list[Task]:
    root = tasks_dir.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"tasks directory does not exist: {root}")

    folders = [root] if (root / "task.json").is_file() else sorted(p for p in root.iterdir() if p.is_dir())
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
                reward=int(spec.get("reward") or 0),
                check=str(spec.get("check") or ""),
                directory=folder,
            )
        )
    return tasks
