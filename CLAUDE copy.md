# Anima — Make Every Hardware Intelligent

## Quick Start
cd anima && uv sync
cp .env.example .env  # fill in LLM_API_KEY
docker compose up mqtt -d  # start MQTT broker
uv run python -m core.main  # start Anima

## Test
cd anima && uv run pytest tests/ -v

## Architecture
Thin Core (single asyncio process) + MQTT device layer.
See docs/plans/2026-03-17-anima-design.md for full design.
Read `ARCHITECTURE_GUARDRAILS.md` and `ARCHITECTURE_GUARDRAILS.zh-CN.md` before making architectural or cross-module changes.

## Key Directories
- core/          — Core process (brain, events, rules, memory, scheduler, api)
- adapters/      — Device adapters (miot, matter, homeassistant)
- skills/        — AI Skill packages (humidifier, air_conditioner, light)
- data/          — Runtime data (memory, config) — persisted via Docker volume
- tests/         — Test suite
