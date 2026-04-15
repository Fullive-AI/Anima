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
        self._tasks: list[asyncio.Task[None]] = []

    def add_job(self, name: str, func: Callable[[], Awaitable[None]], interval_seconds: float) -> None:
        self.jobs[name] = Job(name=name, func=func, interval_seconds=interval_seconds)

    def remove_job(self, name: str) -> None:
        self.jobs.pop(name, None)

    def update_job_interval(self, name: str, interval_seconds: float) -> None:
        job = self.jobs.get(name)
        if job:
            job.interval_seconds = interval_seconds

    def stop(self) -> None:
        self._running = False
        for task in list(self._tasks):
            task.cancel()

    async def start(self) -> None:
        self._running = True
        self._tasks = [asyncio.create_task(self._run_job(job)) for job in self.jobs.values()]
        try:
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            self.stop()
            raise
        finally:
            self._running = False
            if self._tasks:
                await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks = []

    async def _run_job(self, job: Job) -> None:
        while self._running:
            try:
                await job.func()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Scheduler job '%s' failed", job.name)
            await asyncio.sleep(job.interval_seconds)
