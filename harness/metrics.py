"""One record per task, then a readable total at the end of the run."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class TaskMetric:
    task_id: str
    task_type: str
    status: str
    reward: int = 0
    reward_gained: int = 0
    cost: int = 0
    estimate: int = 0
    model: str = ""
    attempts: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    elapsed_ms: int = 0
    answer: str = ""
    note: str = ""


@dataclass
class RunMetrics:
    task_count: int
    budget_limit: int
    records: list[TaskMetric] = field(default_factory=list)

    def add(self, record: TaskMetric) -> None:
        self.records.append(record)
        self._write(record)

    def finish(self, spent: int) -> None:
        by_status: dict[str, int] = {}
        by_type: dict[str, list[int]] = {}
        for item in self.records:
            by_status[item.status] = by_status.get(item.status, 0) + 1
            bucket = by_type.setdefault(item.task_type, [0, 0, 0])
            bucket[0] += item.reward_gained
            bucket[1] += item.cost
            bucket[2] += 1
        input_tokens = sum(item.input_tokens for item in self.records)
        output_tokens = sum(item.output_tokens for item in self.records)
        reasoning_tokens = sum(item.reasoning_tokens for item in self.records)
        reward = sum(item.reward_gained for item in self.records)
        missed = sum(item.reward - item.reward_gained for item in self.records)
        lines = [
            "--- итог ---",
            f"задач: {self.task_count}",
            "по статусам: " + ", ".join(f"{name}={count}" for name, count in sorted(by_status.items())),
            f"баллы: {reward}",
            f"бюджет: {self.budget_limit}, потрачено: {spent}, осталось: {self.budget_limit - spent}",
            f"токены модели: вход={input_tokens}, выход={output_tokens}, рассуждения={reasoning_tokens}",
        ]
        for task_type, (type_reward, type_cost, count) in sorted(by_type.items()):
            lines.append(f"  {task_type}: задач={count}, баллы={type_reward}, токены={type_cost}")
        if missed:
            lines.append(f"баллы несданных задач: {missed}")
        print("\n".join(lines), flush=True)

    def _write(self, record: TaskMetric) -> None:
        raw = os.environ.get("OUT", "").strip()
        if not raw:
            return
        try:
            path = Path(raw)
            if raw.endswith(("/", "\\")) or path.is_dir():
                path.mkdir(parents=True, exist_ok=True)
                path = path / "solutions.jsonl"
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
        except OSError:
            return
