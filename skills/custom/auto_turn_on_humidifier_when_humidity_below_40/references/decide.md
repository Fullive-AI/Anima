# Decision Logic: Auto Turn On Humidifier When Humidity Below 40%

## Input Context
The following context variables are used for all decision making:
- Current real-time environment and device data: `{current_data}`
- Available capabilities of connected smart devices: `{capabilities}`
- Saved user automation preferences: `{user_preferences}`
- Learned user behavior and comfort profile: `{learned_profile}`
- Recent device state and automation trigger history: `{recent_history}`
- Stored domain knowledge for indoor humidity regulation: `{knowledge}`

## Core Decision Rules
1. Extract the latest valid indoor humidity reading from the connected humidity sensor in `{current_data}`.
2. Check the trigger condition: confirm if the current indoor humidity is strictly lower than 40% RH:
   - If current humidity is 40% RH or higher: Output action `none`
   - If current humidity is strictly below 40% RH: Proceed to capability check
3. Verify that the connected smart humidifier is accessible and supports both required actions (`turn_on` and `set_target_humidity`) listed in `{capabilities}`:
   - If required capabilities are unavailable: Output action `none`
   - If required capabilities are confirmed: Execute the sequence of required actions
4. Per skill hard rules: Override any conflicting humidity settings from `{learned_profile}` or custom preferences in `{user_preferences}` when the trigger condition is met, always set the target humidity to exactly 50%.

## Allowed Actions
The following actions are explicitly permitted for this skill:
- `none`: No action is executed. This is the default output when the trigger condition is not met, or required devices/capabilities are unavailable.
- `turn_on`: Send command to power on the connected smart humidifier.
- `set_target_humidity`: Send command to set the humidifier's target humidity, with the fixed parameter `target_humidity: 50` whenever the skill triggers.