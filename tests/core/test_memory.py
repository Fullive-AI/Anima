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

    async def test_ensure_cold_start_profiles_generates_device_aware_defaults(self):
        result = await self.store.ensure_cold_start_profiles(
            device_types=["speaker", "light", "humidifier"],
            user_id="default",
            style="comfort_first",
        )

        prefs = await self.store.get_preferences("default")
        profiles = await self.store.get_learned_profiles("default")

        assert result["preferences_created"] is True
        assert result["profiles_created"] == ["humidifier", "light", "speaker"]
        assert "- humidity: 45-55%" in prefs
        assert "- brightness: daytime moderate, evening warm and dim" in prefs
        assert "speaker: keep voice interactions low-noise by default" in prefs
        assert "humidifier" in profiles
        assert "light" in profiles
        assert "speaker" in profiles
        assert "air_conditioner" not in profiles

        humidifier = json.loads(profiles["humidifier"])
        assert humidifier["bootstrap_style"] == "comfort_first"
        assert humidifier["bootstrap_source"] == "current_device_types"
        assert "45-55%" in " ".join(humidifier["stable_preferences"])

    async def test_ensure_cold_start_profiles_does_not_overwrite_existing_preferences(self):
        custom_preferences = "# User Preferences\n\n## Comfort\n- temperature: 25°C\n"
        self.store._preferences_path("default").write_text(custom_preferences, encoding="utf-8")

        result = await self.store.ensure_cold_start_profiles(
            device_types=["air_conditioner"],
            user_id="default",
            style="comfort_first",
        )

        prefs = await self.store.get_preferences("default")
        assert result["preferences_created"] is False
        assert prefs == custom_preferences

    async def test_ensure_cold_start_profiles_only_fills_missing_profiles(self):
        await self.store.update_learned_for_skill(
            "default",
            "humidifier",
            json.dumps({"stable_preferences": ["Keep 55% humidity"]}),
        )

        result = await self.store.ensure_cold_start_profiles(
            device_types=["humidifier", "light"],
            user_id="default",
            style="comfort_first",
        )

        profiles = await self.store.get_learned_profiles("default")
        assert result["preferences_created"] is True
        assert result["profiles_created"] == ["light"]
        assert result["profiles_skipped"] == ["humidifier"]
        assert json.loads(profiles["humidifier"])["stable_preferences"] == ["Keep 55% humidity"]
        assert "light" in profiles
