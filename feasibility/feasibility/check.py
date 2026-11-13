"""Dispatch by task_type. Unknown wording stays feasible and goes to the model."""

from __future__ import annotations

from dataclasses import dataclass

from feasibility.types import data_analysis, coding, math, search
from feasibility.task import Task


@dataclass(frozen=True)
class Verdict:
    task_id: str
    task_type: str
    feasible: bool
    reason: str


def check_task(task: Task) -> Verdict:
    kind = task.task_type
    if kind == "data_analysis":
        feasible, reason = data_analysis.can_answer(task.instruction, task.work_dir)
    elif kind == "search":
        feasible, reason = search.can_answer(task.instruction, task.work_dir)
    elif kind == "math":
        feasible, reason = math.can_answer(task.instruction)
    elif kind == "coding":
        feasible, reason = coding.can_answer(task.instruction, task.work_dir)
    else:
        feasible, reason = True, "неизвестный тип: не пропускаем, отдаём модели"
    return Verdict(task.task_id, kind, feasible, reason)


def select_solvable(tasks: list[Task]) -> list[Task]:
    return [task for task in tasks if check_task(task).feasible]
