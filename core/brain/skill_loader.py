from __future__ import annotations

import logging
import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

import yaml

from core.models import SkillMeta

logger = logging.getLogger(__name__)


@dataclass
class LoadedSkill:
    meta: SkillMeta
    knowledge: str
    decide_prompt: str | None
    learn_prompt: str | None
    actions_module_path: Path | None
    path: Path

    @property
    def orchestrate_prompt(self) -> str | None:
        p = self.path / "prompts" / "orchestrate.md"
        if p.exists():
            return p.read_text(encoding="utf-8")
        return None

    @property
    def chat_prompt(self) -> str | None:
        p = self.path / "prompts" / "chat.md"
        if p.exists():
            return p.read_text(encoding="utf-8")
        return None


class SkillLoader:
    def __init__(self, skills_dir: str = "skills") -> None:
        self._dir = Path(skills_dir)
        self._cache: dict[str, LoadedSkill] = {}
        self._cache_by_name: dict[str, LoadedSkill] = {}
        self._actions_cache: dict[str, ModuleType] = {}

    def discover(self) -> list[LoadedSkill]:
        skills = []
        if not self._dir.exists():
            logger.warning("Skills directory not found: %s", self._dir)
            return skills

        for skill_dir in sorted(self._dir.iterdir()):
            yaml_path = skill_dir / "skill.yaml"
            if not yaml_path.exists():
                continue

            try:
                skill = self._load_skill(skill_dir)
                skills.append(skill)
                self._cache_by_name[skill.meta.name] = skill
                for dt in skill.meta.device_types:
                    self._cache[dt] = skill
            except Exception:
                logger.exception("Failed to load skill from %s", skill_dir)

        logger.info("Loaded %d skills: %s", len(skills), [s.meta.name for s in skills])
        return skills

    def _load_skill(self, skill_dir: Path) -> LoadedSkill:
        # Load metadata
        with open(skill_dir / "skill.yaml", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        meta = SkillMeta(**raw)

        # Load knowledge
        knowledge_path = skill_dir / "knowledge.md"
        knowledge = knowledge_path.read_text(encoding="utf-8") if knowledge_path.exists() else ""

        # Load prompts
        decide_path = skill_dir / "prompts" / "decide.md"
        decide_prompt = decide_path.read_text(encoding="utf-8") if decide_path.exists() else None

        learn_path = skill_dir / "prompts" / "learn.md"
        learn_prompt = learn_path.read_text(encoding="utf-8") if learn_path.exists() else None

        # Actions module
        actions_path = skill_dir / "actions.py"

        return LoadedSkill(
            meta=meta,
            knowledge=knowledge,
            decide_prompt=decide_prompt,
            learn_prompt=learn_prompt,
            actions_module_path=actions_path if actions_path.exists() else None,
            path=skill_dir,
        )

    def get_skill_for_device(self, device_type: str) -> LoadedSkill | None:
        if not self._cache:
            self.discover()
        return self._cache.get(device_type)

    def get_skill(self, name: str) -> LoadedSkill | None:
        if not self._cache_by_name:
            self.discover()
        return self._cache_by_name.get(name)

    def load_actions(self, skill: LoadedSkill) -> ModuleType | None:
        if not skill.actions_module_path:
            return None

        cache_key = skill.meta.name
        if cache_key in self._actions_cache:
            return self._actions_cache[cache_key]

        module_name = f"anima_skill_{cache_key}"
        spec = importlib.util.spec_from_file_location(module_name, skill.actions_module_path)
        if not spec or not spec.loader:
            logger.warning("Failed to load actions module for skill %s", cache_key)
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        self._actions_cache[cache_key] = module
        return module
