"""全局单写队列：所有对平台的写动作串行执行 + 抖动。

这同时是风控纪律（串行、间隔、退避）与并发控制（不会两个回复同时发）。
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

log = logging.getLogger("yuxiaoer.write_queue")

Operation = Callable[[], Awaitable[Any]]


@dataclass
class _Job:
    label: str
    operation: Operation
    future: asyncio.Future
    min_interval: float | None = None
    jitter: float | None = None


class WriteQueue:
    def __init__(self, *, min_interval: float = 0.12, jitter: float = 0.06):
        self.min_interval = min_interval
        self.jitter = jitter
        self.queue: asyncio.Queue[_Job] = asyncio.Queue()
        self.worker: asyncio.Task | None = None
        self.running = False
        self.processed = 0
        self.failed = 0
        self.last_error: str | None = None
        self.last_write_at: float = 0.0
        self._last_label: str | None = None
        self.risk_guard: Any = None

    def start(self) -> None:
        if self.worker is None:
            self.running = True
            self.worker = asyncio.create_task(self._run(), name="write-queue")

    async def stop(self) -> None:
        self.running = False
        if self.worker:
            self.worker.cancel()
            try:
                await self.worker
            except (asyncio.CancelledError, Exception):
                pass
            self.worker = None

    async def run(
        self,
        operation: Operation,
        *,
        label: str = "write",
        min_interval: float | None = None,
        jitter: float | None = None,
    ) -> Any:
        if self.risk_guard is not None:
            await self.risk_guard.ensure_closed()
        if not self.running:
            try:
                return await operation()
            except Exception as exc:
                if self.risk_guard is not None:
                    await self.risk_guard.observe_error(exc)
                raise
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        await self.queue.put(_Job(label, operation, future, min_interval, jitter))
        return await future

    async def _run(self) -> None:
        while self.running:
            try:
                job = await self.queue.get()
            except asyncio.CancelledError:
                return
            try:
                if self.risk_guard is not None:
                    await self.risk_guard.ensure_closed()
                gap = time.monotonic() - self.last_write_at
                interval = self.min_interval if job.min_interval is None else job.min_interval
                jitter = self.jitter if job.jitter is None else job.jitter
                wait = max(0.0, interval - gap)
                if jitter:
                    wait += random.uniform(0, jitter)
                if wait > 0:
                    await asyncio.sleep(wait)
                result = await job.operation()
                self.processed += 1
                self.last_write_at = time.monotonic()
                self._last_label = job.label
                if not job.future.done():
                    job.future.set_result(result)
            except asyncio.CancelledError:
                return
            except Exception as exc:  # noqa: BLE001
                self.failed += 1
                self.last_error = f"{job.label}: {exc}"
                log.warning("write failed [%s]: %s", job.label, exc)
                if self.risk_guard is not None and type(exc).__name__ != "RiskControlOpen":
                    await self.risk_guard.observe_error(exc)
                if not job.future.done():
                    job.future.set_exception(exc)
            finally:
                self.queue.task_done()

    def stats(self) -> dict[str, Any]:
        return {
            "depth": self.queue.qsize(),
            "processed": self.processed,
            "failed": self.failed,
            "last_error": self.last_error,
            "last_label": self._last_label,
            "running": self.running,
        }
