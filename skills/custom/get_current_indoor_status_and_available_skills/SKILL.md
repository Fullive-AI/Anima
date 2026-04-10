---
name: get_current_indoor_status_and_available_skills
description: Retrieves and clearly presents currently available activated Anima skills and up-to-date indoor status from connected sensors per user request
metadata:
  device_types:
    - indoor_environment_sensor
    - smart_home_hub
---

## Goal
Fully address user requests for current indoor status and available Anima skills by correctly listing activated skills for the user's setup and accurately reporting available sensor data.

## Trigger
This skill activates when a user asks about current indoor space status and inquires about currently available relevant Anima skills.

## Load These Resources
1. Synced list of currently activated, available Anima skills for the user's specific setup
2. Up-to-date measurement data from connected indoor environment sensors (if available)
3. User's original request context

## Working Rules
1. Only list skills that are currently activated and available for the user's setup; never list unactivated/unavailable skills
2. Only report indoor status values directly measured by connected sensors; do not guess values for unmeasured metrics
3. Only include information relevant to current indoor status and available Anima skills; exclude irrelevant off-topic content
4. Compile all collected information and present it clearly to the user

## Success Criteria
- All currently available Anima skills for the user's setup are correctly listed
- All available indoor status data is reported accurately with no guessed unmeasured values
- The user's full request for current indoor status and available skills is completely addressed