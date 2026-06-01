---
name: your-skill-name
description: Use when reasoning about your custom device type in Anima. Replace this text with when the skill should trigger and what actions it can produce.
metadata:
  device_types:
    - your_device_type
  version: 0.1.0
---

# Your Skill

This folder is a starter template for a user-authored Anima skill.

Before you use it:

1. Copy `_template/` to `skills/custom/<your-skill-name>/`
2. Rename `name:` to a real skill name
3. Replace `your_device_type` with the device type your adapter emits
4. Update the references and scripts below

## What This Skill Must Define

- When the skill should be used
- Which device types it supports
- What actions it is allowed to emit
- What counts as a safe no-op
- How preferences should be learned over time

## Load These Resources

- `references/knowledge.md` for domain rules, comfort ranges, and device interactions.
- `references/decide.md` when generating a single-device action.
- `references/learn.md` when updating the learned profile from usage history.
- `scripts/actions.py` for the runtime action helpers exposed to Anima.

## Working Rules

- Keep the description in frontmatter concrete so the skill is easy to trigger.
- Only expose actions in `scripts/actions.py` that the target adapter can execute.
- Prefer narrow, conservative decisions over broad generic prompts.

## Fill-In Checklist

- Frontmatter:
  Replace `your-skill-name` with a lowercase stable id such as `fan` or `plant_watering`.
- `metadata.device_types`:
  Must match the `device.type` values your adapter produces.
- `references/knowledge.md`:
  Add real target ranges, risk conditions, and interactions.
- `references/decide.md`:
  Keep the output schema strict. Do not let the model invent actions.
- `references/learn.md`:
  Keep the output structured. Avoid free-form essays.
- `scripts/actions.py`:
  Only keep helpers that are valid for your device.

## Common Mistakes

- Using action names that no adapter actually supports
- Forgetting to define when the correct decision is `none`
- Writing vague descriptions like "smart control for devices"
- Mixing multiple unrelated device types into one skill
