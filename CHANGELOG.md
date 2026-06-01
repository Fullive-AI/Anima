# Changelog

All notable changes to Anima will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-04-15

### Added

- **Core Framework** — Single async Python process with EventBus, Scheduler, Memory, and Rules Engine
- **LLM Brain** — Skill-driven planning and execution pipeline using LangGraph
- **MIoT Adapter** — Xiaomi device discovery (mDNS + cloud), QR-based onboarding, token activation, capability reflection, and command execution
- **Virtual Adapter** — Virtual devices for demo and testing without real hardware
- **Skill System** — Domain knowledge packages for autonomous device intelligence
  - Built-in skills: humidifier, air conditioner, light, air purifier, speaker, coordinator
  - Custom skill support with template and auto-generation
- **REST API** — FastAPI-based API with Swagger docs at `/docs`
- **Dashboard** — React + Vite + Tailwind operator console with device list, environment view, AI decision stream, chat, memory debugger, and settings
- **Memory & Learning** — File-based preference storage, pattern extraction, and profile learning
- **Rules Engine** — Fast-path safety rules with cooldown and threshold logic
- **Docker Deployment** — Docker Compose with Mosquitto broker
- **CI Pipeline** — GitHub Actions with Ruff lint/format, pytest, and frontend build checks
- **Documentation** — README (EN/CN), CONTRIBUTING, SECURITY, AGENT.md, architecture docs
