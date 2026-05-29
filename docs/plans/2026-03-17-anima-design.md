[English](./2026-03-17-anima-design.md) | [中文](./2026-03-17-anima-design.zh-CN.md)

> **Historical design note**
>
> This document is an early architecture proposal written before the current implementation stabilized.
> It is kept for project history and design context, but some details are now outdated, including the
> MQTT-centered adapter layout, Matter/Home Assistant bridge assumptions, `learned.md`, `skill.yaml`,
> and early deployment/roadmap descriptions.
>
> For the current implementation-oriented design, see [design.md](./design.md). For contribution
> guardrails and module boundaries, see [ARCHITECTURE_GUARDRAILS.md](../../ARCHITECTURE_GUARDRAILS.md).

# Anima — Make Every Hardware Intelligent

> An open-source Agent OS that auto-discovers your hardware devices, empowers each one with AI Skills, and lets them autonomously sense, decide, and collaborate.

## Project Name: Anima

**Anima** — Latin for "soul". The name captures the project's core mission: to breathe intelligence into every piece of hardware you own. Just as "anima" gives life to the inanimate, this project gives autonomous intelligence to otherwise passive devices.

Why Anima:
- **Semantic fit**: "Give hardware a soul" aligns perfectly with "Make Every Hardware Intelligent"
- **Short and memorable**: 5 letters, easy to pronounce in any language
- **International-friendly**: Latin root recognized globally
- **Brand potential**: Strong identity, distinct from "Home Assistant / OpenHAB / Domoticz"

---

## Core Philosophy

**"Intelligence scales with what you have."**

The system's premise is not "what sensors do you need" but **"what do you have — I'll use it."**

- Zero prerequisites — no mandatory hardware
- 1 device = control 1, 8 devices = control 8
- Advanced features (biometric sensing, spatial mapping) activate only when the user has the corresponding hardware
- Users can add new devices at any time; the system auto-discovers and integrates them
- An adaptive intelligence layer, not a rigid automation platform

---

## Architecture Overview: Thin Core + MQTT Device Layer

```
┌─────────────────────────────────────────────────────────────┐
│                        Core (single process)                │
│                                                             │
│  ┌───────────┐   ┌───────────┐   ┌────────────┐            │
│  │ Discovery  │   │ EventBus  │   │ Scheduler  │            │
│  │ (device    │──▶│ (internal │◀──│ (cron/     │            │
│  │  scanning) │   │  nervous  │   │  periodic) │            │
│  └───────────┘   │  system)  │   └────────────┘            │
│                   └─────┬─────┘                             │
│            ┌────────────┼────────────┐                      │
│            ▼            ▼            ▼                      │
│  ┌───────────┐  ┌────────────┐  ┌───────────┐              │
│  │   Rules   │  │ LLM Brain  │  │  Memory   │              │
│  │ (fast     │  │ (AI        │  │ (user     │              │
│  │  path,    │─▶│  decision  │◀─│  prefs,   │              │
│  │  safety)  │  │  engine)   │─▶│  history, │              │
│  └───────────┘  └────────────┘  │  learned) │              │
│                        │         └───────────┘              │
│            ┌───────────┼───────────┐                        │
│            ▼           ▼           ▼                        │
│  ┌───────────┐  ┌───────────┐  ┌────────────┐              │
│  │ Dashboard │  │ Chat API  │  │ MQTT Client│              │
│  │ (Web UI)  │  │ (Telegram │  │ (device    │              │
│  │           │  │  /WeChat) │  │  comms)    │              │
│  └───────────┘  └───────────┘  └────────────┘              │
└─────────────────────────────┬───────────────────────────────┘
                              │ MQTT
                     ┌────────┴────────┐
                     │  MQTT Broker    │
                     │  (Mosquitto)    │
                     └──┬──────┬────┬──┘
                        │      │    │
                  ┌─────┴┐ ┌──┴───┐ ┌┴──────┐
                  │ MIoT │ │Matter│ │HA     │
                  │Adapter│ │Adapter│ │Bridge │
                  └──────┘ └──────┘ └───────┘
```

### Design Rationale

