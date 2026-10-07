"""Where guardrail events go. Saving them must never slow down or break a chat reply."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

from mirrorguard.guardrail.types import GuardrailEvent

log = logging.getLogger(__name__)


class EventSink(Protocol):
    async def emit(self, event: GuardrailEvent) -> None: ...


class NullSink:
    async def emit(self, event: GuardrailEvent) -> None:
        return None


class MemorySink:
    """Keeps events in a list. For tests and the benchmark."""

    def __init__(self):
        self.events: list[GuardrailEvent] = []

    async def emit(self, event: GuardrailEvent) -> None:
        self.events.append(event)


class QueueSink:
    """Hands events to a background task through a bounded queue.

    If the writer falls behind and the queue fills up, new events are dropped and
    counted. Losing a log line is better than making a user wait.
    """

    def __init__(self, write: Callable[[GuardrailEvent], Awaitable[None]], max_queue: int = 5000):
        self._write = write
        self._queue: asyncio.Queue[GuardrailEvent | None] = asyncio.Queue(maxsize=max_queue)
        self._task: asyncio.Task | None = None
        self.dropped = 0

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def emit(self, event: GuardrailEvent) -> None:
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self.dropped += 1

    async def _run(self) -> None:
        while True:
            event = await self._queue.get()
            try:
                if event is None:
                    return
                await self._write(event)
            except Exception:
                log.exception("could not save a guardrail event")
            finally:
                self._queue.task_done()

    async def flush(self) -> None:
        """Wait until everything queued so far has been written."""
        await self._queue.join()

    async def stop(self) -> None:
        """Write out everything still waiting, then stop."""
        if self._task is None:
            return
        await self._queue.put(None)
        await self._task
        self._task = None
