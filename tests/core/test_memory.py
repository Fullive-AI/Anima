import pytest
import json
import tempfile
from pathlib import Path
from core.memory.store import MemoryStore


class TestMemoryStore:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = MemoryStore(base_dir=self.tmpdir)

    async def test_read_preferences_default(self):
        prefs = await self.store.get_preferences("default")
        assert "Comfort" in prefs  # default template should exist

    async def test_write_and_read_preferences(self):
        await self.store.update_preferences("default", "comfort.temperature", "23°C")
        prefs = await self.store.get_preferences("default")
        assert "23°C" in prefs

    async def test_append_history(self):
        await self.store.append_history("default", {
            "action": "set_humidity",
            "device": "humidifier_01",
            "value": 55,
            "reason": "user prefers 55%",
        })
        history = await self.store.get_history("default", limit=10)
        assert len(history) == 1
        assert history[0]["action"] == "set_humidity"

    async def test_history_limit(self):
        for i in range(20):
            await self.store.append_history("default", {"index": i})
        history = await self.store.get_history("default", limit=5)
        assert len(history) == 5

    async def test_get_learned(self):
        learned = await self.store.get_learned("default")
        assert isinstance(learned, str)

    async def test_update_learned(self):
        await self.store.update_learned("default", "User prefers cool environments.")
        learned = await self.store.get_learned("default")
        assert "cool environments" in learned

    async def test_update_learned_for_skill(self):
        await self.store.update_learned_for_skill("default", "humidifier", '{"stable_preferences":["55% humidity"]}')
        learned = await self.store.get_learned_for_skill("default", "humidifier")
        profiles = await self.store.get_learned_profiles("default")
        assert "55% humidity" in learned
        assert "humidifier" in profiles

    async def test_get_full_context(self):
        await self.store.update_preferences("default", "comfort.temperature", "23°C")
        await self.store.append_history("default", {"action": "turn_on"})
        ctx = await self.store.get_full_context("default")
        assert "preferences" in ctx
        assert "history" in ctx
        assert "learned" in ctx
        assert "learned_profiles" in ctx