- **Single process Core**: Simple deployment (one container), like OpenClaw
- **MQTT device layer**: IoT industry standard; Zigbee2MQTT, Z-Wave JS, and others can plug in natively
- **Community-friendly**: Contributors write an adapter (3 methods) or a Skill (3 files) without touching Core
- **Phase 1 all-in-one**: Everything in `docker compose up`. Adapters can split into separate processes later

---

## Core Modules

### Discovery

- Auto-scans local network on startup: mDNS (Matter/HomeKit) + MIoT scan (Xiaomi) + SSDP (UPnP)
- New device found → event to EventBus → auto-match corresponding Skill
- Periodic re-scan (devices may go online/offline)
- Manual device addition also supported (IP/token input)

### EventBus

- Internal nervous system; all modules communicate via events
- Event types: `device.discovered`, `sensor.updated`, `rule.triggered`, `action.executed`, `user.command`
- Async, based on Python asyncio

### Rules Engine

- **Fast path**: No LLM involved, millisecond response
- Safety fallback: "temperature > 35°C → turn on AC immediately"
- Emergency alerts: "smoke sensor triggered → push notification"
- Users can also define simple custom rules

### LLM Brain

- Receives events that Rules cannot handle → loads relevant Skill's knowledge + prompt
- Assembles context: all current sensor data + user preferences + recent decision history
- Calls LLM API (user brings own key, model-agnostic: Claude / GPT / DeepSeek / Doubao)
- Parses returned Action JSON → executes via MQTT
- Coordinator Skill handles cross-device orchestration

### Memory

- OpenClaw-inspired Markdown file approach, no database dependency
- `preferences.md`: User preferences (LLM readable/writable)
- `history.json`: Decision records (data source for LLM learning)
- `learned.md`: LLM-generated user profile, periodically updated
- Evolution mechanism: LLM reviews history daily/weekly, updates learned.md

### Scheduler

- Periodic device scanning (every 5 minutes)
- Periodic preference learning (daily)
- Skill-defined scheduled tasks (e.g., "7:30 AM morning routine")

### Dashboard

Three-column layout:
- **Left**: Room list with aggregated sensor data
- **Center**: Room visualization (device icons + data, future: heatmap) + device cards
- **Right**: AI decision stream (real-time, traceable)
- **Bottom**: Chat input bar

Key pages: Overview, Device Management, Skill Store, My Preferences, Decision History, Settings

### Chat API

- Embedded in Dashboard (bottom bar)
- External platforms via HTTP API (`POST /api/chat`)
- Phase 1: Telegram Bot
- Phase 2: WeChat / Slack / others

---

## Skill System (Core Differentiator)

### Philosophy

Skills are not just "how to control a device" — they are **"how this hardware becomes autonomously intelligent"**. Each Skill contains domain knowledge, control logic, and user personalization.

### Structure

```
skills/
  humidifier/
    skill.yaml            # Metadata: name, compatible device models, capability declarations
    knowledge.md          # Domain knowledge: comfortable humidity ranges, seasonal recommendations,
                          #   relationship with temperature
    actions.py            # Executable actions: set_humidity, set_mode, turn_on/off
    prompts/
      decide.md           # Decision prompt: "Current humidity {x}, target {y}, user prefs {z}, what to do?"
      learn.md            # Learning prompt: "Based on user's past 7 days, summarize preferences"
  air_conditioner/
    skill.yaml
    knowledge.md          # Cooling/heating strategies, energy optimization, humidity interaction
    actions.py
    prompts/
  air_purifier/
    ...
  light/
    ...
  coordinator/            # Special Skill: cross-device orchestration
    skill.yaml
    knowledge.md          # "When AC turns on, humidity drops — need to coordinate with humidifier"
    prompts/
      orchestrate.md      # Multi-device coordination decisions
```

### Execution Flow

```
Sensor data changes
  → Rules engine: threshold breached?
  → If yes → Load relevant Skill's knowledge.md + user memory
  → Assemble prompt → Send to LLM
  → LLM returns decision (JSON action call)
  → Execute action → Control device via MQTT
  → Record result to Memory (user preference evolution)
```

### User Preference Evolution

