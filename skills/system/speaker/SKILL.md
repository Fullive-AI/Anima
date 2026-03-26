---
name: speaker
description: Handles reasoning and control for speaker devices in the Anima platform.
metadata:
  device_types:
    - speaker
---

# Speaker Device Skill

This skill manages control and reasoning for speaker devices such as Xiaomi Smart Speaker within the Anima platform. Use this skill when processing user requests related to speaker power operations.

Key relevant files:
- `actions.py`: Implements the supported `turn_on` and `turn_off` actions for speaker devices.
- Follow the defined hard rules and knowledge points to ensure safe, non-redundant, and capability-aligned device interactions.