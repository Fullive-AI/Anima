# Air Purifier Skill Decision Reference
## Available Context Variables
- `{current_data}`: Current real-time state and telemetry of the target air purifier device
- `{capabilities}`: Official exposed device capabilities, allowed parameter bounds, and supported action list
- `{user_preferences}`: Stored user-defined device operation preferences
- `{learned_profile}`: Auto-generated behavioral pattern data for the user and device
- `{recent_history}`: Recent command and state change history for the device to prevent redundant actions
- `{knowledge}`: Static skill knowledge base including core rules and supported actions

## Permitted Actions
Only the following actions from `scripts/actions.py` are valid for decision output:
1. `on`: Power on the air purifier (no required parameters)
2. `off`: Power off the air purifier (no required parameters)
3. `set_mode`: Configure device operating mode, requires a string `mode` parameter validated against {capabilities}
4. `set_fan_level`: Adjust device fan speed level, requires a numeric `level` parameter validated against {capabilities}
5. `none`: No action will be emitted (valid fallback for ambiguous/missing context, redundant changes, or no