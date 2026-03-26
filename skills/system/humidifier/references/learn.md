Analyze the user's humidifier or dehumidifier history and update the learned profile.

## History
{history}

## Current Learned Profile
{current_profile}

## Instructions

- Separate stable preferences from weak signals.
- Ignore one-off behavior unless it repeats.
- Mention uncertainty when the data is sparse or inconsistent.
- Keep the output compact and machine-readable.

Respond with a JSON object:

```json
{{
  "stable_preferences": [
    "clear preference statements backed by repeated history"
  ],
  "time_based_patterns": [
    "patterns tied to sleep, morning, evening, or other time windows"
  ],
  "seasonal_patterns": [
    "patterns tied to season, weather, or heating/AC usage"
  ],
  "weak_signals": [
    "possible preferences that need more evidence"
  ],
  "confidence_notes": "short note about certainty and data quality"
}}
```
