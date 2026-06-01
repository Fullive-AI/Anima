# Decision Logic for Leave Home Air Purifier Shutoff Skill
## Context Inputs
The decision process uses the following provided variables:
- `{current_data}`: Includes real-time home occupancy status, connected air purifier's power state and connectivity status
- `{capabilities}`: Lists supported device control actions, including the `turn_off` action for air purifier devices
- `{user_preferences}`: Contains user's automation preferences and device usage habits
- `{learned_profile}`: Stores the user's historical home departure and return patterns
- `{recent_history}`: Records recent occupancy events and air purifier operational history
- `{knowledge}`: Includes validated rules for home departure detection and remote air purifier control

## Decision Workflow
1.  **Validate Home Departure**
    Use `{knowledge}`, `{recent_history}`, and `{learned_profile}` to confirm the user has left their home. If departure is not confirmed, return action `none`.
2.  **Check Purifier Power State**
    Retrieve the air purifier's current power status from `{current_data}`. If the purifier is already powered off, return action `none`.
3.  **Verify Action Support**
    Confirm the `turn_off` action is available for the connected air purifier via `{capabilities}`. If not supported, return action `none`.
4.  **Execute Valid Action**
    If all preceding checks pass, return the `turn_off` action for the connected air purifier.