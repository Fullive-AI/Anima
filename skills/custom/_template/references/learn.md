Analyze the user's history for this custom device and update the learned profile.

Replace generic wording with patterns that matter for your device type.

## History
{history}

## Current Learned Profile
{current_profile}

## Instructions

- Separate stable preferences from weak signals.
- Ignore one-off behavior unless it repeats.
- Mention uncertainty when the data is sparse or inconsistent.
- Keep the output compact and machine-readable.

When customizing this file, think about:

- Does the device have time-of-day behavior
- Does it have seasonal behavior
- Are there mode preferences worth learning
- Is there any reason not to learn from some history entries

Respond with a JSON object:

```json
{{
  "stable_preferences": [
    "clear preference statements backed by repeated history"
  ],
  "time_based_patterns": [
    "patterns tied to time of day or routines"
  ],
  "seasonal_patterns": [
    "patterns tied to season, weather, or other longer cycles"
  ],
  "weak_signals": [
    "possible preferences that need more evidence"
  ],
  "confidence_notes": "short note about certainty and data quality"
}}
```

Example:

```json
{
  "stable_preferences": ["user usually targets 45% after 10pm"],
  "time_based_patterns": ["lower output during work hours"],
  "seasonal_patterns": ["prefers higher target during winter heating season"],
  "weak_signals": ["may prefer quiet mode on weekends"],
  "confidence_notes": "moderate confidence from 18 relevant history entries"
}
```
