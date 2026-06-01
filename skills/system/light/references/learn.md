Analyze the user's lighting history and update the learned profile.

## History
{history}

## Current Learned Profile
{current_profile}

## Instructions

- Separate stable preferences from weak signals.
- Ignore one-off behavior unless it repeats.
- Mention uncertainty when the data is sparse or inconsistent.
- Keep the output compact and machine-readable.
- Treat extracted long-term memories as evidence only when their status is confirmed.
- Candidate memories are weak hints only. Do not promote candidate memories into stable_preferences.
- Rejected or stale memories must be ignored.
- Do not convert one-off behavior from recent history into stable_preferences.
- Use stable_preferences only for explicit user preferences or repeated behavior supported by confirmed memories or enough consistent history.
- Put weak, sparse, or one-off signals into weak_signals, or leave the current_profile unchanged.
- If the new evidence conflicts with current_profile, mention the uncertainty in confidence_notes instead of overwriting stable preferences aggressively.
- Do not infer a brightness, color temperature, or room-specific lighting preference from a single turn_on action.
- Night lighting preferences should require explicit user preference or repeated confirmed night-time evidence.

Respond with a JSON object:

```json
{{
  "stable_preferences": [
    "clear preference statements backed by repeated history"
  ],
  "time_based_patterns": [
    "patterns tied to time of day, routines, or activities"
  ],
  "seasonal_patterns": [
    "patterns tied to season, daylight, or weather"
  ],
  "weak_signals": [
    "possible preferences that need more evidence"
  ],
  "confidence_notes": "short note about certainty and data quality"
}}
```
