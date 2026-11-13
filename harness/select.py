"""Queue price and one-step knapsack.

The price is input/10 plus a per-type output price. The output price starts
from a constant and moves after every live call of that type. max_tokens is
not part of the price.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from harness.config import BUDGET_MARGIN, MODEL_BY_TYPE, MODEL_REASON, OUTPUT_CAP, OUTPUT_PRIOR
from harness.tasks import Task

_TEXT = {".csv", ".md", ".txt", ".py"}


@dataclass
class Candidate:
    task: Task
    estimate: int
    model: str
    note: str
    max_tokens: int = 4096
    prompt: str = ""


@dataclass
class Prices:
    output: dict[str, int] = field(default_factory=lambda: dict(OUTPUT_PRIOR))

    def observe(self, task_type: str, output_cost: int) -> None:
        old = self.output.get(task_type, output_cost)
        self.output[task_type] = max(1, round(0.5 * output_cost + 0.5 * old))


def prompt_tokens(text: str) -> int:
    return max(1, (len(text) + 2) // 3)


def _files(task: Task) -> str:
    work = task.work_dir
    if not work.is_dir():
        return ""
    chunks: list[str] = []
    for path in sorted(p for p in work.rglob("*") if p.is_file() and p.suffix.lower() in _TEXT):
        if path.name == "task.json":
            continue
        body = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(work).as_posix()
        chunks.append(f"===== {rel} =====\n{body}")
    return "\n\n".join(chunks)


def user_prompt(task: Task) -> str:
    if task.task_type == "coding":
        library = task.work_dir / "mylib.py"
        original = library.read_text(encoding="utf-8", errors="replace") if library.is_file() else ""
        tests = sorted(task.work_dir.glob("test_*.py"))
        test_text = tests[0].read_text(encoding="utf-8", errors="replace") if tests else ""
        return (
            f"{task.instruction}\n\nmylib.py:\n```python\n{original}\n```\n\n"
            f"test:\n```python\n{test_text}\n```"
        )
    files = _files(task)
    if not files:
        return task.instruction
    return f"{task.instruction}\n\n{files}"


def output_cap(task: Task) -> int:
    return OUTPUT_CAP.get(task.task_type, 4096)


def model_for(task: Task) -> str:
    return MODEL_BY_TYPE.get(task.task_type, MODEL_REASON)


def price(task: Task, prices: Prices, system: str) -> int:
    incoming = prompt_tokens(system + "\n" + user_prompt(task))
    outgoing = prices.output.get(task.task_type, 200)
    return max(1, (incoming + 9) // 10 + outgoing)


def candidate_for(task: Task, note: str, prices: Prices | None = None, system: str = "") -> Candidate:
    book = prices or Prices()
    return Candidate(
        task=task,
        estimate=price(task, book, system),
        model=model_for(task),
        note=note,
        max_tokens=output_cap(task),
        prompt=user_prompt(task),
    )


def reprice(candidates: list[Candidate], prices: Prices, system_for) -> None:
    for item in candidates:
        item.estimate = price(item.task, prices, system_for(item.task))
        item.max_tokens = output_cap(item.task)


def next_task(candidates: list[Candidate], remaining: int, margin: float = BUDGET_MARGIN) -> Candidate | None:
    cap = int(remaining * margin)
    fitting = [item for item in candidates if item.estimate <= cap]
    if not fitting:
        return None
    return max(fitting, key=lambda item: (item.task.reward / item.estimate, item.task.reward))
