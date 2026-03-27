[English](./README.md) | [中文](./README.zh-CN.md)

# Anima

**Make Every Hardware Intelligent.**

An open-source Agent OS that auto-discovers your hardware devices, empowers each one with AI Skills, and lets them autonomously sense, decide, and collaborate.

## What is Anima?

**Anima** (Latin for "soul") breathes intelligence into every piece of hardware you own. Instead of asking "what sensors do you need?", Anima asks **"what do you have — I'll use it."**

- Zero configuration — auto-discovers devices on your local network
- AI-driven decisions — LLM Brain loads domain knowledge and makes smart choices
- Skill system — each device type gets specialized intelligence, not just on/off control
- Learns your preferences — evolves over time based on your habits
- Visual Dashboard — real-time device monitoring, AI decision stream, and a unified graph-based chat entry

## 60 Seconds Quick Start

```bash
# Clone and enter project
git clone https://github.com/fulai-tech/Anima.git
cd Anima

# Install dependencies (frontend + backend, one command)
pnpm install

# Configure
cp .env.example .env      # Fill in ANIMA_LLM_API_KEY

# Start MQTT broker
docker compose up mqtt -d

# Start (Dashboard + Backend together)
pnpm dev
```

Open **http://localhost:3000** — you'll see the Anima Dashboard.

### After Launch: Connect Your Devices

1. Click **⚙ Settings** (top-right gear icon)
2. In **LLM Brain** section, enter your API Key and model config (or use .env)
3. In **Xiaomi** section, click **Generate QR Code**
4. Open **Mi Home app** on your phone and scan the QR code
5. Done — all your Xiaomi devices and tokens are fetched automatically

> **Why QR scan?** Tokens are device control keys stored on Xiaomi's cloud servers. Local network scanning can find devices but cannot get tokens. QR login is the most reliable authentication method — no password input, no captcha issues.

Click the **? Help** button (top-right) for a step-by-step guide inside the Dashboard.

### Prerequisites

