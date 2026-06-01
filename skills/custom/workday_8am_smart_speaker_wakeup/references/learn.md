# Learning Log: Workday 8AM Smart Speaker Wakeup Skill

## Core Learning Input Context
All training and updates for this skill must ingest the following required context variables:
- Full user interaction and trigger history: `{history}`
- Current user profile, location calendar, and connected device state: `{current_profile}`

## Required Structured Output Schema
All learned insights for this skill must be output as structured JSON containing the following top-level fields:
| Field | Description |
|-------|-------------|
| `stable_preferences` | Array of confirmed, persistent user preferences and hard requirements from the skill specification |
| `time_based_patterns` | Array of validated recurring time-based patterns for alarm scheduling |
| `seasonal_patterns` | Array of seasonal/annual variations to the user's workday/holiday schedule (e.g. regional public holiday shifts, custom annual vacation) |
| `weak_signals` | Array of unconfirmed potential pattern observations that require additional interaction data to validate |
| `confidence_notes` | Object mapping each learned insight to a 0-1 confidence score and supporting justification for the score |

---

## Example Valid Learned Insight Structure
```json
{
  "stable_preferences": [
    "Wakeup alarm may only trigger at 8:00 AM user local time",
    "Wakeup alarm must only be output via the user's connected smart speaker",
    "No alarm may be activated on any holiday",
    "User requires alarm only on workdays"
  ],
  "time_based_patterns": [
    "Alarm check trigger runs daily at 8:00 AM user local time",
    "Standard workdays fall on Monday-Friday not marked as holidays per user's regional calendar"
  ],
  "seasonal_patterns": [
    "Public holidays follow the official regional calendar for the user's saved location",
    "Custom user holidays (personal vacation, time off) follow dates explicitly saved in the user profile"
  ],
  "weak_signals": [
    "No unconfirmed pattern observations have been detected to date"
  ],
  "confidence_notes": {
    "8AM trigger time requirement": 1.0,
    "No alarm on holidays requirement": 1.0,
    "Smart speaker only output requirement": 1.0
  }
}
```

---

## Prioritized Learning Focus
Per skill specification, the learning system should prioritize improving performance on:
1. Accurate classification of workdays vs holidays aligned with the user's location and custom calendar
2. Precise timing of alarm activation exactly at 8:00 AM user local time
3. Consistent and reliable alarm suppression on all holidays
4. Reliable command delivery to the user's connected smart speaker