# Anima Current Design

> 中文版: [design.zh-CN.md](./design.zh-CN.md)
>
> Current implementation-oriented design for Anima.
>
> This document describes how Anima is structured today. For the original early proposal, see
> [2026-03-17-anima-design.md](./2026-03-17-anima-design.md). For architectural guardrails used by
> future contributors and agents, see [ARCHITECTURE_GUARDRAILS.md](../../ARCHITECTURE_GUARDRAILS.md).

## 1. Purpose

Anima is an open-source Agent OS for hardware intelligence. It is designed to connect large language
models with physical devices through a local-first runtime that can discover devices, understand their
state, reason with device-specific skills, execute safe actions, and learn user preferences over time.

Anima is not just a device dashboard and not just a chat wrapper around smart-home APIs. The core goal
is to make hardware behavior context-aware:

```text
perceive -> plan -> act -> verify -> remember
```

The current implementation focuses on smart-home devices, especially Xiaomi / Mi Home / MIoT devices,
while keeping the adapter boundary open for future protocols.

## 2. Runtime Overview

The current runtime is assembled in `core/main.py` as a single Python process. The Dashboard runs as a
separate Vite/React frontend and communicates with the backend through REST APIs and server-sent event
streams.

```text
                    Dashboard
                 React / Vite UI
                       |
                    REST / SSE
                       |
┌──────────────────────▼─────────────────────────┐
│                  Anima Core                    │
│             single asyncio process             │
│                                                │
│  DiscoveryOrchestrator ────────┐               │
│       device registry          │               │
│       command routing          │               │
│                                │               │
│  EventBus ◀──── sensor/device/action events    │
│                                │               │
│  Scheduler ───── periodic jobs │               │
│                                ▼               │
│  Brain ───── SkillLoader ───── Skills          │
│    │            │             knowledge        │
│    │            │             prompts          │
│    │            │             actions          │
│    ▼            │                              │
│  MemoryStore ◀──┘                              │
│  history / preferences / learned / memories    │
│                                                │
│  Adapters                                      │
│  MIoT local/cloud, virtual, future protocols   │
└──────────────────────┬─────────────────────────┘
                       |
                 Physical Devices
```

MQTT still exists in the repository as runtime infrastructure, but the current MIoT control path is not
MQTT-centered. The primary command path is:

```text
Brain / API -> DiscoveryOrchestrator.execute_command() -> owning Adapter.execute() -> device protocol
```

## 3. Main Runtime Components

### `core/main.py`

`core/main.py` owns process assembly and top-level runtime wiring. It creates:

- `SettingsStore`
- `EventBus`
- `MemoryStore`
- `MemoryExtractionService`
- `PreferenceLearningService`
- `RulesEngine`
- `SkillLoader`
- `Brain`
- `Scheduler`
- `DiscoveryOrchestrator`
- adapters such as `MIoTAdapter` and `VirtualAdapter`
- FastAPI application state

It also registers event handlers and scheduled jobs.

Current scheduler jobs:

| Job | Function | Interval |
|---|---|---:|
| `device_scan` | `discovery.scan` | 7200 seconds |
| `environment_refresh` | `discovery.refresh_device_states` | 60 seconds |
| `learn_preferences` | `preference_learner.run_now` | 300 seconds |
| `brain_tick` | scheduler-driven brain cycle | 60 seconds |

The Scheduler directly calls registered functions. It does not use the EventBus as a timer mechanism.
Those functions may emit events as a consequence of scan, refresh, or command execution.

### `DiscoveryOrchestrator`

`core/devices/discovery.py` owns the canonical device registry and command routing.

It is responsible for:

- asking adapters to discover devices
- maintaining `device_id -> Device`
- maintaining `device_id -> adapter`
- refreshing device state through adapter `subscribe()`
- emitting device and sensor events
- routing commands through the adapter that owns the target device

This is the boundary that prevents random modules from directly controlling protocol clients.

### `EventBus`

`core/events/bus.py` is an async in-process event bus. It is used for runtime visibility and reactive
coordination between modules.

Important event categories include:

- device discovered
- sensor updated
- action executed

The EventBus is not the only runtime path. For example, scheduled jobs are registered directly in the
Scheduler, and device commands are routed through `DiscoveryOrchestrator`.

### `RulesEngine`

`core/rules/engine.py` is the deterministic fast path for local automation and safety-oriented logic.
Rules should stay local, predictable, and independent of LLM availability.

The long-term architectural direction is:

```text
rules first -> LLM slow path only when reasoning is needed
```