```
memory/
  users/
    default/
      preferences.md      # "Prefers sleep temperature 23°C, wake-up time 7:30"
      history.json         # Last 30 days of decisions + user feedback
      learned.md           # LLM-summarized user profile, periodically updated
```

### Beyond Home: Skill Imagination

- Robot vacuum Skill: "Someone entered → delay 30 min → clean entryway"
- Smart lock Skill: "Repeated stranger attempts → notify user + turn on lights"
- Smart speaker Skill: "User woke up → announce weather + start coffee machine"
- Industrial sensors, office equipment, agricultural greenhouses...

---

## Device Adapter Layer

### MQTT Topic Design

```
# ── Device Discovery ──
anima/discovery/announce            # Adapter reports discovered devices
anima/discovery/scan                # Core requests re-scan

# ── Device State (Adapter → Core) ──
anima/devices/{device_id}/state     # Full device state
anima/devices/{device_id}/online    # Online/offline

# ── Device Control (Core → Adapter) ──
anima/devices/{device_id}/command   # Control commands

# ── Sensor Data ──
anima/rooms/{room_id}/sensors       # Room-level aggregated sensor data

# ── System Events ──
anima/system/brain/decisions        # AI decision log (Dashboard subscribes)
anima/system/brain/actions          # Executed action log
```

### Unified Device Model

Regardless of underlying protocol (Xiaomi or Matter), Core sees the same data structure:

```yaml
# Device discovery report
device_id: "miot_xiaomi_humidifier_01"
name: "Bedroom Humidifier"
adapter: "miot"
room: null                          # User assigns later
type: "humidifier"                  # Maps to Skill
capabilities:
  - set_humidity: { min: 30, max: 80, step: 10 }
  - set_mode: { options: ["auto", "silent", "strong"] }
  - turn_on
  - turn_off
sensors:
  - humidity: { unit: "%", current: 45 }
  - water_level: { unit: "%", current: 60 }
  - power: { unit: "on/off", current: "on" }
```

```yaml
# Control command format
device_id: "miot_xiaomi_humidifier_01"
action: "set_humidity"
params:
  value: 55
source: "brain"                     # Who initiated: brain / rules / user
reason: "User prefers 55%, currently 45%"  # AI decision reasoning (traceable)
```

### Adapter Development Spec

Each adapter is a standalone Python package with minimal structure:

```
adapters/
  miot/
    __init__.py
    adapter.py          # Must implement 3 methods:
                        #   discover() → List[Device]
                        #   subscribe(device_id) → continuous state reporting
                        #   execute(device_id, action, params) → control execution
    config.yaml         # Adapter config (scan interval, auth method, etc.)
    README.md
  matter/
    adapter.py
    config.yaml
  homeassistant/
    adapter.py          # Bridges via HA REST API
    config.yaml
```

### Adapter Priority

| Priority | Adapter | Library | Coverage |
|----------|---------|---------|----------|
| P0 | MIoT | python-miio | Xiaomi ecosystem |
| P0 | Matter | connectedhomeip | All Matter-certified devices |
| P1 | Home Assistant | httpx (REST API) | All devices HA users already have |
| P2 | Tuya | TinyTuya | Tuya white-label devices |
| P2 | BLE | bleak | Bluetooth sensors |

---

## Deployment

### Phase 1: Docker Compose

```yaml
services:
  core:
    image: anima/core
    ports:
      - "8080:8080"          # Dashboard + API
    volumes:
      - ./data:/app/data      # Memory + config persistence
    environment:
      - LLM_API_KEY=${LLM_API_KEY}
      - LLM_MODEL=claude-sonnet-4-20250514
      - LLM_BASE_URL=         # Optional custom endpoint

  mqtt:
    image: eclipse-mosquitto:2
    ports:
      - "1883:1883"
```

### User Onboarding Flow

```bash
git clone https://github.com/xxx/anima
cp .env.example .env        # Fill in LLM_API_KEY
docker compose up -d
# Open http://localhost:8080
# System auto-discovers devices and starts working
```

Users do NOT need to:
- Manually configure any device (auto-discovery)
- Understand MQTT (internal detail, invisible)
- Write any code or rules (AI decides autonomously)

