# Speaker Device System Skill Reference

## Domain Background
This is an auto-generated system skill for the Anima platform, designed to handle reasoning and control for speaker devices including examples like the Xiaomi Smart Speaker.

## Core Knowledge
1.  The target device type is strictly `speaker`, and only the actions exposed in the device capability list may be used.
2.  When context is insufficient to make a confident, safe decision, prefer a no-op (do nothing) behavior.
3.  Avoid sending redundant commands if the device's recent interaction history shows it was just adjusted.
4.  All emitted actions and their parameters must strictly adhere to the device's exposed capabilities as the hard boundary.
5.  If the user asks to play music but does not provide a specific file path or URL, prefer `play_random_audio` when that capability is available.
6.  If the user asks to stop playback, prefer `stop_audio` when that capability is available.

## Hard Operating Rules
1.  Return `none` if the current context is missing or ambiguous, do not execute unconfirmed actions.
2.  Do not invent or use any actions that are not defined in the skill's `scripts/actions.py` file.
3.  Do not repeat materially identical commands if the device was recently adjusted in the interaction history.
4.  Always respect the device's reported capability list and any associated parameter bounds from the device integration.

## Learning Priorities
1.  Identifying which actions users repeatedly prefer for their speaker devices
2.  Detecting if user behavior shifts based on time of day or room occupancy patterns
3.  Recognizing consistent user preferences for specific speaker modes or targets over others
