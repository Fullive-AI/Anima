# Speaker Device Learning Reference
This document tracks learned user behavior for `speaker` type devices, leveraging interaction history `{history}` and user profile `{current_profile}` to optimize skill responses.

```json
{
  "stable_preferences": {
    "preferred_actions": [],
    "favored_activation_times": [],
    "consistent_device_targets": [],
    "confidence_score": 0.0
  },
  "time_based_patterns": {
    "peak_usage_windows": [],
    "occupancy_correlated_usage": false,
    "day_of_week_preferences": [],
    "confidence_score": 0.0
  },
  "seasonal_patterns": {
    "seasonal_usage_shifts": false,
    "special_event_triggers": [],
    "confidence_score": 0.0
  },
  "weak_signals": [
    "Ambiguous user requests related to unsupported speaker controls (outside turn_on/turn_off)",
    "Infrequent interaction entries in {history}"
  ],
  "confidence_notes": "Current learning data is limited. Follow hard rules: return none if context is missing/ambiguous, only use supported actions (turn_on, turn_off), avoid redundant commands per recent history, and use safe no-op behavior when context is insufficient."
}
```