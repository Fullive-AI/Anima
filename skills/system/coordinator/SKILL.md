---
name: coordinator
description: Use when coordinating multiple devices in Anima. Covers conflict detection, synergy planning, and structured multi-device actions across humidifiers, AC units, lights, and related devices.
metadata:
  device_types:
    - coordinator
  version: 0.1.0
---

# Coordinator

Use this skill for cross-device orchestration when multiple devices should be considered together.

## Load These Resources

- `references/knowledge.md` for interaction rules and system-wide priorities.
- `references/orchestrate.md` when generating a multi-device action plan.

## Working Rules

- Resolve conflicts before optimizing comfort.
- Prioritize safety, then comfort, then energy efficiency.
- Prefer a short list of coordinated actions over noisy micro-adjustments.
