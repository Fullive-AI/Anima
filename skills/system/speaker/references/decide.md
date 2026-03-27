# Speaker Device Decision Logic Reference

## Decision Workflow
1.  **Context Validation**
    Confirm {current_data}, {capabilities}, {recent_history}, and {user_preferences} are complete and unambiguous. If context is missing or ambiguous, return `none`.
2.  **Base Knowledge Application**
    Use {knowledge} to enforce rules:
    - Only supported actions are those present in the current device capability list
    - Prefer `none` when context is insufficient
    - Skip redundant commands if {recent_history} shows recent device adjustment
    - All actions must respect {capabilities} bounds
3.  **Learned Pattern Integration**
    Incorporate {learned_profile} and {user_preferences} to identify:
    - Repeatedly preferred user actions
    - Time/occupancy tied behavior shifts
    - Consistently favored device settings
4.  **Recent History Check**
    Avoid emitting materially identical commands if {recent_history} indicates the device was recently adjusted.
5.  **Capability Compliance**
    Validate all proposed actions exist in `scripts/actions.py` and match {capabilities} constraints. Only use allowed actions.
6.  **Final Output**
    Return exactly one of:
    - A valid supported action such as `play_random_audio`, `stop_audio`, `play_audio_file`, `play_audio_url`, `turn_on`, or `turn_off`
    - `none` if no valid action can be determined
