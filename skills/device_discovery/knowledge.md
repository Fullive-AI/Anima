# Device Discovery Skill — Domain Knowledge

## Discovery Modes
- Local LAN scan can find some Xiaomi devices by IP and model, but may not have valid tokens.
- Xiaomi QR login via Mi Home is the most reliable onboarding path for fetching full device metadata and tokens.
- If the user mentions customer onboarding, QR code flow is usually the right first step.

## When To Use QR Login
- The user wants to connect Xiaomi or Mi Home devices.
- The user says scanning requires a customer to scan a QR code.
- Local scans find devices that still need token activation.

## When To Use Local Scan
- The user asks to rescan or refresh currently reachable devices on the LAN.
- The user wants a quick inventory without customer interaction.

## Response Style
- Be explicit about whether you are generating a QR code or running a local scan.
- If QR login starts successfully, tell the user to open Mi Home and scan the code.
- If a local scan completes, summarize how many devices were newly found and total known devices.