- [Node.js](https://nodejs.org/) >= 18 + [pnpm](https://pnpm.io/) >= 8
- [uv](https://docs.astral.sh/uv/) (Python package manager, auto-installed by pnpm)
- [Docker](https://www.docker.com/) (for MQTT broker)

## Architecture

```
┌───────────────────────────────────────────┐
│              Core (single process)         │
│                                           │
│  Discovery ──▶ EventBus ◀── Scheduler     │
│                   │                       │
│      Sensor / Chat ──▶ LLM Brain ◀── Memory │
│                   │                       │
│        Dashboard · Chat API · MQTT Client │
└──────────────────┬────────────────────────┘
                   │ MQTT
            ┌──────┴──────┐
            │  Mosquitto  │
            └──┬─────┬────┘
           MIoT    Matter   HA Bridge
          Adapter  Adapter  (v0.2+)
```

## What's Included

| Module | Description |
|--------|-------------|
| **Dashboard** | React + Vite + Tailwind — three-column layout with device list, sensor cards, AI decision stream, chat bar |
| **EventBus** | Async event system with wildcard subscriptions and error isolation |
| **Rules Engine** | Kept in the codebase as an optional deterministic layer, but the current main runtime path routes sensor and chat input through the LLM Brain |
| **LLM Brain** | Skill-driven LangGraph planner/executor — loads skill summaries, plans actions, executes skills, verifies device state, and also serves `/api/chat` |
| **Memory System** | `preferences.md` + `history.json` + `learned.md` — all human-readable, no database |
| **Skill System** | 4 built-in skills: Humidifier, Air Conditioner, Light, Coordinator (cross-device) |
| **Discovery** | Auto-scans local network via mDNS, registers devices, deduplicates |
| **MIoT Adapter** | Xiaomi/Mi Home device discovery and control via python-miio |
| **Scheduler** | Periodic device scanning (5 min), preference learning (daily) |
| **CLI** | Interactive Rich terminal: `devices`, `scan`, `status <id>`, `history` |
| **REST API** | FastAPI server on port 8080 with 8 endpoints |

## Configuration (.env)

```env
# Required: any OpenAI-compatible API key
ANIMA_LLM_API_KEY=sk-xxx

# Optional: model name (default: gpt-4o)
ANIMA_LLM_MODEL=gpt-4o

# Optional: custom endpoint for DeepSeek / Doubao / Ollama / etc.
ANIMA_LLM_BASE_URL=https://api.deepseek.com/v1

# Optional: disable deep thinking (required for Doubao)
ANIMA_LLM_DISABLE_THINKING=false
```

**Supported LLM providers** (any OpenAI-compatible API):

| Provider | ANIMA_LLM_MODEL | ANIMA_LLM_BASE_URL |
|----------|-----------------|---------------------|
| OpenAI | `gpt-4o` | *(leave empty)* |
| Anthropic (via proxy) | `claude-sonnet-4-20250514` | your proxy URL |
| DeepSeek | `deepseek-chat` | `https://api.deepseek.com/v1` |
| Doubao | `doubao-seed-2-0-lite-260215` | `https://ark.cn-beijing.volces.com/api/v3` |
| Ollama (local) | `llama3` | `http://localhost:11434/v1` |

## Development Scripts

| Command | Description |
|---------|-------------|
| `pnpm install` | Install all dependencies (frontend + backend) |
| `pnpm dev` | Start Dashboard (port 3000) + Backend (port 8080) together |
| `pnpm dev:frontend` | Start Dashboard only |
| `pnpm dev:backend` | Start Python backend only |
| `pnpm build` | Build Dashboard for production |
| `uv run pytest tests/ -v` | Run the full test suite |

## REST API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/api/devices` | List all discovered devices |
| GET | `/api/devices/{id}` | Get device details |
| POST | `/api/devices/{id}/command` | Send command to device |
| POST | `/api/scan` | Trigger device re-scan |
| GET | `/api/decisions` | Recent AI decision history |
| POST | `/api/chat` | Unified graph-based chat entry for reply, system operations, and skill execution |
| GET | `/api/rooms` | List rooms |

## Skill System

Each Skill teaches Anima **how a device type becomes autonomously intelligent** — not just how to toggle it on/off.

Global planner policy can also be adjusted in [`core/brain/prompts/planner_hints.md`](./core/brain/prompts/planner_hints.md), which is loaded into the Brain's top-level planner prompt.

```
skills/
  system/               # Built-in skills maintained by Anima
    humidifier/
      SKILL.md
      references/
        knowledge.md
        decide.md
        learn.md
      scripts/
        actions.py
  custom/               # User-added skills live here
    <your-skill>/
      SKILL.md
      references/
      scripts/
```

### Built-in Skills

| Skill | Knowledge includes |
|-------|-------------------|
| **Humidifier** | Comfort ranges (40-60%), seasonal adjustments, AC interaction, water level alerts |
| **Air Conditioner** | Energy optimization, circadian temperature, humidity coordination |
| **Light** | Circadian lighting (2200K-5000K), time-of-day brightness, transition smoothness |
| **Coordinator** | Cross-device orchestration — prevents conflicts, creates synergies |

## Project Structure

```
Anima/
├── dashboard/                  # Frontend (React + Vite + Tailwind)
│   └── src/components/         # DeviceList, DeviceCard, DecisionLog, ChatBar, Header
├── core/                       # Python backend
│   ├── brain/                  # LLM decision engine + Skill loader
│   ├── events/                 # Async EventBus
│   ├── rules/                  # Fast-path rules engine
│   ├── memory/                 # User memory (markdown + JSON)
│   ├── scheduler/              # Periodic job scheduler
│   ├── api/                    # FastAPI REST endpoints
│   └── main.py                 # Main entrypoint
├── adapters/                   # Device protocol adapters
│   └── miot/                   # Xiaomi MIoT adapter
├── skills/
│   ├── system/                # Built-in skills shipped with Anima
│   └── custom/                # User-created skills loaded from the same runtime
├── tests/                      # automated test suite
├── docs/plans/                 # Design doc + implementation plan
├── package.json                # pnpm monorepo root
├── pyproject.toml              # Python dependencies
├── docker-compose.yml          # MQTT broker + core
└── .env.example                # Configuration template
```

## Roadmap

| Version | Milestone | Key Features |
|---------|-----------|-------------|
| **v0.1** | "It's Alive" (current) | Core framework, MIoT adapter, 4 Skills, Dashboard, CLI + API, Docker |
| v0.2 | "Getting Smarter" | Matter adapter, real-time WebSocket, preference learning, room management |
| v0.3 | "Community Arrives" | Skill Store, adapter plugins, Telegram Bot, HA bridge |
| v0.4 | "Getting Stronger" | Multi-user, Raspberry Pi image, security hardening |

## Contributing

Anima is designed for easy contribution:

- **Write a Skill** — create a new folder under `skills/custom/` with `SKILL.md`, `references/`, and optional `scripts/`
  Start from `skills/custom/_template/` and copy it to `skills/custom/<your-skill-name>/`.
- **Write an Adapter** — 1 class, 3 methods: `discover()`, `subscribe()`, `execute()`

See [Design Document](docs/plans/2026-03-17-anima-design.md) for full architecture details.

## License

[Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0)
