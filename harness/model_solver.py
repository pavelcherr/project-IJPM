"""One-shot model fallback. Coding gets at most two attempts, then the file is restored."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from harness.budget import Usage
from harness.config import MODEL_CODE, MODEL_CODE_STRONG
from harness.llm_client import LlmClient, Slot
from harness.sandbox import run_tests
from harness.select import user_prompt
from harness.tasks import Task

_SHORT_SYSTEM = (
    "You solve one contest task. Reply with ONLY the final answer: "
    "a number or a short string. No explanation, no units, no punctuation."
)
_CODE_SYSTEM = (
    "You repair mylib.py so that test_mylib.py passes.\n"
    "The checker runs those tests and then calls the same functions with other inputs. "
    "Fix the behaviour. Do not special-case the examples written in the test.\n"
    "Comments in the file may be in Russian.\n"
    "Return the complete corrected source of mylib.py and nothing else.\n"
    "Keep every function that already exists. Do not delete functions. Do not edit the tests.\n"
    "Do not write DONE. Do not explain.\n"
    "If no change to mylib.py can make the tests pass, return exactly UNSOLVABLE."
)


def system_prompt(task: Task) -> str:
    return _CODE_SYSTEM if task.task_type == "coding" else _SHORT_SYSTEM


_NARRATION = re.compile(
    r"^(let me|let's|i need|i'll|i will|we need|the user|i should|verify|checking)\b",
    re.IGNORECASE,
)


_ECHO = re.compile(r"^echo\s+(.+?)\s*>\s*answer\.txt$", re.IGNORECASE)


def _line_value(line: str, check: str) -> str:
    line = line.strip().strip("\"'`")
    if line.endswith("."):
        line = line[:-1]
    echoed = _ECHO.match(line)
    if echoed:
        line = echoed.group(1).strip().strip("\"'`")
    if not line or line.startswith("```") or _NARRATION.match(line):
        return ""
    if check == "exact_int":
        numbers = re.findall(r"-?\d+", line)
        return numbers[-1] if numbers else ""
    return line


def _answer_line(text: str, check: str) -> str:
    for line in reversed(text.splitlines()):
        answer = _line_value(line, check)
        if answer:
            return answer
    return ""


def _python_source(text: str) -> str:
    match = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL)
    body = match.group(1) if match else text
    return body.strip() + "\n"


@dataclass
class ModelResult:
    answer: str | None
    usage: Usage
    note: str
    model: str
    attempts: int


async def solve_with_model(task: Task, client: LlmClient, model: str, slot: Slot, max_tokens: int = 4096, user: str = "") -> ModelResult:
    try:
        if task.task_type == "coding":
            return await _solve_coding(task, client, model, slot, max_tokens, user or user_prompt(task))
        prompt = user or user_prompt(task)
        usage = Usage()
        call = await client.complete(model, _SHORT_SYSTEM, prompt, max_tokens=max_tokens, fallback_cost=max_tokens, slot=slot)
        usage.add(call.usage)
        answer = _answer_line(call.text, task.check) or _answer_line(call.reasoning, task.check)
        note = f"модель {model}" if answer else "модель не дала итоговую строку"
        return ModelResult(answer or None, usage, note, model, 1)
    finally:
        slot.release()


async def _solve_coding(task: Task, client: LlmClient, model: str, slot: Slot, max_tokens: int, prompt: str) -> ModelResult:
    work = task.work_dir
    library = work / "mylib.py"
    original = library.read_text(encoding="utf-8") if library.is_file() else ""
    usage = Usage()
    error = ""
    order = [model or MODEL_CODE]
    if order[0] != MODEL_CODE_STRONG:
        order.append(MODEL_CODE_STRONG)
    try:
        for attempt, used_model in enumerate(order, 1):
            user = prompt if attempt == 1 else f"{prompt}\n\nThe tests failed:\n{error[-2000:]}\nReturn the full file again."
            current = slot if attempt == 1 else await client.take()
            try:
                call = await client.complete(used_model, _CODE_SYSTEM, user, max_tokens=max_tokens, fallback_cost=max_tokens, slot=current)
            finally:
                current.release()
            usage.add(call.usage)
            source = _python_source(call.text)
            if "def " not in source:
                source = _python_source(call.reasoning)
            if "def " not in source:
                code, output = await asyncio.to_thread(run_tests, work)
                if code == 0:
                    return ModelResult(
                        "DONE",
                        usage,
                        f"модель {used_model} не прислала файл, тесты уже зелёные\n{library}",
                        used_model,
                        attempt,
                    )
                error = output or "ответ без файла"
                print(f"[{task.task_id}] попытка {attempt} без кода, модель {used_model}", flush=True)
                continue
            library.write_text(source, encoding="utf-8")
            code, output = await asyncio.to_thread(run_tests, work)
            if code == 0:
                return ModelResult(
                    "DONE",
                    usage,
                    f"mylib.py записан: {library}\nтесты прошли, попытка {attempt}",
                    used_model,
                    attempt,
                )
            error = output
            print(f"{task.task_id}: тесты красные, попытка {attempt}, модель {used_model}", flush=True)
        library.write_text(original, encoding="utf-8")
        return ModelResult(None, usage, "код не починился", order[-1], len(order))
    except Exception:
        if library.exists() or original:
            library.write_text(original, encoding="utf-8")
        raise
