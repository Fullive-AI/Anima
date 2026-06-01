---
name: light
description: Use when reasoning about smart lights in Anima. Covers circadian brightness and color-temperature heuristics, smooth transitions, and choosing `set_brightness`, `set_color_temp`, `turn_on`, or `turn_off`.
metadata:
  device_types:
    - light
    - ceiling_light
    - desk_lamp
    - led_strip
  version: 0.1.0
---

# Light

Use this skill for device-level lighting decisions and preference learning.

## Load These Resources

- `references/knowledge.md` for circadian lighting rules and energy heuristics.
- `references/decide.md` when generating a single-device action.
- `references/learn.md` when summarizing long-term lighting preferences.
- `scripts/actions.py` for the structured action helpers exposed to the runtime.

## Working Rules

- Prefer smooth transitions over abrupt jumps.
- Treat time of day as a primary signal for brightness and color temperature.
- If current lighting is already reasonable, return `none`.
