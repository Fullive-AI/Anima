---
name: air_purifier
description: Provides reasoning and control capabilities for air purifier devices within the Anima platform.
metadata:
  device_types:
    - air_purifier
---
This skill is intended for use with Anima platform air purifier devices, including models like the Mijia Smart Air Purifier 5. Use this skill when processing user requests to interact with or adjust settings for connected air purifier hardware.

Relevant files in this skill package include:
- `actions.py`: Contains the implemented supported device actions and their parameter constraints
- Core skill logic files that enforce the specified safe operation, non-redundant command, and context-aware rules.