# Custom Skill: Turn Off Connected Air Purifier After Home Departure

## Domain Knowledge
User home departure status is detected via occupancy sensors or the user's mobile app state (such as geofence-based away detection or manual "away" mode activation). Compatible air purifiers support remote power-off control through standard smart home integration protocols.

## Safe Operating Goals
1. Only execute the air purifier turn-off action after confirming the user has left home, to prevent unintended device shutdowns while the user is still present.
2. Skip the turn-off action if the air purifier is already powered off, avoiding redundant device interactions and unnecessary network communications.

## Important Context
This skill is exclusively supported for air purifier devices. The trigger is strictly tied to the user's confirmed home departure event, and does not respond to manual user commands or other automated events.