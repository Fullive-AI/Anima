---
name: air_conditioner
description: Use when reasoning about air conditioners in Anima. Covers comfort temperature ranges, energy heuristics, humidity interaction, and choosing `set_temperature`, `set_mode`, `turn_on`, or `turn_off`.
metadata:
  device_types:
    - air_conditioner
  version: 0.1.0
---

# Air Conditioner

Use this skill for device-level cooling and heating decisions plus preference learning.

## Load These Resources

- `references/knowledge.md` for comfort temperatures, energy heuristics, and device interaction rules.
- `references/decide.md` when generating a single-device action.
- `references/learn.md` when updating the learned profile from usage history.
- `scripts/actions.py` for the structured action helpers exposed to the runtime.

## Working Rules

- Optimize for comfort without ignoring energy cost.
- Treat humidity side effects as part of the decision, not a separate concern.
- Prefer no-op over unnecessary cycling near the target range.
