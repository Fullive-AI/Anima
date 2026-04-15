<div align="center">

<!-- <img src="./assets/logo.png" alt="Anima Logo" width="200"> -->

# Anima

### Make Every Hardware Intelligent

An open-source **Agentic AI OS** for hardware — auto-discovers devices, gives each one an AI brain, and lets them autonomously sense, decide, and evolve.

[English](./README.md) | [中文](./README.zh-CN.md)

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](./LICENSE)
[![CI](https://github.com/fulai-tech/Anima/actions/workflows/ci.yml/badge.svg)](https://github.com/fulai-tech/Anima/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](./docker-compose.yml)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/fulai-tech/Anima)

<!-- <img src="./assets/demo.gif" alt="Anima Dashboard Demo" width="800"> -->

**[Quick Start](#quick-start)** · **[Architecture](#architecture)** · **[Skill System](#skill-system)** · **[Contributing](#contributing)** · **[Roadmap](#roadmap)** · **[Changelog](./CHANGELOG.md)**

</div>

---

## Why Anima?

Most smart-home systems are dumb remotes — they toggle switches and follow rigid schedules. Anima is different.

**Anima** (Latin for _"soul"_) breathes real intelligence into your hardware. Instead of asking _"what rules should I set?"_, Anima asks **_"what do you have? I'll figure it out."_**

### Three Core Superpowers

<table>
<tr>
<td width="33%" align="center">
<h3>🧠 Skill-Driven AI Brain</h3>
<p>Each device type gets <strong>specialized domain knowledge</strong> — not just on/off control. A humidifier knows about comfort ranges, seasonal adjustments, and AC interactions. A light understands circadian rhythms. The AI Brain loads these skills and makes autonomous decisions.</p>
</td>
<td width="33%" align="center">
<h3>🔌 Zero-Config Discovery</h3>
<p><strong>Plug in any device and Anima finds it.</strong> Auto-discovers devices via mDNS, identifies types, loads matching skills, and starts managing — no YAML configs, no manual setup. Works with Xiaomi/MIoT today, Matter and HomeAssistant bridges coming next.</p>
</td>
<td width="33%" align="center">
<h3>🧬 Learns and Evolves</h3>
<p>Anima <strong>remembers your preferences</strong> and evolves over time. It extracts patterns from your decisions, builds preference profiles per device type, and continuously refines its behavior. The more you use it, the smarter it gets.</p>
</td>
</tr>
</table>

---

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                        Anima Core (Single Process)                 │
│                                                                    │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    │
│  │Discovery │───▶│ EventBus │◀───│Scheduler │    │  Memory  │    │
│  │Orchestr. │    │          │    │          │    │  System  │    │
│  └──────────┘    └────┬─────┘    └──────────┘    └────┬─────┘    │
│                       │                               │          │
│  ┌────────────────────┴───────────────────────────────┘          │
│  │                                                               │
│  │         ┌──────────────────────────────┐                      │
│  │         │        LLM Brain             │                      │
│  │         │  ┌────────┐  ┌───────────┐   │                      │
│  │         │  │Planner │  │ Executor  │   │                      │
│  │         │  │(Skills)│  │(LangGraph)│   │                      │
│  │         │  └────────┘  └───────────┘   │                      │
│  │         └──────────────────────────────┘                      │
│  │                                                               │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐            │
│  │  │ REST API │  │   Chat   │  │    Dashboard     │            │
│  │  │ (8080)   │  │  (SSE)   │  │   (Vite/3000)   │            │
│  │  └──────────┘  └──────────┘  └──────────────────┘            │
│  └───────────────────────────────────────────────────────────────│
└──────────────────────────┬─────────────────────────────────────────┘
                           │ MQTT
                    ┌──────┴──────┐
                    │ MQTT Broker │
                    └──┬─────┬───┘
                       │     │
              ┌────────┘     └────────┐
              │                       │
        ┌─────┴─────┐         ┌──────┴──────┐
        │   MIoT    │         │   Virtual   │
        │  Adapter  │         │   Adapter   │
        └───────────┘         └─────────────┘
        Xiaomi Devices         Demo/Testing
```

**Single async Python process** — EventBus + LLM Brain + Scheduler + Memory, all in one. No microservices overhead.

---

## Quick Start

### Prerequisites

- [Node.js](https://nodejs.org/) >= 18 + [pnpm](https://pnpm.io/) >= 8
- [Python](https://www.python.org/) >= 3.11 + [uv](https://docs.astral.sh/uv/)

### Install & Run

```bash
# Clone
git clone https://github.com/fulai-tech/Anima.git
cd Anima

# Install all dependencies (frontend + backend)
pnpm install

# Configure your LLM API key
cp .env.example .env
# Edit .env and set ANIMA_LLM_API_KEY

# Start everything (MQTT broker + backend + dashboard)
pnpm dev
```

Open **http://localhost:3000** — the Anima Dashboard is live.

> **No devices?** No problem — use the Dashboard to add virtual devices for a full demo experience. Click the Chat bar and ask Anima to create devices for you.

### Docker Deployment

```bash
cp .env.example .env  # fill in your API key

docker compose up -d
```

The backend runs on port **8080**. Mount `data/` and `skills/` for persistence.

---

## Configuration

Anima uses environment variables with the `ANIMA_` prefix:

```env
# Required: any OpenAI-compatible API key
ANIMA_LLM_API_KEY=sk-xxx

# Optional: model name (default: gpt-4o)
ANIMA_LLM_MODEL=gpt-4o

# Optional: custom endpoint for DeepSeek / Doubao / Ollama / etc.
ANIMA_LLM_BASE_URL=https://api.deepseek.com/v1

# Optional: disable deep thinking (required for some providers)
ANIMA_LLM_DISABLE_THINKING=false
```

**Supported LLM Providers** (any OpenAI-compatible API):

| Provider | Model | Base URL |
|----------|-------|----------|
| OpenAI | `gpt-4o` | _(leave empty)_ |
| DeepSeek | `deepseek-chat` | `https://api.deepseek.com/v1` |
| Doubao | `doubao-seed-2-0-lite-260215` | `https://ark.cn-beijing.volces.com/api/v3` |
| Anthropic (via proxy) | `claude-sonnet-4-20250514` | your proxy URL |
| Ollama (local) | `llama3` | `http://localhost:11434/v1` |

---

## Skill System

Each Skill teaches Anima **how a device type becomes autonomously intelligent** — not just how to toggle it.

```
skills/
  system/              # Built-in skills shipped with Anima
    humidifier/
      SKILL.md          # Domain knowledge and decision logic
      references/       # Supporting knowledge documents
      scripts/
        actions.py      # Executable skill actions
  custom/              # Your custom skills go here
    _template/          # Copy this to create a new skill
```

### Built-in Skills

| Skill | Intelligence |
|-------|-------------|
| **Humidifier** | Comfort ranges (40-60%), seasonal adjustments, AC coordination, water level alerts |
| **Air Conditioner** | Energy optimization, circadian temperature curves, humidity coordination |
| **Light** | Circadian lighting (2200K–5000K), time-based brightness, smooth transitions |
| **Air Purifier** | Occupancy-aware purification, sleep-time quiet mode, AQI heuristics |
| **Speaker** | Playback-oriented behavior, quiet-hour protection, safe defaults |
| **Coordinator** | Cross-device orchestration — prevents conflicts, creates synergies |
| **Device Discovery** | Automatic scanning and registration of new devices |
| **Skill Creator** | AI-powered generation of custom skills from natural language |

### Write Your Own Skill

```bash
cp -r skills/custom/_template skills/custom/my-skill
# Edit skills/custom/my-skill/SKILL.md
# Restart Anima — it auto-discovers new skills
```

---

## Dashboard

The React Dashboard provides a complete control and monitoring experience:

- **Device List** — live status of all discovered devices with sensor editing and command controls
- **Environment View** — aggregated sensor data across rooms
- **AI Decision Stream** — watch Anima's reasoning in real-time via SSE
- **Unified Chat** — natural language control, device discovery, and skill creation
- **Memory Debugger** — inspect learned preferences and decision history
- **Settings** — LLM config, Xiaomi QR onboarding, device management
- **Virtual Devices** — create demo devices to experience Anima without real hardware

---

## Development

| Command | Description |
|---------|-------------|
| `pnpm install` | Install all dependencies (frontend + backend) |
| `pnpm dev` | Start broker + backend + dashboard together |
| `pnpm dev:frontend` | Dashboard only (port 3000) |
| `pnpm dev:backend` | Python backend only (port 8080) |
| `pnpm dev:broker` | MQTT broker only (port 1883) |
| `pnpm build` | Build dashboard for production |
| `uv run pytest tests/ -v` | Run test suite |
| `uv run ruff check .` | Lint Python code |

### REST API

FastAPI Swagger docs available at `http://localhost:8080/docs` when running.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/api/devices` | List all devices |
| `POST` | `/api/chat` | Unified chat entry |
| `GET` | `/api/environment` | Aggregated sensor snapshot |
| `GET` | `/api/decisions` | AI decision history |
| `GET` | `/api/memory` | Learned preferences and profiles |
| `POST` | `/api/scan` | Trigger device re-scan |

<details>
<summary><strong>Full API Reference</strong></summary>

**Devices**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/devices` | List all devices |
| `GET` | `/api/devices/{device_id}` | Device details |
| `POST` | `/api/devices/{device_id}/command` | Send command to device |
| `POST` | `/api/devices/{device_id}/sensors` | Update sensor values |
| `PATCH` | `/api/devices/{device_id}/rename` | Rename a device |
| `DELETE` | `/api/devices/{device_id}` | Remove a device |
| `PUT` | `/api/devices/{device_id}/room` | Assign device to room |
| `POST` | `/api/devices/add` | Add manual MIoT device |
| `POST` | `/api/devices/{device_id}/activate` | Activate with token |

**Virtual Devices**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/admin/virtual-devices` | Create virtual device |
| `DELETE` | `/api/admin/virtual-devices/{device_id}` | Remove virtual device |

**Rooms**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/rooms` | List rooms |
| `POST` | `/api/rooms` | Create room |
| `PUT` | `/api/rooms/{room_id}` | Update room |
| `DELETE` | `/api/rooms/{room_id}` | Delete room |

**Skills**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/skills` | List all skills |
| `GET` | `/api/skills/custom/{folder_name}` | Get custom skill details |
| `PUT` | `/api/skills/custom/{folder_name}` | Update custom skill |

**Environment & Brain**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/environment` | Aggregated sensor snapshot |
| `POST` | `/api/environment/refresh` | Refresh environment |
| `GET` | `/api/brain/events` | SSE stream of AI decisions |
| `GET` | `/api/onboarding/status` | Check onboarding state |

**Settings & Xiaomi**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/settings` | Dashboard settings |
| `GET` | `/api/settings/xiaomi/status` | Xiaomi cloud status |
| `POST` | `/api/settings/xiaomi/qr/start` | Start QR login |
| `POST` | `/api/settings/xiaomi/qr/poll` | Poll QR login |
| `POST` | `/api/settings/xiaomi/disconnect` | Disconnect Xiaomi |
| `GET` | `/api/settings/llm/status` | LLM config status |
| `POST` | `/api/settings/llm/configure` | Save LLM config |

</details>

---

## Project Structure

```
Anima/
├── core/                       # Python backend
│   ├── brain/                  # LLM Brain (planner + executor + skills)
│   ├── events/                 # Async EventBus
│   ├── memory/                 # Preference learning & storage
│   ├── scheduler/              # Periodic jobs
│   ├── api/                    # FastAPI REST API
│   ├── devices/                # Discovery orchestrator
│   ├── runtime/                # Config, MQTT client, settings store
│   ├── llm/                    # LLM client
│   ├── media/                  # Audio registry & speaker playback
│   └── main.py                 # Entry point
├── adapters/                   # Device protocol adapters
│   ├── miot/                   # Xiaomi MIoT
│   └── virtual/                # Virtual devices (demo/testing)
├── skills/
│   ├── system/                 # Built-in AI skills (8 skills)
│   └── custom/                 # User-created skills
├── dashboard/                  # React + Vite + Tailwind frontend
├── tests/                      # Pytest + Playwright test suite
├── docs/                       # Design documents
├── docker-compose.yml          # Docker deployment
├── pyproject.toml              # Python config
└── package.json                # pnpm monorepo root
```

---

## Roadmap

| Version | Milestone | Status |
|---------|-----------|--------|
| **v0.1** | **"It's Alive"** — Core framework, MIoT adapter, Dashboard, LLM Brain, memory learning, built-in skills, CLI + API, Docker | **Current** |
| v0.2 | **"Getting Smarter"** — Matter adapter, real-time WebSocket, room management, advanced preference learning | Planned |
| v0.3 | **"Community Arrives"** — Skill Store, adapter plugins, Telegram Bot, HomeAssistant bridge | Planned |
| v0.4 | **"Getting Stronger"** — Multi-user, Raspberry Pi image, security hardening | Planned |

---

## Documentation

| Resource | Link |
|----------|------|
| Architecture Design | [`docs/plans/2026-03-17-anima-design.md`](./docs/plans/2026-03-17-anima-design.md) |
| API Reference (Swagger) | `http://localhost:8080/docs` (when running) |
| Contributing Guide | [`CONTRIBUTING.md`](./CONTRIBUTING.md) |
| Security Policy | [`SECURITY.md`](./SECURITY.md) |
| Changelog | [`CHANGELOG.md`](./CHANGELOG.md) |
| Agent Architecture Guide | [`AGENT.md`](./AGENT.md) |

---

## Contributing

We welcome contributions! The easiest ways to start:

- **Write a Skill** — teach Anima about a new device type
- **Write an Adapter** — add support for a new device protocol (3 methods: `discover()`, `subscribe()`, `execute()`)
- **Report bugs** or **suggest features** via [Issues](https://github.com/fulai-tech/Anima/issues)

See [CONTRIBUTING.md](./CONTRIBUTING.md) for full guidelines.

---

## About

Anima is built by [**Fullive.AI**](https://fullive.ai/) (福来数创), a Spatial Agentic AI company backed by Hillhouse Ventures, Mohua Tech, AGIBOT, Peking University Institute, and leading industry partners.

> _We believe environments should proactively evolve to adapt to humans — that is the technological privilege humanity deserves._

Fullive.AI builds Spatial Agentic AI that gives physical spaces the ability to autonomously perceive, decide, execute, and evolve — enabling a new paradigm of seamless human-environment interaction.

---

## License

[Apache License 2.0](./LICENSE) — Anima is free and open source.

---

<!-- [![Star History Chart](https://api.star-history.com/svg?repos=fulai-tech/Anima&type=Date)](https://star-history.com/#fulai-tech/Anima&Date) -->
