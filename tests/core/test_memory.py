import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

from core.brain.skill_loader import SkillLoader
from core.memory.extractor import MemoryExtractionService
from core.memory.learning import PreferenceLearningService
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

    async def test_update_learned_for_skill_normalizes_legacy_shape(self):
        await self.store.update_learned_for_skill(
            "default",
            "speaker",
            json.dumps(
                {
                    "stable_preferences": {
                        "preferred_actions": ["turn_on"],
                        "consistent_device_targets": ["speaker_01"],
                    },
                    "time_based_patterns": {"peak_usage_windows": ["evening"]},
                    "seasonal_patterns": {},
                    "weak_signals": ["Limited history"],
                    "confidence_notes": "Sparse but consistent.",
                }
            ),
        )

        profile = json.loads(await self.store.get_learned_for_skill("default", "speaker"))
        assert "preferred_actions" in profile["stable_preferences"][0]
        assert "peak_usage_windows" in profile["time_based_patterns"][0]
        assert profile["confidence_notes"] == "Sparse but consistent."

    async def test_get_full_context(self):
        await self.store.update_preferences("default", "comfort.temperature", "23°C")
        await self.store.append_history("default", {"action": "turn_on"})
        ctx = await self.store.get_full_context("default")
        assert "preferences" in ctx
        assert "history" in ctx
        assert "learned" in ctx
        assert "learned_profiles" in ctx
        assert "memory_manifest" in ctx
        assert "extracted_memories" in ctx

    async def test_extracted_memories_round_trip(self):
        await self.store.upsert_extracted_memory(
            "default",
            "sleep_lighting_preference",
            {
                "title": "Sleep lighting preference",
                "category": "preference",
                "summary": "User prefers warm dim lights before sleep.",
                "details": ["Use warmer light late at night."],
                "device_types": ["light"],
                "confidence": "high",
                "source_actions": ["set_brightness"],
            },
        )

        manifest = await self.store.get_memory_manifest("default")
        memories = await self.store.get_extracted_memories("default")

        assert manifest[0]["topic"] == "sleep_lighting_preference"
        assert memories["sleep_lighting_preference"]["category"] == "preference"

    async def test_memory_extractor_writes_topic_files_and_advances_cursor(self, monkeypatch):
        await self.store.append_history("default", {"action": "turn_on", "device_type": "light", "reason": "evening routine"})
        await self.store.append_history("default", {"action": "set_brightness", "device_type": "light", "params": {"value": 20}})

        monkeypatch.setattr("core.memory.extractor.settings.llm_api_key", "sk-test")
        extractor = MemoryExtractionService(self.store)
        extractor._invoke_llm_text = AsyncMock(
            return_value=json.dumps(
                {
                    "memories": [
                        {
                            "topic": "evening_lighting_routine",
                            "title": "Evening lighting routine",
                            "category": "routine",
                            "summary": "Lights are typically turned on at low brightness in the evening.",
                            "details": ["Favor low brightness during evening hours."],
                            "device_types": ["light"],
                            "confidence": "high",
                            "source_actions": ["turn_on", "set_brightness"],
                        }
                    ],
                    "forget_topics": [],
                }
            )
        )

        changed = await extractor.run_now("default")
        state = await self.store.get_memory_extraction_state("default")
        memories = await self.store.get_extracted_memories("default")

        assert changed is True
        assert state["history_cursor"] == 2
        assert "evening_lighting_routine" in memories
        assert memories["evening_lighting_routine"]["summary"].startswith("Lights are typically")

    async def test_preference_learner_updates_skill_profile_from_history_and_memories(self, monkeypatch):
        await self.store.append_history("default", {"action": "turn_on", "device_type": "light", "reason": "evening routine"})
        await self.store.append_history("default", {"action": "set_brightness", "device_type": "light", "params": {"value": 20}})
        await self.store.append_history("default", {"action": "set_color_temp", "device_type": "light", "params": {"value": 2700}})

        monkeypatch.setattr("core.memory.extractor.settings.llm_api_key", "sk-test")
        extractor = MemoryExtractionService(self.store)
        extractor._invoke_llm_text = AsyncMock(
            return_value=json.dumps(
                {
                    "memories": [
                        {
                            "topic": "evening_lighting_preference",
                            "title": "Evening lighting preference",
                            "category": "preference",
                            "summary": "The user prefers warm dim lighting in the evening.",
                            "details": ["Warm and dim lighting repeats in recent history."],
                            "device_types": ["light"],
                            "confidence": "high",
                            "source_actions": ["set_brightness", "set_color_temp"],
                        }
                    ],
                    "forget_topics": [],
                }
            )
        )

        loader = SkillLoader(skills_dir="skills")
        loader.discover()
        learner = PreferenceLearningService(
            self.store,
            extractor=extractor,
            skill_loader=loader,
            invoke_llm_text=AsyncMock(return_value='{"stable_preferences":["Prefer warm dim lights in the evening."]}'),
        )

        changed = await learner.run_now("default")
        profile = await self.store.get_learned_for_skill("default", "light")

        assert changed is True
        assert "warm dim lights" in profile
        parsed = json.loads(profile)
        assert parsed["metadata"]["device_type"] == "light"
        assert parsed["metadata"]["history_samples"] == 3
        assert parsed["metadata"]["memory_topics"] == ["evening_lighting_preference"]

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
        assert humidifier["metadata"]["bootstrap_style"] == "comfort_first"
        assert humidifier["metadata"]["bootstrap_source"] == "current_device_types"
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
