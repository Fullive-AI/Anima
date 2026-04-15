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
        await self.store.append_history(
            "default",
            {
                "action": "set_humidity",
                "device": "humidifier_01",
                "value": 55,
                "reason": "user prefers 55%",
            },
        )
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
        await self.store.append_history(
            "default", {"action": "turn_on", "device_type": "light", "reason": "evening routine"}
        )
        await self.store.append_history(
            "default", {"action": "set_brightness", "device_type": "light", "params": {"value": 20}}
        )

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

    async def test_memory_extractor_skips_custom_skill_memory_without_real_custom_skill(self, monkeypatch):
        await self.store.append_history(
            "default",
            {"action": "plan.reply", "params": {"reply": "已成功创建一个新的自定义技能。"}},
        )

        skills_dir = Path(self.tmpdir) / "skills"
        skills_dir.mkdir()

        monkeypatch.setattr("core.memory.extractor.settings.llm_api_key", "sk-test")
        extractor = MemoryExtractionService(self.store, skills_dir=str(skills_dir))
        extractor._invoke_llm_text = AsyncMock(
            return_value=json.dumps(
                {
                    "memories": [
                        {
                            "topic": "user_custom_curtain_control_skill",
                            "title": "User's custom smart curtain control skill",
                            "category": "context",
                            "summary": "The user's requested custom smart curtain control skill has been successfully created and processed.",
                            "details": ["Custom smart curtain control skill created and processed"],
                            "device_types": ["curtain"],
                            "confidence": "high",
                            "source_actions": ["plan.reply"],
                        }
                    ],
                    "forget_topics": [],
                }
            )
        )

        changed = await extractor.run_now("default")
        memories = await self.store.get_extracted_memories("default")

        assert changed is False
        assert "user_custom_curtain_control_skill" not in memories

    async def test_memory_extractor_keeps_custom_skill_memory_only_when_matching_real_custom_skill_exists(
        self, monkeypatch
    ):
        await self.store.append_history(
            "default",
            {"action": "plan.reply", "params": {"reply": "工作日早上8点起床提醒技能已创建并激活。"}},
        )

        custom_skill_dir = Path(self.tmpdir) / "skills" / "custom" / "workday_8am_smart_speaker_wakeup"
        custom_skill_dir.mkdir(parents=True)
        (custom_skill_dir / "SKILL.md").write_text(
            (
                "---\n"
                "name: Workday 8AM Smart Speaker Wakeup\n"
                "description: A recurring automated skill that triggers a wake-up alarm via connected smart speaker at 8 AM local time on workdays and skips alarms on holidays\n"
                "metadata:\n"
                "  device_types:\n"
                "    - smart_speaker\n"
                "---\n"
            ),
            encoding="utf-8",
        )

        monkeypatch.setattr("core.memory.extractor.settings.llm_api_key", "sk-test")
        extractor = MemoryExtractionService(self.store, skills_dir=str(Path(self.tmpdir) / "skills"))
        extractor._invoke_llm_text = AsyncMock(
            return_value=json.dumps(
                {
                    "memories": [
                        {
                            "topic": "user_custom_8am_workday_wake_up_reminder_skill",
                            "title": "User's custom 8 AM workday wake up reminder skill",
                            "category": "routine",
                            "summary": "The user's requested custom 8 AM workday wake up reminder skill that skips legal holidays and triggers via connected Xiaomi Smart Speaker has been successfully created and activated.",
                            "details": [
                                "Triggers at 8 AM on workdays",
                                "Skips legal holidays",
                                "Triggers via connected Xiaomi Smart Speaker",
                            ],
                            "device_types": ["smart_speaker"],
                            "confidence": "high",
                            "source_actions": ["plan.reply"],
                        }
                    ],
                    "forget_topics": [],
                }
            )
        )

        changed = await extractor.run_now("default")
        memories = await self.store.get_extracted_memories("default")

        assert changed is True
        assert (
            memories["user_custom_8am_workday_wake_up_reminder_skill"]["linked_custom_skill_name"]
            == "Workday 8AM Smart Speaker Wakeup"
        )

    async def test_memory_extractor_cleans_up_existing_invalid_custom_skill_memories_without_llm(self):
        await self.store.upsert_extracted_memory(
            "default",
            "user_custom_curtain_control_skill",
            {
                "title": "User's custom smart curtain control skill",
                "category": "context",
                "summary": "The user's requested custom smart curtain control skill has been successfully created and processed.",
                "details": ["Custom smart curtain control skill created and processed"],
                "device_types": ["curtain"],
                "confidence": "high",
                "source_actions": ["plan.reply"],
            },
        )

        skills_dir = Path(self.tmpdir) / "skills"
        skills_dir.mkdir()

        extractor = MemoryExtractionService(self.store, skills_dir=str(skills_dir))
        extractor._invoke_llm_text = AsyncMock(
            return_value=json.dumps(
                {
                    "memories": [],
                    "forget_topics": [],
                }
            )
        )

        changed = await extractor.run_now("default")
        memories = await self.store.get_extracted_memories("default")

        assert changed is True
        assert "user_custom_curtain_control_skill" not in memories

    async def test_preference_learner_updates_skill_profile_from_history_and_memories(self, monkeypatch):
        await self.store.append_history(
            "default", {"action": "turn_on", "device_type": "light", "reason": "evening routine"}
        )
        await self.store.append_history(
            "default", {"action": "set_brightness", "device_type": "light", "params": {"value": 20}}
        )
        await self.store.append_history(
            "default", {"action": "set_color_temp", "device_type": "light", "params": {"value": 2700}}
        )

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
