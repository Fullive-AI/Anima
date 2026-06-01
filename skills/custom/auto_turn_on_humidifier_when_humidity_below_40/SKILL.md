---
name: custom_skill_bde0ceda
description: Automatically activates the connected humidifier and sets its target humidity to 50% when indoor humidity drops below 40% RH
metadata:
  device_types:
    - humidity_sensor
    - smart_humidifier
---

## Goal
Maintain indoor humidity above 40% at a comfortable level by automatically triggering the humidifier when humidity drops too low.

## Load These Resources
- A working connected humidity sensor that provides accurate real-time indoor humidity readings
- A connected smart humidifier that supports remote control of power state and target humidity settings

## Working Rules
### Trigger Condition
This skill activates when the measured indoor humidity drops strictly below 40% relative humidity. It continuously monitors humidity to check for this threshold.

### Core Actions
1. Monitor real-time indoor humidity level from the connected sensor
2. When humidity is confirmed to be below 40%, turn on the connected smart humidifier
3. Set the humidifier's target humidity to exactly 50%

### Hard Constraints
- Do not activate the humidifier if indoor humidity is 40% or higher
- Always set target humidity to exactly 50% every time the skill triggers

### Success Criteria
- Humidifier is automatically turned on when indoor humidity drops below 40%
- The humidifier's target humidity is correctly set to 50% after activation