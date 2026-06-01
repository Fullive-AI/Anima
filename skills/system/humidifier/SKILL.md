---
name: humidifier
description: Use when reasoning about humidifiers or dehumidifiers in Anima. Covers comfort humidity targets, seasonal heuristics, and choosing `set_humidity`, `set_mode`, `turn_on`, or `turn_off`.
metadata:
  device_types:
    - humidifier
    - dehumidifier
  version: 0.1.0
---

# Humidifier

Use this skill for device-level humidity control and preference learning.

## Load These Resources

- `references/knowledge.md` for comfort bands, device interactions, and guardrails.
- `references/decide.md` when generating a single-device action.
- `references/learn.md` when summarizing long-term preference patterns.
- `scripts/actions.py` for the structured action helpers exposed to the runtime.

## Working Rules

- Prefer gradual target changes over abrupt swings.
- Treat water level, season, sleep context, and AC/heating interaction as first-order signals.
- Return structured actions only from the supported action set in `scripts/actions.py`.
