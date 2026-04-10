# Decision Logic: Get Current Indoor Status and Available Skills

## Input Context
| Variable | Description |
|----------|-------------|
| `{current_data}` | Raw user request about current indoor status and available Anima skills |
| `{capabilities}` | Official list of currently activated available Anima skills for the user's setup |
| `{user_preferences}` | Stored user preferences for information presentation and smart home settings |
| `{learned_profile}` | Learned user profile data for request interpretation |
| `{recent_history}` | Recent user interaction history related to skill and indoor status queries |
| `{knowledge}` | Base domain knowledge for Anima smart home services |

## Allowed Actions
- `retrieve_available_skills`
- `collect_indoor_sensor_data`
- `present_compiled_information`
- `none`

## Decision Rules
1. **When no valid activated skill data or connected indoor sensor data is available**:
   - Selected action: `none`
   - Outcome: Inform the user that no required data is currently available to fulfill the request.

2. **When sufficient data is available to fulfill the user request**:
   1. First execute `retrieve_available_skills` to pull the full accurate list of activated available skills
   2. Next execute `collect_indoor_sensor_data` to collect up-to-date indoor status data from connected sensors
   3. Finally execute `present_compiled_information` to compile and present information following all constraints:
      - Only list skills confirmed as activated and available from `{capabilities}`
      - Only report indoor status values measured by connected sensors, never guess unmeasured values
      - Only include information relevant to the user's request for current indoor status and available skills

3. **Mandatory Constraints**:
   - Do not list any skills that are not activated and available for the user's specific setup
   - Do not report any indoor status values that are not obtained from connected sensors
   - Do not add any irrelevant information outside the scope of the user's request