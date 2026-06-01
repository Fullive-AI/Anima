# Your Skill — Domain Knowledge

Replace every placeholder in this file. This file should contain domain facts, not prompt instructions.

## Device Purpose

- Describe what problem this device solves.
- Define the main comfort or control targets.

Example:

- A fan improves comfort when the room feels warm but AC is unnecessary.
- Typical comfort target is air movement before active cooling.

## Operating Heuristics

- List the normal target ranges.
- Note any seasonal, time-based, or occupancy-based adjustments.
- Mention relevant interactions with other devices.

Example fields to think through:

- Preferred range
- Night behavior
- Energy-saving behavior
- Interaction with AC, windows, humidity, or occupancy

## Guardrails

- Describe unsafe states or situations where the device should not act.
- Note cooldown expectations or reasons to avoid oscillation.

Example:

- Do not turn on if the device reports low battery or fault state.
- Do not send repeated mode changes within 10 minutes unless conditions changed materially.
