# Air Purifier System Skill Knowledge Base

## Domain Overview
This system skill provides control and reasoning capabilities for `air_purifier` type devices, including examples such as the Mijia Smart Air Purifier 5, within the Anima platform.

## Core Domain Knowledge
1. The supported device actions are strictly limited to: `on`, `off`, `set_mode`, and `set_fan_level`.
2. When context is insufficient to determine user intent, use a safe no-op (no action) behavior.
3. Avoid sending redundant control commands if recent device history shows the device was recently adjusted.
4. All emitted actions and parameters must adhere strictly to the device's exposed capabilities and defined bounds.

## Hard Operational Rules
- Return `none` if the current context is missing or ambiguous.
- Do not invent or use any actions not defined in the skill's `actions.py` script.
- Do not repeat identical or materially identical commands when recent device adjustment history exists.
- Always respect the device's published capability list and parameter value bounds.

## Learning Focus Areas
- Identify which device actions are repeatedly preferred by the user
- Detect if user behavior changes based on time of day or occupancy patterns
- Track consistently favored operating modes or fan level targets