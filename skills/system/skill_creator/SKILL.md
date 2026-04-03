---
name: skill_creator
description: Use when the user asks Anima to create, generate, scaffold, or customize a new skill package from a natural-language requirement.
metadata:
  device_types:
    - skill_creator
  version: 0.1.0
---

# Skill Creator

Use this skill for turning a user request into a new custom skill package under `skills/custom/`.
Work analysis-first: extract the repeatable workflow, trigger, inputs, constraints, and success criteria before generating any files.

## Load These Resources

- `references/knowledge.md` for packaging rules and generation constraints.
- `references/chat.md` when deciding whether to create a new skill from user chat.
- `scripts/actions.py` for the runtime file-generation workflow.

## Working Rules

- Generate skills only inside `skills/custom/`.
- Preserve the same package shape as built-in skills: `SKILL.md`, `references/`, and optional `scripts/`.
- Prefer clear, conservative skills over overly broad generic automations.
- If the request is ambiguous, ask for clarification instead of generating a vague skill.
- Keep the generated skill aligned across all files: the trigger, supported actions, no-op boundary, and learned preferences must describe the same workflow.
