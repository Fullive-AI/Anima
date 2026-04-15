# Anima — Make Every Hardware Intelligent

## Quick Start
pnpm install
cp .env.example .env  # fill in ANIMA_LLM_API_KEY
pnpm dev              # starts MQTT broker + backend (port 8080) + frontend (port 3000) together

# Or start individually:
# pnpm dev:broker    — MQTT broker (amqtt)
# pnpm dev:backend   — Python backend only (uv run python -m core.main)
# pnpm dev:frontend  — React dashboard only (port 3000)

## Test
uv run pytest tests/ -v

## Architecture
Thin Core (single asyncio process) + MQTT device layer.
See docs/plans/2026-03-17-anima-design.md for full design.

## Key Directories
- core/          — Core process (brain, events, rules, memory, scheduler, api)
- adapters/      — Device adapters (miot, matter, homeassistant)
- skills/        — AI Skill packages (humidifier, air_conditioner, light)
- data/          — Runtime data (memory, config) — persisted via Docker volume
- tests/         — Test suite