### `Brain`

`core/brain/engine.py` is the slow-path reasoning layer. It combines:

- user message or scheduler task
- current device state
- environment snapshot
- available skills
- memory context
- LLM output parsing
- action execution and verification
- history/memory recording

The Brain should not contain protocol-specific control logic. It plans actions and delegates execution
through skills and the discovery/adapter boundary.

The current Brain supports:

- LangGraph planner/executor flows
- ReAct-style streaming chat with tools
- scheduler-driven brain ticks
- skill context construction
- action execution retries and verification
- chat turn recording
- OpenAI-compatible LLM backends

## 4. Device Adapter Layer

Adapters translate Anima's canonical actions and device model into concrete device protocol calls.

The abstract interface lives in `adapters/base.py`:

```python
async def discover() -> list[Device]
async def subscribe(device: Device) -> None
async def execute(device_id: str, action: str, params: dict) -> ActionResult
```

### Current MIoT Adapter

The current MIoT adapter lives in `adapters/miot/`.

It supports several device sources:

- manual devices from persisted config
- cached Xiaomi Cloud devices
- Xiaomi Cloud discovery where credentials are available
- local MIoT UDP broadcast discovery
- QR login flow for Xiaomi Cloud device and token synchronization

For ordinary MIoT device control, Anima still needs a reachable local IP and valid token. Xiaomi Cloud
login is mainly used to synchronize device metadata and tokens. If Xiaomi Cloud does not return a valid
token for a device, the device may remain in a `needs_token` state and require manual activation.

### Virtual Adapter

The virtual adapter provides local test/demo devices and helps validate the runtime without relying on
physical hardware.

### Future Adapters

New protocols should be added as new adapters rather than by branching protocol logic inside Core.
Candidate future adapters include:

- Matter
- Home Assistant bridge
- BLE sensors
- HTTP API devices
- private vendor APIs

## 5. Skill System

Skills are Anima's device intelligence packages. They define how a device type should be reasoned about,
not merely how a device is toggled.

Current skill layout:

```text
skills/system/<skill_name>/
├── SKILL.md
├── references/
│   ├── knowledge.md
│   ├── decide.md
│   └── learn.md
└── scripts/
    └── actions.py
```

Custom skills follow the same structure under:

```text
skills/custom/
```

Current built-in skills include:

- `light`
- `humidifier`
- `air_conditioner`
- `air_purifier`
- `speaker`
- `coordinator`
- `device_discovery`
- `skill_creator`

Global planner policy can also be adjusted in [`core/brain/prompts/planner_hints.md`](./core/brain/prompts/planner_hints.md).

### Skill Lifecycle

Skills participate in several runtime phases:

1. **Discovery / loading**: `SkillLoader` discovers system and custom skills.
2. **Planning**: Brain sees lightweight skill summaries and chooses the relevant skill.
3. **Context construction**: Brain builds device-specific context from current device state, memory, learned profile, and skill references.
4. **Decision**: LLM produces a structured decision based on the skill prompt.
5. **Execution**: skill action code converts the decision into an executable device command.
6. **Feedback**: execution result, verification status, and history entries feed memory and future learning.

### Skill Creator

`skill_creator` can scaffold or generate custom skill packages from user requests. Its role is to help
expand Anima's behavior layer without changing Core. Generated skills should still respect the standard
skill structure and action boundaries.

## 6. Memory System

Anima's memory is file-based and intentionally simple. The default user memory directory is:

```text
data/memory/users/default/
```

Important files:

| File | Purpose |
|---|---|
| `preferences.md` | Human-readable preference notes |
| `history.json` | Recent decisions, chat turns, actions, and verification records |
| `learned.json` | Normalized learned profiles per device type |
| `memory_state.json` | Extraction cursor/state |
| `memories/{slug}.json` | Topic-based long-term memory entries |

### Three-Level Context API

The current memory system is organized as a layered context API:

| Layer | Purpose | Typical Use |
|---|---|---|
| L1 Core Context | Small always-loaded context such as preference summary and last interaction | planner and chat context |
| L2 Summary Layer | Directory of learned profile types and memory topics | helps the planner know what memory exists |
| L3 On-demand Detail | Detailed confirmed memories and learned profiles | loaded for device-specific skill decisions |

This design keeps prompts small while allowing detailed long-term memory to be retrieved only when it
is relevant.

### Evidence and Overlearning Control

Long-term memories use structured fields such as:

