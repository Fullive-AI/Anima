# Planner Hints

These hints are part of Anima's top-level planner policy.

- Call `humidifier` when current humidity is below 50% and the environment is not already comfortable.
- Call `air_conditioner` when temperature is clearly outside the comfortable range and the change is meaningful.
- Call `light` when brightness or color temperature is mismatched with time of day or user preference.
- Prefer no action when the current state is already acceptable.
