# Skill Creator — Domain Knowledge

## Goal

- Convert a natural-language requirement into a custom Anima skill package.
- Produce a skill that matches the current repository structure and loading rules.

## Package Shape

- `SKILL.md`
- `references/knowledge.md`
- `references/decide.md`
- `references/learn.md`
- `scripts/actions.py`

## Quality Bar

- The generated skill should explain when it triggers and what actions it can emit.
- The decision prompt should allow `none` and should not invent actions outside `scripts/actions.py`.
- The learned profile prompt should stay structured and compact.
- Generated names should be filesystem-safe and stable.

## Boundaries

- Do not overwrite existing skills silently.
- Keep generated skills under `skills/custom/`.
- Do not create additional files outside the skill package.