- `claim_type`
- `status`
- `confidence`
- `evidence_count`
- `positive_evidence`
- `negative_evidence`
- `device_types`
- `device_ids`
- `scenes`

By default, only confirmed memories should influence device skill decisions. Candidate memories can be
shown for debugging or review but should not be treated as stable preferences.

## 7. API and Dashboard

The FastAPI app is created in `core/api/routes.py`. It exposes runtime state and control surfaces.

Important API areas:

- device listing and command execution
- room/device metadata
- virtual device management
- environment refresh
- chat and streaming chat
- memory inspection
- skill inspection and editing
- LLM settings
- Xiaomi QR login and token synchronization

The Dashboard is a React/Vite operator console. It visualizes:

- devices and device controls
- environment state
- assistant/chat replies
- execution traces
- memory state
- settings and Xiaomi onboarding

The frontend should not own business logic. It should remain a control and observation surface over the
backend runtime.

## 8. Current Execution Flows

### User Chat Flow

```text
Dashboard
  -> POST /api/chat
  -> Brain chat planner or ReAct agent
  -> skill selection / tool calls
  -> DiscoveryOrchestrator.execute_command()
  -> Adapter.execute()
  -> device protocol
  -> verification / history / memory scheduling
  -> response streamed or returned to Dashboard
```

### Scheduler Flow

```text
Scheduler
  -> environment_refresh / brain_tick / learn_preferences / device_scan
  -> direct function call
  -> optional EventBus events
  -> Brain or Memory services where relevant
```

### Sensor Update Flow

```text
Adapter refresh
  -> DiscoveryOrchestrator updates cached sensor values
  -> EventBus emits SENSOR_UPDATED
  -> main runtime may request a throttled brain cycle
  -> Brain evaluates whether any action is needed
```

### Device Command Flow

```text
Brain or API
  -> DiscoveryOrchestrator.execute_command(device_id, action, params)
  -> owning Adapter.execute()
  -> protocol-specific command
  -> ActionResult
  -> ACTION_EXECUTED event
  -> history/memory recording
```

## 9. Identity and Device IDs

MIoT device identity is token-aware. When a valid token is available, the adapter builds a stable
token-based device ID without exposing the raw token. Pending devices discovered without valid tokens
may use temporary DID/IP-based IDs until they are activated or reconciled with cloud data.

This matters because local IP addresses can change, while token-derived IDs are more stable across
restarts and network changes.

## 10. Development and Extension Guidelines

### Adding a Skill

Add a skill when the new behavior is about device intelligence, domain reasoning, or user-personalized
control.

Use:

```text
skills/custom/<name>/
├── SKILL.md
├── references/
│   ├── knowledge.md
│   ├── decide.md
│   └── learn.md
└── scripts/
    └── actions.py
```

Do not hardcode device-specific reasoning directly into `Brain`.

### Adding an Adapter

Add an adapter when the new work is about protocol integration.

Adapters may:

- discover devices
- map raw device capabilities into Anima's canonical `Device`
- refresh state
- execute protocol commands

Adapters should not:

- call the LLM
- own user memory
- decide policy
- bypass the `DiscoveryOrchestrator`

### Adding Memory Behavior

Route memory reads and writes through `MemoryStore` and related services. Avoid scattering memory logic
inside API routes, adapters, or frontend components.

## 11. Current Limitations

Anima is still early-stage. Current limitations include:

- MIoT support depends on valid local IP and token for ordinary device control.
- Xiaomi Cloud token availability may vary by account, region, and device.
- Not every device type has a mature built-in skill.
- Long-term memory is file-based and single-user by default.
- Security controls are intentionally conservative but still need stronger production hardening.
- Remote access should not be exposed directly to the public internet.
- MQTT is not yet the canonical adapter boundary for current MIoT execution.

## 12. Future Directions

Likely future work includes:

- richer adapter ecosystem
- Matter / Home Assistant integration
- stronger room and multi-user models
- user-facing memory review and correction
- permission and safety policies for high-risk devices
- improved verification and uncertainty reporting
- skill marketplace or community skill installation
- deployment packaging for Raspberry Pi, NAS, or appliance-style installs

## 13. Design Principle Summary

Keep Anima's architecture centered on clear boundaries:

```text
Frontend observes and requests.
API exposes the runtime.
Brain reasons.
Skills encode device intelligence.
Memory stores user context.
Discovery routes commands.
Adapters speak hardware protocols.
Devices remain the source of physical truth.
```

This separation is what allows Anima to grow from a smart-home prototype into a broader Agent OS for
hardware intelligence.
