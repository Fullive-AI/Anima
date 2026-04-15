# Domain Knowledge
## Indoor Humidity Basics
Indoor relative humidity (RH) between 40%-60% is the widely accepted optimal range for human comfort, respiratory health, and protection of indoor property (such as wooden furniture, musical instruments, and houseplants). When indoor humidity drops below 40% RH, it often causes issues including dry skin, irritated airways, increased static electricity, and damage to wood and plants.

## Threshold-Based Smart Home Automation
This skill uses a standard threshold trigger logic for environmental control: it continuously monitors real-time data from a connected humidity sensor, and executes pre-configured control actions only when the measured reading crosses below the set threshold. This is a low-latency, reliable automation pattern for smart home climate regulation.

## Required Device Capabilities
This automation depends on two core connected device types:
1. A working, calibrated humidity sensor that can provide accurate, real-time indoor humidity readings to the smart system
2. A network-connected smart humidifier that supports remote control of power state and remote adjustment of target humidity settings

# Safe Operating Goals
1. Maintain indoor humidity above 40% RH to avoid the discomfort and damage caused by excessively low air humidity
2. Avoid unnecessary energy waste by only activating the humidifier when the humidity meets the trigger condition
3. Stabilize indoor humidity at 50% RH, a balanced comfortable level that avoids over-humidification which can lead to mold or mildew growth
4. Run automatically without repeated manual intervention after initial setup, to maintain consistent indoor humidity conditions

# Important Operational Context & Rules
1. This skill only activates the humidifier when indoor humidity is strictly lower than 40% RH. It will not trigger if the measured humidity is 40% RH or higher.
2. Every time the skill triggers, it will always set the humidifier's target humidity to exactly 50% RH, no other target value is applied.
3. Automation accuracy depends on the calibration and working status of the humidity sensor: faulty or uncalibrated sensors will lead to incorrect trigger behavior.
4. The skill can only control connected smart humidifiers that support remote power and humidity setting adjustment, it cannot operate non-smart or offline humidifiers.