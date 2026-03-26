---
name: device_discovery
description: Use when a user wants Anima to discover devices, refresh the LAN inventory, or start Xiaomi or Mi Home onboarding with a QR flow.
metadata:
  device_types:
    - assistant
  version: 0.1.0
---

# Device Discovery

Use this skill for discovery-oriented chat tasks and Xiaomi onboarding flows.

## Load These Resources

- `references/knowledge.md` for choosing between local scan and Xiaomi QR onboarding.
- `references/chat.md` when planning the next discovery action from user chat.
- `scripts/actions.py` for executing the chosen scan or onboarding flow.

## Working Rules

- Use Xiaomi QR onboarding when the user needs full Xiaomi or Mi Home account-linked discovery.
- Use local scan for a quick LAN refresh that does not require user interaction.
- Keep replies operational and explicit about the next action.
