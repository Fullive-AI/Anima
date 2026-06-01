# Domain Knowledge for Workday 8AM Smart Speaker Wakeup Skill

## Domain Knowledge
This skill is a personalized recurring home automation alarm service for workday morning wake-up, built on the following core knowledge domains:
1. **Workday and Holiday Classification**
   - Workdays for this skill are defined as non-holiday days per the user's local regional holiday calendar. All public holidays (regardless of their weekday position) are classified as days that require no alarm.
   - Accurate date classification relies on up-to-date regional holiday calendar data aligned with the user's location to ensure correct activation logic.
2. **Time-Based Recurring Trigger Scheduling**
   - The skill automatically runs a date check every day at exactly 8:00 AM user local time.
   - Accurate local time synchronization is required to ensure any alarm activation happens at the exact requested time.
3. **Connected Smart Speaker Remote Control**
   - The skill communicates with the user's pre-linked compatible smart speaker to send standardized alarm activation commands.
   - All alarm output is restricted to the connected smart speaker per user requirements.

## Safe Operating Goals
The core operating goals and non-negotiable constraints for this skill are:
### Core Operating Goals
1. Reliably trigger the wake-up alarm through the user's connected smart speaker at 8:00 AM local time on all workdays, to help the user wake up on time for work.
2. Avoid any alarm activation on holidays to prevent unwanted disturbance to the user's rest.
3. Only use the user's connected smart speaker as the alarm output channel, matching the user's explicit request.

### Hard Safety Rules
1. Never trigger a wake-up alarm on any confirmed holiday, under any circumstance.
2. Only trigger the alarm at 8:00 AM user local time; no off-schedule alarm activation is allowed.
3. Alarm output can only be delivered via the user's connected smart speaker; no other output channels will be used.

## Important Context and Operating Assumptions
1. The user has a compatible connected smart speaker already linked to this skill, and the speaker remains powered and connected to the network at the time of scheduled triggering.
2. The skill has access to up-to-date, accurate regional holiday information for the user's current location to correctly classify workdays and holidays.
3. The user has pre-configured an appropriate alarm volume on their smart speaker that is sufficient to wake them.
4. The skill relies on accurate local time synchronization to trigger the date check and alarm at the correct requested time.