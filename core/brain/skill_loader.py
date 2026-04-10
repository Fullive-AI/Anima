from __future__ import annotations

import re
import logging
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import yaml

from core.models import SkillMeta, SkillSummary

logger = logging.getLogger(__name__)


@dataclass
class LoadedSkill:
    meta: SkillMeta
    knowledge: str
    decide_prompt: str | None
    learn_prompt: str | None
    orchestrate_prompt: str | None
    chat_prompt: str | None
    actions_module_path: Path | None
    path: Path


@dataclass
class SkillInventoryItem:
    name: str
    description: str
    scope: str
    folder_name: str
    device_types: list[str]
    version: str
    path: str
    has_actions: bool
    has_chat_prompt: bool
    has_decide_prompt: bool


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

        self._cache.clear()
        self._cache_by_name.clear()
        self._actions_cache.clear()

        for skill_dir in self._iter_skill_dirs():
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

    def _iter_skill_dirs(self) -> list[Path]:
        markers = ("SKILL.md", "skill.yaml")
        seen: set[Path] = set()
        skill_dirs: list[Path] = []

        for marker in markers:
            for path in sorted(self._dir.rglob(marker)):
                skill_dir = path.parent
                if self._should_skip_dir(skill_dir):
                    continue
                if skill_dir in seen:
                    continue
                seen.add(skill_dir)
                skill_dirs.append(skill_dir)

        return sorted(skill_dirs)

    def _should_skip_dir(self, path: Path) -> bool:
        return any(
            part.startswith(".") or part.startswith("_") or part == "__pycache__"
            for part in path.parts
        )

    def _load_skill(self, skill_dir: Path) -> LoadedSkill:
        skill_md_path = skill_dir / "SKILL.md"
        legacy_yaml_path = skill_dir / "skill.yaml"

        if skill_md_path.exists():
            return self._load_skill_from_skill_md(skill_dir, skill_md_path)
        if legacy_yaml_path.exists():
            return self._load_skill_from_legacy(skill_dir, legacy_yaml_path)

        raise FileNotFoundError(f"No SKILL.md or skill.yaml found in {skill_dir}")

    def _load_skill_from_skill_md(self, skill_dir: Path, skill_md_path: Path) -> LoadedSkill:
        frontmatter, _body = self._parse_frontmatter(skill_md_path.read_text(encoding="utf-8"))
        metadata = frontmatter.get("metadata", {}) if isinstance(frontmatter.get("metadata"), dict) else {}

        meta = SkillMeta(
            name=frontmatter["name"],
            description=frontmatter["description"],
            device_types=frontmatter.get("device_types") or metadata.get("device_types") or [],
            version=frontmatter.get("version") or metadata.get("version") or "0.1.0",
        )

        references_dir = skill_dir / "references"
        prompts_dir = skill_dir / "prompts"

        return LoadedSkill(
            meta=meta,
            knowledge=self._read_optional(
                references_dir / "knowledge.md",
                fallback=skill_dir / "knowledge.md",
                default="",
            ),
            decide_prompt=self._read_optional(
                references_dir / "decide.md",
                fallback=prompts_dir / "decide.md",
            ),
            learn_prompt=self._read_optional(
                references_dir / "learn.md",
                fallback=prompts_dir / "learn.md",
            ),
            orchestrate_prompt=self._read_optional(
                references_dir / "orchestrate.md",
                fallback=prompts_dir / "orchestrate.md",
            ),
            chat_prompt=self._read_optional(
                references_dir / "chat.md",
                fallback=prompts_dir / "chat.md",
            ),
            actions_module_path=self._find_actions_module(skill_dir),
            path=skill_dir,
        )

    def _load_skill_from_legacy(self, skill_dir: Path, legacy_yaml_path: Path) -> LoadedSkill:
        with legacy_yaml_path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        meta = SkillMeta(**raw)

        return LoadedSkill(
            meta=meta,
            knowledge=self._read_optional(skill_dir / "knowledge.md", default=""),
            decide_prompt=self._read_optional(skill_dir / "prompts" / "decide.md"),
            learn_prompt=self._read_optional(skill_dir / "prompts" / "learn.md"),
            orchestrate_prompt=self._read_optional(skill_dir / "prompts" / "orchestrate.md"),
            chat_prompt=self._read_optional(skill_dir / "prompts" / "chat.md"),
            actions_module_path=self._find_actions_module(skill_dir),
            path=skill_dir,
        )

    @staticmethod
    def _parse_frontmatter(content: str) -> tuple[dict[str, object], str]:
        match = re.match(r"^---\n(.*?)\n---\n?(.*)$", content, re.DOTALL)
        if not match:
            raise ValueError("SKILL.md is missing YAML frontmatter")

        frontmatter = yaml.safe_load(match.group(1)) or {}
        if not isinstance(frontmatter, dict):
            raise ValueError("SKILL.md frontmatter must be a YAML mapping")
        if "name" not in frontmatter or "description" not in frontmatter:
            raise ValueError("SKILL.md frontmatter must include name and description")

        return frontmatter, match.group(2)

    @staticmethod
    def _read_optional(path: Path, fallback: Path | None = None, default: str | None = None) -> str | None:
        candidates = [path]
        if fallback is not None:
            candidates.append(fallback)

        for candidate in candidates:
            if candidate.exists():
                return candidate.read_text(encoding="utf-8")

        return default

    @staticmethod
    def _find_actions_module(skill_dir: Path) -> Path | None:
        candidates = [
            skill_dir / "scripts" / "actions.py",
            skill_dir / "actions.py",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def get_skill_for_device(self, device_type: str) -> LoadedSkill | None:
        if not self._cache:
            self.discover()
        return self._cache.get(device_type)

    def get_skill(self, name: str) -> LoadedSkill | None:
        if not self._cache_by_name:
            self.discover()
        return self._cache_by_name.get(name)

    def get_system_skill_for_device(self, device_type: str) -> LoadedSkill | None:
        if not self._cache:
            self.discover()

        skill = self._cache.get(device_type)
        if not skill:
            return None

        return skill if "system" in skill.path.parts else None

    @staticmethod
    def _to_summary(skill: LoadedSkill) -> SkillSummary:
        return SkillSummary(
            name=skill.meta.name,
            description=skill.meta.description,
            device_type=skill.meta.device_types[0] if skill.meta.device_types else "",
        )

    def list_executable_skill_summaries(self) -> list[SkillSummary]:
        if not self._cache_by_name:
            self.discover()

        summaries: list[SkillSummary] = []
        for skill in self._cache_by_name.values():
            if not skill.decide_prompt:
                continue
            if not skill.meta.device_types:
                continue
            summaries.append(self._to_summary(skill))

        return sorted(summaries, key=lambda item: item.name)

    def list_chat_skill_summaries(self) -> list[SkillSummary]:
        if not self._cache_by_name:
            self.discover()

        summaries: list[SkillSummary] = []
        for skill in self._cache_by_name.values():
            is_system_skill = "system" in skill.path.parts
            is_executable_custom_skill = bool(skill.decide_prompt and skill.meta.device_types)
            if not is_system_skill and not is_executable_custom_skill:
                continue
            summaries.append(self._to_summary(skill))

        return sorted(summaries, key=lambda item: item.name)

    def list_custom_skill_names(self) -> list[str]:
        if not self._cache_by_name:
            self.discover()

        return sorted(
            skill.meta.name
            for skill in self._cache_by_name.values()
            if "custom" in skill.path.parts
        )

    def list_system_device_skill_summaries(self) -> list[SkillSummary]:
        if not self._cache_by_name:
            self.discover()

        summaries: list[SkillSummary] = []
        for skill in self._cache_by_name.values():
            if "system" not in skill.path.parts:
                continue
            if not skill.decide_prompt:
                continue
            if not skill.meta.device_types:
                continue
            summaries.append(self._to_summary(skill))

        return sorted(summaries, key=lambda item: item.name)

    def list_system_skill_summaries(self) -> list[SkillSummary]:
        if not self._cache_by_name:
            self.discover()

        summaries: list[SkillSummary] = []
        for skill in self._cache_by_name.values():
            if "system" not in skill.path.parts:
                continue
            summaries.append(self._to_summary(skill))

        return sorted(summaries, key=lambda item: item.name)

    @staticmethod
    def _to_inventory_item(skill: LoadedSkill) -> SkillInventoryItem:
        scope = "custom" if "custom" in skill.path.parts else "system" if "system" in skill.path.parts else "unknown"
        return SkillInventoryItem(
            name=skill.meta.name,
            description=skill.meta.description,
            scope=scope,
            folder_name=skill.path.name,
            device_types=list(skill.meta.device_types),
            version=skill.meta.version,
            path=str(skill.path),
            has_actions=skill.actions_module_path is not None,
            has_chat_prompt=bool(skill.chat_prompt),
            has_decide_prompt=bool(skill.decide_prompt),
        )

    def list_system_skills_with_meta(self) -> list[SkillInventoryItem]:
        if not self._cache_by_name:
            self.discover()

        items = [
            self._to_inventory_item(skill)
            for skill in self._cache_by_name.values()
            if "system" in skill.path.parts
        ]
        return sorted(items, key=lambda item: item.name)

    def list_custom_skills_with_meta(self) -> list[SkillInventoryItem]:
        if not self._cache_by_name:
            self.discover()

        items = [
            self._to_inventory_item(skill)
            for skill in self._cache_by_name.values()
            if "custom" in skill.path.parts
        ]
        return sorted(items, key=lambda item: item.name)

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
