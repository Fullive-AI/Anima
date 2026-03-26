# Custom Skill Learning Reference: Leave Home Air Purifier Auto-Shutoff

## stable_preferences
```json
{
  "primary_goal": "Turn off connected air purifiers immediately after the user is confirmed to have left home",
  "device_requirements": ["air_purifier"],
  "user_alignment": "Derived from {current_profile}'s registered smart home air purifier devices and {history} of past manual air purifier power-off actions triggered by home departure",
  "exclusion_rules": "Skip shutoff action if the air purifier is already powered off, per defined hard rules"
}
```

## time_based_patterns
```json
{
  "trigger_windows": "Aligned with {history} of the user's confirmed home departure timestamps and typical daily/weekly leave schedules",
  "exception_adjustments": "Dynamically shifts for irregular leave events detected in {history} such as work-from-home days, late-night departures, or last-minute trips"
}
```

## seasonal_patterns
```json
{
  "usage_alignment": "Tied to {current_profile}'s documented air purifier usage seasons (e.g., allergy season, winter heating season)",
  "trigger_prioritization": "Increases activation priority during peak air purifier usage periods identified in {history}"
}
```

## weak_signals
```json
{
  "pre_confirmation_signals": [
    "User's mobile device disconnects from home Wi-Fi network",
    "Front door lock is disengaged and not re-engaged within 5 minutes",
    "Indoor occupancy sensors detect no movement for 10+ consecutive minutes",
    "User's linked smart calendar shows a scheduled departure event"
  ],
  "confirmation_requirement": "Auto-shutoff only activates after verifying at least two overlapping weak signals to confirm home departure, per hard rules"
}
```

## confidence_notes
```json
{
  "base_confidence": 0.85,
  "confidence_modifiers": {
    "increase": "+0.1 for each confirmed match between weak signals and past departure events logged in {history}",
    "decrease": "-0.45 if only one weak signal is detected with no matching historical departure data in {history}"
  },
  "profile_dependency": "Confidence score is directly tied to {current_profile}'s home occupancy detection setup and air purifier connectivity status"
}
```