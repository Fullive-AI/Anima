from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Job:
    name: str
    func: Callable[[], Awaitable[None]]
    interval_seconds: float


class Scheduler:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self._running = False

    def add_job(self, name: str, func: Callable[[], Awaitable[None]], interval_seconds: float) -> None:
        self.jobs[name] = Job(name=name, func=func, interval_seconds=interval_seconds)

    def remove_job(self, name: str) -> None:
        self.jobs.pop(name, None)

    def stop(self) -> None:
        self._running = False

    async def start(self) -> None:
        self._running = True
        tasks = []
        for job in self.jobs.values():
            tasks.append(asyncio.create_task(self._run_job(job)))
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass

    async def _run_job(self, job: Job) -> None:
        while self._running:
            try:
                await job.func()
            except Exception:
                logger.exception("Scheduler job '%s' failed", job.name)
            await asyncio.sleep(job.interval_seconds)
