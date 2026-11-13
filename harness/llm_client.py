"""Every model call goes through openJiuwen's Model client.

The proxy is OpenAI-compatible. ``-noreason`` model ids are the cheap path;
the request itself stays a plain chat completion.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from harness.budget import Usage, usage_of_message
from harness.config import HTTP_LIMIT

_TRANSIENT = ("connection", "connect", "timeout", "timed out")
_RATE = ("429", "ratelimit", "rate limit", "одновременных", "too many")
_RESET = re.compile(r"Limit resets at:\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


def _transient(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _TRANSIENT)


def _rate_limited(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _RATE)


def _wait_seconds(exc: Exception, attempt: int) -> float:
    match = _RESET.search(str(exc))
    if match:
        reset = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return max(0.5, min((reset - datetime.now(timezone.utc)).total_seconds() + 0.4, 70))
    return float(2 * attempt)


class _DropLibrary(logging.Filter):
    _names = ("common", "llm", "httpx", "httpcore", "openai", "urllib3")

    def filter(self, record: logging.LogRecord) -> bool:
        return record.name.split(".", 1)[0] not in self._names


_quiet_ready = False


def _quiet_logs() -> None:
    global _quiet_ready
    drop = _DropLibrary()
    if not _quiet_ready:
        original = logging.Logger.addHandler

        def add(self, handler, *args, **kwargs):
            handler.addFilter(drop)
            return original(self, handler, *args, **kwargs)

        logging.Logger.addHandler = add
        _quiet_ready = True
    logging.basicConfig(level=logging.WARNING, force=True)
    root = logging.getLogger()
    root.addFilter(drop)
    for handler in root.handlers:
        handler.addFilter(drop)
    for name, logger in list(logging.Logger.manager.loggerDict.items()):
        if not isinstance(logger, logging.Logger):
            continue
        logger.setLevel(logging.WARNING)
        logger.addFilter(drop)
        for handler in logger.handlers:
            handler.addFilter(drop)
    try:
        from loguru import logger as loguru_logger

        loguru_logger.remove()
        loguru_logger.add(lambda _message: None, level="CRITICAL")
    except Exception:
        return


def _plain(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
        return "".join(parts)
    return str(value or "")


def _text(message) -> str:
    return _plain(getattr(message, "content", ""))


def _reasoning(message) -> str:
    return _plain(getattr(message, "reasoning_content", "") or "")


@dataclass
class LlmCall:
    text: str
    usage: Usage
    network_tries: int
    reasoning: str = ""


class Slot:
    """One proxy permit. Releasing it lets the next task call the model."""

    def __init__(self, client: LlmClient):
        self._client = client
        self.held = True

    def release(self) -> None:
        if not self.held:
            return
        self.held = False
        self._client._slots.release()
        self._client.freed.set()


class LlmClient:
    def __init__(self, api_base: str, api_key: str):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self._models: dict[str, object] = {}
        self._slots = asyncio.Semaphore(HTTP_LIMIT)
        self.freed = asyncio.Event()

    def room(self) -> bool:
        return not self._slots.locked()

    async def take(self) -> Slot:
        await self._slots.acquire()
        return Slot(self)

    def busy(self) -> int:
        return HTTP_LIMIT - self._slots._value

    def _model(self, name: str):
        cached = self._models.get(name)
        if cached is not None:
            return cached
        from openjiuwen.core.foundation.llm import init_model

        created = init_model(
            provider="OpenAI",
            model_name=name,
            api_key=self.api_key,
            api_base=self.api_base,
            temperature=0,
            timeout=180,
            verify_ssl=self.api_base.startswith("https://"),
        )
        self._models[name] = created
        return created

    async def complete(self, model: str, system: str, user: str, max_tokens: int, fallback_cost: int, slot: Slot) -> LlmCall:
        held = slot
        last_error: Exception | None = None
        try:
            for attempt in (1, 2, 3, 4, 5, 6):
                _quiet_logs()
                client = self._model(model)
                try:
                    message = await client.invoke(
                        [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        temperature=0,
                        max_tokens=max_tokens,
                    )
                except Exception as exc:
                    last_error = exc
                    if attempt == 6 or not (_transient(exc) or _rate_limited(exc)):
                        raise
                    reason = "лимит 3" if _rate_limited(exc) else "сеть"
                    delay = _wait_seconds(exc, attempt)
                    print(f"LLM повтор {attempt}/6 | модель={model} | {reason}, жду {delay:.1f} с", flush=True)
                    if _transient(exc):
                        self._models.pop(model, None)
                    held.release()
                    await asyncio.sleep(delay)
                    held = await self.take()
                    continue
                held.release()
                usage = usage_of_message(message, fallback_cost)
                return LlmCall(_text(message), usage, attempt, _reasoning(message))
            raise last_error or RuntimeError("model call failed")
        finally:
            held.release()