### Future Deployment Targets

| Phase | Deployment |
|-------|-----------|
| v1 | Docker Compose (any machine) |
| v2 | Raspberry Pi image (flash SD card and go) |
| v3 | NAS package (Synology / QNAP app store) |
| v4 | Dedicated hardware (partner with hardware vendors) |

---

## Open Source Strategy

### License: Apache 2.0

- Same as OpenClaw, Matter SDK
- Allows commercial use (attracts enterprise contributors)
- Patent protection (safer than MIT)

### Repository Structure

```
anima/
├── core/                        # Core process
│   ├── brain/                   # LLM decision engine
│   ├── events/                  # EventBus
│   ├── rules/                   # Rules engine
│   ├── memory/                  # User memory system
│   ├── scheduler/               # Scheduled tasks
│   └── api/                     # HTTP + WebSocket API
├── adapters/                    # Device adapters
│   ├── miot/
│   ├── matter/
│   └── homeassistant/
├── skills/                      # Skill packages
│   ├── humidifier/
│   ├── air_conditioner/
│   ├── light/
│   ├── air_purifier/
│   └── coordinator/
├── dashboard/                   # Frontend (React)
├── docker-compose.yml
├── .env.example
├── CLAUDE.md
└── docs/
    ├── getting-started.md
    ├── write-a-skill.md
    ├── write-an-adapter.md
    └── architecture.md
```

### Community Growth (Lessons from OpenClaw)

| Phase | Strategy |
|-------|----------|
| Cold start | 3-minute demo video: "From docker compose up to AI auto-controlling my Xiaomi devices" — post on Twitter / V2EX / Hacker News |
| First contributors | Make writing Skills and Adapters trivially easy (3 methods / 3 files) |
| Ecosystem flywheel | Skill Store — community Skills installable with one click |
| Internationalization | English-first (README, docs, code comments), Chinese as second language |

---

## Roadmap

### v0.1 — "It's Alive" (MVP)

- [ ] Core framework (EventBus + Rules + Scheduler)
- [ ] MIoT adapter (Xiaomi device discovery + state + control)
- [ ] 2-3 base Skills (humidifier / AC / light)
- [ ] LLM Brain basic decision loop
- [ ] Memory system (preference read/write)
- [ ] CLI interaction (geek mode)
- [ ] Docker Compose deployment
- **Goal**: `docker compose up` → auto-discover Xiaomi devices → AI auto-adjusts

### v0.2 — "Now You Can See"

- [ ] Dashboard MVP (device list + room management + AI decision log)
- [ ] Dashboard embedded chat
- [ ] Matter adapter
- [ ] Room-based spatial data model
- [ ] User preference evolution (LLM periodic learning)
- [ ] More Skills (air purifier / robot vacuum / curtain)

### v0.3 — "Community Arrives"

- [ ] Skill Store (online install community Skills)
- [ ] Adapter plugin system (`pip install anima-adapter-tuya`)
- [ ] Home Assistant bridge adapter
- [ ] Telegram Bot integration
- [ ] 2D room heatmap (exploration)
- [ ] Documentation: write-a-skill / write-an-adapter

### v0.4 — "Getting Stronger"

- [ ] Coordinator Skill enhancement (complex multi-device scenarios)
- [ ] Raspberry Pi image
- [ ] Multi-user support (family members with different preferences)
- [ ] More chat platform integrations
- [ ] Security hardening (device control permissions, API auth)

---

## Key References

- [OpenClaw](https://en.wikipedia.org/wiki/OpenClaw) — Agent OS architecture inspiration (Gateway + Brain + Memory + Skills + Heartbeat)
- [Matter Protocol](https://project-chip.github.io/connectedhomeip-doc/index.html) — Open-source IoT interoperability standard
- [python-miio](https://github.com/rytilahti/python-miio) — Xiaomi MIoT local control library
- [Home Assistant](https://www.home-assistant.io/) — Optional device bridge via REST API
- [Eclipse Mosquitto](https://mosquitto.org/) — MQTT broker
- [NetDisco](https://github.com/home-assistant-libs/netdisco) — Device discovery library
