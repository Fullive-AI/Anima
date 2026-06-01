# Device Discovery Skill — Domain Knowledge

## Discovery Modes

- Local LAN scan can find reachable Xiaomi devices by IP and sometimes by model, but may still miss valid tokens
- Xiaomi QR login through Mi Home is the most reliable way to fetch full metadata and usable tokens
- If onboarding depends on a customer scanning a code, QR login is usually the right first step

## When To Use QR Login

- The user wants to connect Xiaomi or Mi Home devices
- The user explicitly asks for a QR code or scan flow
- Local discovery found devices that still need token activation

## When To Use Local Scan

- The user asks for a refresh or rescan of the current LAN
- The user wants a quick reachable-device inventory without customer interaction

## Response Style

- State clearly whether Anima is generating a QR code or running a local scan
- If QR login starts, instruct the user to open Mi Home and scan the code
- If a local scan completes, summarize new devices and total known devices
