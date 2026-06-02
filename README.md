<div align="center">
  <img src="docs/images/Anima Logo.svg" alt="Anima logo" width="320" />
  <h1></h1>
  <p><strong>Make every hardware intelligent</strong></p>
  <p>An open-source Agent OS for hardware intelligence.</p>

  [English](./README.md) | [中文](./README.zh-CN.md)
  <br/><br/>

  [![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](./LICENSE)
  ![Python](https://img.shields.io/badge/Python-3.11--3.13-blue)
  ![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi)
  ![React](https://img.shields.io/badge/React-Dashboard-61DAFB?logo=react)
  ![LangGraph](https://img.shields.io/badge/LangGraph-Agent%20Brain-purple)
  ![MIoT](https://img.shields.io/badge/Xiaomi%20MIoT-Supported-orange)
</div>

<br/>

**Anima** is an open-source Agent OS for intelligent hardware. Its goal is not to build yet another device control panel, but to give home hardware perceptive, decision-making, learning, and extensible AI capabilities.

The name **Anima** comes from Latin and means "soul." It reflects the project's original idea: today's smart hardware already has sensors, connectivity, and actuation, but most devices still wait passively for commands. Anima connects these devices to a runnable intelligence center, so lights, air conditioners, humidifiers, air purifiers, speakers, and future devices can understand the environment, the user, and each other.

> Anima's vision: move every piece of hardware from a "connected device" to a collaborative intelligent agent.

<div align="center">
  <img src="docs/images/bedroom.svg" alt="Anima Dashboard Bedroom Design" width="100%" />
</div>

## What Is Anima

Anima can be understood as an intelligent hardware Agent Runtime running inside your local network:

- It discovers devices, maintains device state, and controls real hardware through adapters.
- It maintains long-term Memory and learns from explicit preferences and repeated behavior.
- It uses an LLM Brain to read the environment, user intent, historical memory, and skill knowledge, then plan actions.
- It packages domain knowledge for each device type as a Skill, so decisions are not just "on/off" but aligned with context, comfort, and safety boundaries.
- It provides a Dashboard, REST API, and CLI so you can observe, debug, control, and extend the whole system.

Anima currently supports Mi Home / MIoT devices. More hardware protocols will be added over time, and contributions from the open-source community are welcome.

---

## Why Anima

<div align="center">

![Zero config](https://img.shields.io/badge/Zero%20config-Auto%20discovery-0A7EA4?style=for-the-badge)
![AI skills](https://img.shields.io/badge/AI%20skills-Per%20device-1B5E20?style=for-the-badge)
![Memory system](https://img.shields.io/badge/Memory%20system-Learns%20your%20habits-B71C1C?style=for-the-badge)
![LLM brain](https://img.shields.io/badge/LLM%20Brain-OpenAI%20API%20compatible-4A148C?style=for-the-badge)
![Skill system](https://img.shields.io/badge/Skill%20system-Extensible-0D47A1?style=for-the-badge)
![Dashboard](https://img.shields.io/badge/Dashboard-Realtime%20visibility-6A1B9A?style=for-the-badge)

</div>

> [!TIP]
> Most smart-home systems ask, "What sensors do you need?" Anima asks, **"What do you have? I'll use it."** It discovers your devices automatically, loads domain knowledge for each device, and starts making intelligent decisions from day one.

<details>
<summary><strong>Q: Do I need to configure devices manually?</strong></summary>

**A:** No. Anima scans the local network through the corresponding adapter protocols. For Xiaomi / Mi Home devices, one QR login can automatically obtain device tokens without manually entering IP lists or extracting tokens.

</details>

<details>
<summary><strong>Q: Is it just a fancy switch controller?</strong></summary>

**A:** Far from it. Core device types have dedicated **Skills**: domain knowledge packages that include comfort models, occupancy awareness, cross-device coordination rules, and preference learning. Your humidifier understands seasonal adjustments and AC interaction; your lights can follow circadian lighting patterns.

</details>

<details>
<summary><strong>Q: How does it learn my preferences?</strong></summary>

**A:** Anima maintains a memory system with `preferences.md`, normalized learned profiles per device type, and extracted topic memories. The Brain incrementally extracts preferences from interaction history and evolves behavior over time.

</details>

<details>
<summary><strong>Q: Which LLM providers are supported?</strong></summary>

**A:** Any OpenAI-compatible API service, including OpenAI, DeepSeek, Doubao, Anthropic through a proxy, and local Ollama-compatible endpoints. Set `ANIMA_LLM_API_KEY`, and optionally `ANIMA_LLM_BASE_URL`.

</details>

---

## System Architecture

Anima's overall runtime flow is driven by user requests, device discovery, sensor updates, scheduled tasks, and device actions. After signals enter Anima Core, the Brain combines device state, Memory, and Skill context to understand and plan. During execution, Skills convert decisions into structured actions, and Adapters map those actions to concrete hardware protocols, completing real device control and feedback recording.

<div align="center">
  <img src="docs/images/architecture.svg" alt="Anima Overall Architecture" width="100%" />
</div>

---

## Core Highlights

### 1. Brain: Central Decision Layer

The Brain is Anima's intelligence center. It merges user conversations, device state, environment signals, memory, and skill capabilities into executable plans.

The current Brain supports:

- LangGraph-based planner / executor flows
- Unified chat entrypoint at `/api/chat`
- Scheduled brain ticks for proactive environment checks and automation decisions
- Context construction before skill execution
- State verification and history writes after actions
- OpenAI-compatible LLM backends

The Brain's purpose is not to let an LLM control devices freely. It makes decisions within explicit skill boundaries, device capabilities, and safety rules.

### 2. Skill: The Smallest Unit of Device Intelligence

A Skill in Anima is not a simple function or a plain prompt. It is a device domain knowledge package, typically including:

```text
SKILL.md              # skill metadata, supported devices, and operating rules
references/
  knowledge.md        # domain knowledge
  decide.md           # single-decision prompt
  learn.md            # long-term learning prompt
scripts/
  actions.py          # structured action execution entrypoint
```

Built-in Skills include:

| Skill | Purpose |
|---|---|
| `light` | Light control, brightness, color temperature, circadian lighting |
| `humidifier` | Humidity comfort ranges, seasonal factors, AC interaction |
| `air_conditioner` | Temperature control, comfort and energy balance |
| `air_purifier` | Air quality, purification mode, quiet sleep strategy |
| `speaker` | Audio playback, stop playback, quiet-hour protection |
| `coordinator` | Cross-device coordination |
| `device_discovery` | Device discovery, Mi Home QR login, device activation |
| `skill_creator` | Generate custom skills from natural-language requirements |

You can also add your own skills under `skills/custom/` so Anima can learn new device behaviors or home workflows.

The diagram below shows the full lifecycle of a Skill in Anima: device capabilities can enter the Skill Creator through automatic discovery or user definition, then be organized into the Skill Bank for the Brain to retrieve and select during planning. During execution, the Planner selects an appropriate Skill based on the current environment, device state, and Memory context. The Skill then converts high-level goals into structured actions and applies them to real devices through Adapters. Execution results flow back into Memory and learned profiles, making future decisions more aligned with user habits.

<div align="center">
  <img src="docs/images/skill system.png" alt="Anima Skill System Architecture" width="100%" />
</div>

This means a Skill in Anima is not a one-off function call. It is a device intelligence unit that can be created, registered, retrieved, executed, and improved through feedback. When adding a new device type, prefer extending Skills instead of hardcoding device policy into the Brain or an Adapter.

### 3. Memory: Evidence-Based Long-Term Memory

Anima's Memory system uses a layered design:

```text
L1 Core Identity
  A minimal preference summary loaded on every request, such as preferences_summary.

L2 Memory Directory
  A memory directory for the planner, such as available learned profiles and memory topics.

L3 Memory Detail
  Detailed long-term memories retrieved by device type and task before skill execution.
```

The diagram below shows where Memory sits inside the Anima runtime. The lower layer stores preferences, history, learned profiles, and topic memories as files. The middle Memory service reads, extracts, merges, and updates them. The upper layer exposes different memory granularities to the Brain and Skills through `get_planner_context()` and `get_skill_context(device_type)`. This lets the Planner avoid reading all history on every request: it first learns what memories exist, then loads details only when a device Skill is actually executed.

<div align="center">
  <img src="docs/images/memory%20system.svg" alt="Anima Memory System Architecture" width="100%" />
</div>

This layered design lets Anima balance long-term learning with context control: L1 stays lightweight, L2 provides a directory, and L3 loads confirmed details only when needed. Execution results, user conversations, and device state continuously enter history, are extracted in the background into more stable long-term memories, and eventually influence future device decisions.

The current memory system supports:

- `history.json` generating an `event_id` for each interaction
- extracted memory stored with a standard schema
- `claim_type` distinguishing explicit preferences, implicit preferences, routines, device aliases, constraints, and home context
- `positive_evidence` / `negative_evidence` recording evidence sources
- `status` distinguishing `candidate`, `confirmed`, `rejected`, and `stale`
- only confirmed memory entering skill decisions by default
- learned profiles stored by device type in `learned.json`

### 4. Adapter: Real Hardware Integration Layer

Adapters convert Anima's structured actions into real device protocol calls.

Currently supported:

- Xiaomi / Mi Home / MIoT device discovery
- Xiaomi Cloud QR login for device lists and tokens
- Local `ip + token` control for ordinary MIoT devices
- Partial cloud playback support for Xiaomi speakers
- Manual MIoT device addition
- Device state refresh and action result reporting

Note: ordinary MIoT command execution still depends on the device's currently reachable local IP and token. Xiaomi Cloud login is mainly used for discovery and token acquisition; it does not mean every device supports cloud remote control.

## Features

- **Automatic device discovery**: local network scanning, Xiaomi Cloud device sync, deduplication, and runtime registration.
- **AI decision center**: the LLM Brain generates action plans from environment, devices, skills, and memory.
- **Extensible Skill system**: each device type has independent knowledge, decision prompts, learning prompts, and action scripts.
- **Long-term memory**: candidate memories are extracted from history and promoted to confirmed memory based on evidence.
- **Preference learning**: learned profiles are generated per device type so future decisions better match user habits.
- **Realtime Dashboard**: device list, environment state, chat control, settings, and memory debugging.
- **REST API**: interfaces for devices, chat, settings, scanning, memory, and more.
- **MIoT support**: Xiaomi / Mi Home token acquisition, local control, and partial speaker cloud capabilities.
- **Local-first**: the core runs on your machine and controls devices through the local network whenever possible.

---

## Quick Start

### Requirements

- Node.js >= 18
- pnpm >= 8
- Python >= 3.11
- uv

`pnpm install` installs Python dependencies through `uv sync`.
To control MIoT devices, run `uv sync --extra dev --extra miot --python 3.13`, or change `postinstall` to include `miot`.

### Install and Run

```bash
git clone https://github.com/fulai-tech/Anima.git
cd Anima
pnpm install
pnpm dev
```

After startup, open:

```text
Dashboard: http://localhost:3000
Backend API: http://localhost:8080
Swagger: http://localhost:8080/docs
```

### Configure the LLM

You can configure it in `.env` or in the Dashboard settings page.

```env
ANIMA_LLM_API_KEY=sk-xxx
ANIMA_LLM_MODEL=gpt-4o
ANIMA_LLM_BASE_URL=
ANIMA_LLM_DISABLE_THINKING=false
```

Anima uses an OpenAI-compatible API, so it can connect to OpenAI, DeepSeek, Doubao, Ollama-compatible endpoints, or other proxy services.

### Connect Xiaomi Devices

The recommended path is Xiaomi QR login in the Dashboard:

1. Open the Dashboard settings page.
2. Go to the Xiaomi / Mi Home configuration area.
3. Generate a QR code.
4. Scan it with the Mi Home app.
5. Devices are synchronized automatically when Xiaomi Cloud returns tokens; devices without returned tokens can still be activated by manually entering a token.

If you already know a device IP and token, you can also add a MIoT device manually.

---

## Common Commands

| Command | Description |
|---|---|
| `pnpm install` | Install frontend and backend dependencies |
| `pnpm dev` | Start Dashboard, Backend, and local broker together |
| `pnpm dev:frontend` | Start only the frontend |
| `pnpm dev:backend` | Start only the backend |
| `pnpm dev:broker` | Start only the local MQTT broker |
| `pnpm build` | Build the frontend |
| `uv run pytest tests/ -v` | Run tests |
| `uv run ruff check .` | Run Python lint |

---

## Project Structure

```text
Anima/
├── 🧠 core/                  # Backend runtime: API, brain, memory, devices
│   ├── 🛣️  api/             # FastAPI routes and HTTP endpoints
│   ├── 🧭 brain/            # Planner, executor, ReAct agent, skill loader
│   ├── 🔎 devices/          # Discovery orchestration and device registry
│   ├── 📡 events/           # Async EventBus and runtime signals
│   ├── 🤖 llm/              # OpenAI-compatible LLM runtime config
│   ├── 🔊 media/            # Xiaomi speaker playback support
│   ├── 🗃️  memory/          # Preferences, history, profiles, extracted memories
│   ├── ⚙️  runtime/         # Settings and persisted config
│   └── ⚙️  main.py          # Application entrypoint
├── 🔌 adapters/             # Hardware protocol adapters
│   └── 🏠 miot/             # Xiaomi MIoT adapter
├── ✨ skills/               # Device intelligence packages
│   ├── 🧩 system/           # Built-in skills
│   └── ✍️  custom/          # User-defined skills
├── 🖥️  dashboard/           # React + Vite dashboard
├── ✅ tests/                # Automated tests
├── 📚 docs/                 # Design notes and implementation plans
├── 💾 data/                 # Local runtime data
├── 📦 package.json          # Root pnpm scripts
└── 🧰 pyproject.toml        # Python project config
```

---

## API Overview

The backend runs at `http://localhost:8080` by default.

Common endpoints include:

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/api/devices` | Get the device list |
| `POST` | `/api/devices/{device_id}/command` | Send a command to a device |
| `POST` | `/api/devices/add` | Manually add a MIoT device |
| `POST` | `/api/devices/{device_id}/activate` | Activate a scanned device with a token |
| `POST` | `/api/chat` | Unified chat and task execution entrypoint |
| `GET` | `/api/environment` | Current aggregated environment state |
| `POST` | `/api/environment/refresh` | Refresh device state |
| `POST` | `/api/scan` | Trigger device scanning |
| `GET` | `/api/memory` | Inspect memory, history, and learned profiles |
| `GET` | `/api/settings` | Read settings |
| `POST` | `/api/settings/llm/configure` | Configure the LLM |
| `POST` | `/api/settings/xiaomi/qr/start` | Start Xiaomi QR login |
| `POST` | `/api/settings/xiaomi/qr/poll` | Poll QR login status |

For the full API, open Swagger:

```text
http://localhost:8080/docs
```

---

## How to Extend

### Add a Skill

The simplest extension path is to add a skill.

```text
skills/custom/my_skill/
├── SKILL.md
├── references/
│   ├── knowledge.md
│   ├── decide.md
│   └── learn.md
└── scripts/
    └── actions.py
```

A good skill should answer four questions:

```text
1. Which devices or scenarios does it apply to?
2. What domain knowledge does it need?
3. When should it act, and when should it no-op?
4. What structured actions can it output?
```

### Add an Adapter

Adapters integrate new hardware protocols. The core interface is small:

```text
discover()   # discover devices
subscribe()  # refresh or subscribe to state
execute()    # execute an action
```

You can use `adapters/miot/` as a reference to implement new protocol adapters such as Matter, Home Assistant, BLE, HTTP API, or private device protocols.

---

## Current Status

Anima is still early-stage, but it already has a complete runnable core loop:

```text
device discovery -> Brain planning -> Skill decision -> Adapter execution -> state verification -> History/Memory learning
```

The more mature parts today:

- Core runtime
- Dashboard
- MIoT adapter
- Skill framework
- Memory extraction and learned profiles
- Chat and REST API

Areas still evolving:

- More device protocol adapters
- More complete remote-control strategies
- Stronger memory retrieval and conflict handling
- Skill marketplace / community skills
- Multi-user and permission models
- More complete security policies and deployment experience

---

## Update Log

This section records Anima releases, architecture upgrades, and key capability evolution so developers can quickly understand the core changes at each stage.

- 2026-06-01: Anima's first open-source version is released, providing the foundational Agent OS capabilities for intelligent hardware: local device discovery, MIoT device integration, LLM Brain decisions, Skill mechanism, long-term Memory system, and visual Dashboard.

---

## Contributing

Anima welcomes different kinds of contributions:

- Add new device adapters
- Write or improve skills
- Optimize Brain decision flows
- Improve the Memory mechanism
- Enhance the Dashboard experience
- Add tests and documentation
- Report real-device compatibility issues

Before contributing, you may want to read:

- [CONTRIBUTING.md](./CONTRIBUTING.md)
- [ARCHITECTURE_GUARDRAILS.md](./ARCHITECTURE_GUARDRAILS.md)
- [docs/plans/design.md](./docs/plans/design.md)

---

## Security Notes

Anima connects to real devices and executes real actions. Please note:

- Do not expose the Dashboard or API directly to the public internet.
- Sensitive information such as Xiaomi tokens and LLM API keys should only be stored in trusted environments.
- Establish clear permission boundaries before controlling devices in offices, public spaces, or shared homes.
- Keep automation conservative, especially for high-risk devices such as door locks, security devices, and electrical power.

---

## License

This project is licensed under the Apache License 2.0.
See the [LICENSE](./LICENSE) file for details.

<div align="center">
  <br/>
  <p><em><strong>Anima</strong></em></p>
  <p><em>Make every hardware intelligent.</em></p>
</div>
