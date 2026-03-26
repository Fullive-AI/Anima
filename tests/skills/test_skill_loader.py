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

    def test_skills_use_skill_md_format(self):
        skill = self.loader.get_skill_for_device("humidifier")
        assert skill is not None
        assert (skill.path / "SKILL.md").exists()
        assert (skill.path / "references" / "knowledge.md").exists()
        assert "system" in skill.path.parts

    def test_legacy_skill_yaml_still_supported(self, tmp_path: Path):
        skill_dir = tmp_path / "legacy_skill"
        prompts_dir = skill_dir / "prompts"
        prompts_dir.mkdir(parents=True)

        (skill_dir / "skill.yaml").write_text(
            "\n".join(
                [
                    "name: legacy_skill",
                    "description: legacy test skill",
                    "device_types:",
                    "  - legacy_device",
                    "version: 0.1.0",
                ]
            ),
            encoding="utf-8",
        )
        (skill_dir / "knowledge.md").write_text("legacy knowledge", encoding="utf-8")
        (prompts_dir / "decide.md").write_text("legacy decide {current_data}", encoding="utf-8")

        loader = SkillLoader(skills_dir=str(tmp_path))
        skill = loader.get_skill_for_device("legacy_device")

        assert skill is not None
        assert skill.meta.name == "legacy_skill"
        assert skill.knowledge == "legacy knowledge"
        assert skill.decide_prompt == "legacy decide {current_data}"
