# Air Purifier Skill Learning Reference
## Learning Context
Uses interaction history `{history}` and user profile `{current_profile}` to derive usage patterns for `air_purifier` devices.

## Structured Learning Metrics
```json
{
  "stable_preferences": "Consistently repeated user actions, preferred modes, and fan levels pulled from {history} and aligned with supported air_purifier actions: on, off, set_mode, set_fan_level. Excludes ambiguous or one-off commands.",
  "time_based_patterns": "Temporal usage trends identified from timestamped {history} entries, correlated with {current_profile} occupancy and daily routines (e.g., auto-mode activation at morning commute start, power off at bedtime).",
  "seasonal_patterns": "Seasonal shifts in device usage tied to {current_profile} environmental context and {history} data (e.g., high-f