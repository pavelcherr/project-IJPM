"""Contest constants. Model ids are the four names the proxy accepts."""

import os

MODEL_CHEAP = "qwen3.8-27b-noreason"
MODEL_REASON = "qwen3.8-27b"
MODEL_CODE = MODEL_CHEAP
MODEL_CODE_STRONG = MODEL_REASON

# Starting output price in budget tokens, before any live call.
# The queue adds input/10 on top. max_tokens is a separate cap on the
# reply alone, in completion tokens. Reasoning and the final answer share it.
OUTPUT_PRIOR = {
    "math": 120,
    "data_analysis": 230,
    "search": 10,
    "coding": 60,
}
MODEL_BY_TYPE = {
    "math": MODEL_REASON,
    "data_analysis": MODEL_REASON,
    "search": MODEL_CHEAP,
    "coding": MODEL_CODE,
}
# Reply ceiling in completion tokens. One number for every type: a tangled
# task can spend the trace before the short final answer, and 40 or 512 cut
# that trace. 4096 still stops a temperature-0 loop from draining the budget.
OUTPUT_CAP = {
    "math": 4096,
    "data_analysis": 4096,
    "search": 4096,
    "coding": 4096,
}

# Keep a margin: estimates are coarse, and a single overrun ends the run.
BUDGET_MARGIN = 0.90
# First tasks run one by one so each measured cost can reprice the queue.
# After that the rest run together, up to the proxy's 3 in-flight calls.
SEQUENTIAL_FIRST = 4
HTTP_LIMIT = 3
DEFAULT_BUDGET = 100_000

# 10 input tokens count as 1 output token. Cache is not discounted.
INPUT_TOKEN_DIVISOR = 10


def env_budget() -> int:
    raw = os.environ.get("BUDGET", "").strip()
    if not raw:
        return DEFAULT_BUDGET
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_BUDGET
    return value if value > 0 else DEFAULT_BUDGET


def env_llm() -> tuple[str, str]:
    return os.environ.get("LLM_BASE_URL", "").strip(), os.environ.get("LLM_API_KEY", "").strip()
