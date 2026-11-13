"""Turn provider usage into the contest's output-equivalent token cost."""

from __future__ import annotations

from dataclasses import dataclass

from harness.config import INPUT_TOKEN_DIVISOR


def output_equivalent(input_tokens: int, output_tokens: int, reasoning_tokens: int = 0) -> int:
    """Cost in output tokens.

    OpenAI-compatible usage nests reasoning inside ``completion_tokens``.
    When ``reasoning_tokens`` is larger than ``output_tokens``, the provider
    reported it separately, so the excess is added. Input is rounded up.
    """
    billed_output = output_tokens
    if reasoning_tokens > output_tokens:
        billed_output = output_tokens + reasoning_tokens
    return (max(input_tokens, 0) + INPUT_TOKEN_DIVISOR - 1) // INPUT_TOKEN_DIVISOR + max(billed_output, 0)


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cost: int = 0

    def add(self, other: Usage) -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.reasoning_tokens += other.reasoning_tokens
        self.cost += other.cost


def usage_of_message(message, fallback: int) -> Usage:
    raw = getattr(message, "usage_metadata", None)
    if raw is None:
        return Usage(cost=fallback)
    usage = Usage(
        input_tokens=int(getattr(raw, "input_tokens", 0) or 0),
        output_tokens=int(getattr(raw, "output_tokens", 0) or 0),
        reasoning_tokens=int(getattr(raw, "reasoning_tokens", 0) or 0),
    )
    usage.cost = output_equivalent(usage.input_tokens, usage.output_tokens, usage.reasoning_tokens)
    if usage.cost <= 0:
        usage.cost = fallback
    return usage


@dataclass
class Budget:
    limit: int
    spent: int = 0

    @property
    def remaining(self) -> int:
        return self.limit - self.spent

    def can_spend(self, estimate: int) -> bool:
        return estimate <= self.remaining

    def add(self, cost: int) -> None:
        self.spent += max(cost, 0)
