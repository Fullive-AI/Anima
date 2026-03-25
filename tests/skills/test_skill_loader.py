import pytest
from pathlib import Path
from core.brain.skill_loader import SkillLoader, LoadedSkill


class TestSkillLoader:
    def setup_method(self):
        self.loader = SkillLoader(skills_dir="skills")

    def test_discover_skills(self):
        skills = self.loader.discover()
        names = [s.meta.name for s in skills]
        assert "humidifier" in names
        assert "air_conditioner" in names
        assert "light" in names

    def test_load_skill_by_device_type(self):
        skill = self.loader.get_skill_for_device("humidifier")
        assert skill is not None
        assert skill.meta.name == "humidifier"
        assert len(skill.knowledge) > 0
        assert "humidity" in skill.knowledge.lower()

    def test_load_skill_knowledge(self):
        skill = self.loader.get_skill_for_device("humidifier")
        assert "40%" in skill.knowledge or "60%" in skill.knowledge

    def test_load_skill_prompt(self):
        skill = self.loader.get_skill_for_device("humidifier")
        assert skill.decide_prompt is not None
        assert "{current_data}" in skill.decide_prompt or "{" in skill.decide_prompt

    def test_unknown_device_returns_none(self):
        skill = self.loader.get_skill_for_device("nuclear_reactor")
        assert skill is None

    def test_coordinator_skill(self):
        skill = self.loader.get_skill_for_device("coordinator")
        assert skill is not None

    def test_load_skill_by_name(self):
        skill = self.loader.get_skill("device_discovery")
        assert skill is not None
        assert skill.chat_prompt is not None
