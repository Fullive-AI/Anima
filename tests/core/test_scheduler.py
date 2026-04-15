import asyncio

from core.scheduler.scheduler import Scheduler


class TestScheduler:
    def test_add_job(self):
        sched = Scheduler()

        async def dummy():
            pass

        sched.add_job("test", dummy, interval_seconds=60)
        assert "test" in sched.jobs

    def test_remove_job(self):
        sched = Scheduler()

        async def dummy():
            pass

        sched.add_job("test", dummy, interval_seconds=60)
        sched.remove_job("test")
        assert "test" not in sched.jobs

    async def test_job_executes(self):
        sched = Scheduler()
        counter = {"count": 0}

        async def increment():
            counter["count"] += 1

        sched.add_job("inc", increment, interval_seconds=0.1)
        task = asyncio.create_task(sched.start())
        await asyncio.sleep(0.35)
        sched.stop()
        await task

        assert counter["count"] >= 2
