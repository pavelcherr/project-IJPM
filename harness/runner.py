"""Run every solvable task through the model queue inside the budget."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from harness.budget import Budget
from harness.config import BUDGET_MARGIN, HTTP_LIMIT, SEQUENTIAL_FIRST, env_budget, env_llm
from harness.gate import task_is_solvable
from harness.llm_client import LlmClient, _quiet_logs
from harness.metrics import RunMetrics, TaskMetric
from harness.model_solver import solve_with_model, system_prompt
from harness.select import Candidate, Prices, candidate_for, next_task, reprice
from harness.tasks import Task, load_tasks


def _fatal(exc: Exception) -> bool:
    text = str(exc).lower()
    markers = ("budget", "quota", "insufficient", "401", "403")
    return any(marker in text for marker in markers)


def _metric(task: Task, status: str, note: str, started: float, **extra) -> TaskMetric:
    gained = task.reward if status.startswith("solved") else 0
    return TaskMetric(
        task_id=task.task_id,
        task_type=task.task_type,
        status=status,
        reward=task.reward,
        reward_gained=gained,
        note=note,
        elapsed_ms=int((time.perf_counter() - started) * 1000),
        answer=str(extra.pop("answer", "") or ""),
        **extra,
    )


def _show(record: TaskMetric, remaining: int, answer_path: Path | None = None) -> None:
    answer = ""
    if record.answer:
        shown = record.answer.replace("\n", " ")
        if len(shown) > 80:
            shown = shown[:80] + "..."
        answer = f" ответ={shown}"
    elif answer_path is None and record.status != "skip-unsolvable":
        answer = " answer.txt не записан"
    if record.note and not record.answer:
        note = record.note.replace("\n", " ")
        if len(note) > 160:
            note = note[:160] + "..."
        answer = f"{answer} {note}"
    print(
        f"{record.task_id} {record.status} счёт={record.cost} остаток={remaining}{answer}",
        flush=True,
    )


async def run(tasks_dir: Path, budget_limit: int | None = None) -> Budget:
    _quiet_logs()
    try:
        import openjiuwen

        _quiet_logs()
        print(f"openjiuwen {getattr(openjiuwen, '__version__', 'installed')}", flush=True)
    except ImportError:
        print("openjiuwen не установлен, вызовы модели выключены", flush=True)

    tasks = load_tasks(tasks_dir)
    budget = Budget(budget_limit if budget_limit is not None else env_budget())
    metrics = RunMetrics(len(tasks), budget.limit)
    api_base, api_key = env_llm()
    print(
        f"--- старт --- задач={len(tasks)} бюджет={budget.limit} "
        f"адрес={'задан' if api_base else 'нет'} ключ={'задан' if api_key else 'нет'}",
        flush=True,
    )

    prices = Prices()
    queued: list[Candidate] = []
    rejected: list[tuple[Task, str]] = []
    by_type: dict[str, list[int]] = {}
    print(f"--- проверка {len(tasks)} задач, до запросов к модели ---", flush=True)
    for task in tasks:
        started = time.perf_counter()
        solvable, reason = task_is_solvable(task)
        counts = by_type.setdefault(task.task_type, [0, 0])
        if not solvable:
            counts[1] += 1
            task.clear_answer()
            rejected.append((task, reason))
            record = _metric(task, "skip-unsolvable", reason, started)
            metrics.add(record)
            continue
        counts[0] += 1
        task.clear_answer()
        queued.append(candidate_for(task, "в модель", prices, system_prompt(task)))

    print(f"решаемых {len(queued)}, нерешаемых {len(rejected)}", flush=True)
    for kind in sorted(by_type):
        solvable_count, rejected_count = by_type[kind]
        print(f"  {kind}: решаемых {solvable_count}, нерешаемых {rejected_count}", flush=True)
    if rejected:
        print("--- нерешаемые ---", flush=True)
        for task, reason in rejected:
            print(f"  {task.task_id}: {reason}", flush=True)
    else:
        print("нерешаемых нет", flush=True)

    reprice(queued, prices, system_prompt)
    _print_queue(queued, budget.remaining)

    if not queued:
        metrics.finish(budget.spent)
        return budget
    if not api_base or not api_key:
        for item in queued:
            record = _metric(item.task, "skip-no-key", item.note, time.perf_counter(), estimate=item.estimate, model=item.model)
            metrics.add(record)
            _show(record, budget.remaining)
        metrics.finish(budget.spent)
        return budget

    client = LlmClient(api_base, api_key)
    in_flight: dict[asyncio.Task, tuple[Candidate, float, int]] = {}
    reserved = 0
    stop = False
    finished = 0
    parallel = False

    def _free() -> int:
        return budget.remaining - reserved

    while (queued or in_flight) and not stop:
        reprice(queued, prices, system_prompt)
        if finished >= SEQUENTIAL_FIRST and not parallel:
            parallel = True
            priced = ", ".join(f"{kind}={value}" for kind, value in sorted(prices.output.items()))
            print(f"--- пересчёт после {SEQUENTIAL_FIRST} задач: {priced} ---", flush=True)
            print(f"--- дальше параллельно, слотов {HTTP_LIMIT} ---", flush=True)
        while queued and client.room() and (parallel or not in_flight):
            item = next_task(queued, _free())
            if item is None:
                break
            queued.remove(item)
            slot = await client.take()
            reserved += item.estimate
            started = time.perf_counter()
            if parallel:
                phase = f"слот {client.busy()}/{HTTP_LIMIT}"
            else:
                phase = f"по одной {finished + 1}/{SEQUENTIAL_FIRST}"
            print(f"запрос {item.task.task_id} -> {item.model} | {phase}", flush=True)
            job = asyncio.create_task(
                solve_with_model(item.task, client, item.model, slot, max_tokens=item.max_tokens, user=item.prompt)
            )
            in_flight[job] = (item, started, item.estimate)
            if not parallel:
                break
        if not in_flight:
            break
        client.freed.clear()
        if parallel and queued and client.room():
            continue
        waiter = asyncio.create_task(client.freed.wait())
        done, _pending = await asyncio.wait(set(in_flight) | {waiter}, return_when=asyncio.FIRST_COMPLETED)
        waiter.cancel()
        try:
            await waiter
        except asyncio.CancelledError:
            pass
        for job in done:
            if job is waiter:
                continue
            item, started, hold = in_flight.pop(job)
            reserved -= hold
            try:
                result = job.result()
            except Exception as exc:
                status = "stop-fatal" if _fatal(exc) else "skip-network"
                record = _metric(item.task, status, str(exc).splitlines()[-1][:180], started, estimate=item.estimate, model=item.model)
                metrics.add(record)
                _show(record, _free())
                finished += 1
                if status == "stop-fatal":
                    stop = True
                continue
            budget.add(result.usage.cost)
            _learn(prices, item, result.usage)
            common = dict(
                cost=result.usage.cost,
                estimate=item.estimate,
                model=result.model,
                attempts=result.attempts,
                input_tokens=result.usage.input_tokens,
                output_tokens=result.usage.output_tokens,
                reasoning_tokens=result.usage.reasoning_tokens,
            )
            if result.answer is None:
                record = _metric(item.task, "unsolved", result.note, started, **common)
                metrics.add(record)
                _show(record, _free())
            else:
                item.task.write_answer(result.answer)
                record = _metric(item.task, "solved-model", result.note, started, answer=result.answer, **common)
                metrics.add(record)
                _show(record, _free(), item.task.answer_path)
            finished += 1
    if stop:
        for job in in_flight:
            job.cancel()

    for item in queued:
        record = _metric(
            item.task,
            "skip-budget",
            f"не влезла после пересчёта, оценка {item.estimate}",
            time.perf_counter(),
            estimate=item.estimate,
            model=item.model,
        )
        metrics.add(record)
        _show(record, budget.remaining)
    metrics.finish(budget.spent)
    return budget


def _learn(prices: Prices, item: Candidate, usage) -> None:
    if usage.input_tokens <= 0 and usage.cost <= 0:
        return
    incoming = (max(usage.input_tokens, 0) + 9) // 10
    outgoing = max(usage.cost - incoming, 1)
    prices.observe(item.task.task_type, outgoing)


def _print_queue(queued: list[Candidate], remaining: int) -> None:
    print(
        f"--- очередь {len(queued)}, остаток {remaining}, запас {BUDGET_MARGIN:.0%} ---",
        flush=True,
    )
