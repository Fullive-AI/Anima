---
name: Workday 8AM Smart Speaker Wakeup
description: A recurring automated skill that triggers a wake-up alarm via connected smart speaker at 8 AM local time on workdays and skips alarms on holidays
metadata:
  device_types:
    - smart_speaker
---

## Goal
Reliably wake the user at 8 AM on workdays via their connected smart speaker without disturbing the user on holidays.

## Load These Resources
1. User's current local time and date data
2. Accurate up-to-date holiday calendar for the user's location
3. Authorized access to the user's connected compatible smart speaker

## Working Rules
### Trigger
Automatically triggers at 8:00 AM user local time every day to check the date type.

### Core Workflow
1. Check if the current date is a workday (not a holiday) per the user's regional holiday calendar
2. If the date is a workday: Send an alarm activation command to the connected smart speaker to play the wake-up alarm
3. If the date is a holiday: Skip all alarm activation and take no further action

### Hard Constraints
1. Never trigger a wake-up alarm on holidays
2. Only trigger the alarm at 8 AM user local time
3. Alarm can only be output via the user's connected smart speaker

### Success Criteria
1. Wake-up alarm plays via the smart speaker at 8 AM on all workdays
2. No wake-up alarm is triggered on any holidays
3. Alarm output is always delivered through the user's smart speaker as requested