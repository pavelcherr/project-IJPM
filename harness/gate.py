"""Feasibility gate. Does not read check and does not solve the task."""

from __future__ import annotations

import sys
from pathlib import Path

from harness.tasks import Task

_FEASIBILITY_ROOT = Path(__file__).resolve().parents[1] / "feasibility"
if str(_FEASIBILITY_ROOT) not in sys.path:
    sys.path.insert(0, str(_FEASIBILITY_ROOT))


def task_is_solvable(task: Task) -> tuple[bool, str]:
    try:
        from feasibility.check import check_task
    except Exception as exc:
        return True, f"проверка недоступна: {exc}"
    verdict = check_task(task)
    return verdict.feasible, verdict.reason
