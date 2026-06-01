# AGENT.md

This file is for coding agents working in the `Anima` repository.

It does not replace product thinking. It defines the current system shape, the architectural boundaries that matter, and the safest way to extend the project without degrading its core design.

## What Anima Is

Anima is an Agent OS for hardware intelligence.

Its current product loop is:

1. Discover available devices, especially Xiaomi / MIoT devices.
2. Normalize them into a unified in-memory device model.
3. Apply fast safety rules first.
4. Use Skill-driven LLM reasoning for non-emergency decisions.
5. Execute commands through adapters.
6. Expose the system through a Dashboard, REST API, and chat-driven operational flows.

Do not reduce Anima to "a smart home dashboard" or "an LLM wrapper for devices". The core idea is:

`devices -> skills -> autonomous decisions -> memory -> evolving behavior`

## Current Reality vs Roadmap

Agents must distinguish between what exists now and what is only described in docs / roadmap.

What is implemented now:

- Single-process Python backend under `core/`
- FastAPI REST API
- React + Vite dashboard under `dashboard/`
- MIoT adapter with local scan, cloud onboarding, token activation, and command execution
- Skill loading from `skills/`
- LangGraph-based Brain decision pipeline
- File-based memory in `data/memory`
- Polling-based frontend refresh

What is not the primary runtime path today:

- MQTT as the main production event backbone
- WebSocket-driven realtime dashboard
- Multi-room orchestration as a first-class UX
- General multi-adapter ecosystem beyond MIoT
- Full conversational assistant experience

Do not implement as if roadmap items already exist.

## Architecture Snapshot

The current runtime center is [`core/main.py`](./core/main.py).

Main modules:

- `core/main.py`: composition root, startup flow, event wiring
- `core/api/routes.py`: REST API surface and onboarding/config endpoints
- `core/devices/discovery.py`: adapter orchestration, device registry, command dispatch
- `core/rules/engine.py`: fast-path rule evaluation
- `core/brain/engine.py`: LLM decision pipeline and environment summarization
- `core/brain/skill_loader.py`: loads system/custom skills from disk
- `core/memory/store.py`: preferences/history/learned profile storage
- `core/brain/react_agent.py`: task-oriented chat routing for discovery and skill creation flows
- `adapters/miot/`: current primary hardware integration
- `dashboard/src/`: polling-based operator console

Runtime shape:

1. Backend starts.
2. Skills load.
3. Default rules load.
4. Devices are scanned and registered.
5. Missing system skills may be auto-generated.
6. If Xiaomi devices need tokens, onboarding QR flow may start.
7. UI polls REST endpoints for devices, decisions, and environment.

## Core Design Principles

### 1. Skill-first, not hardcoded business logic

If behavior depends on device semantics, domain knowledge, or autonomous decision policy, prefer expressing it through the Skill system.

Bad direction:

- putting device intelligence directly into the API layer
- burying domain policy in frontend components
- encoding product semantics only inside adapter code

Good direction:

- adapter exposes capabilities and sensor state
- skill provides knowledge and prompts
- brain assembles context and decides

### 2. Rules are for safety and immediacy

The Rules Engine is the fast path.

Use rules for:

- emergency thresholds
- deterministic safety reactions
- low-latency fallback behavior

Do not overload rules with rich adaptive product logic that belongs in Skills or Brain.

### 3. Adapters describe device reality, not user intent

Adapters should:

- discover devices
- refresh state
- expose capabilities
- execute commands

Adapters should not become the place where user preference logic or autonomous policy lives.

### 4. Dashboard is an operator console, not the system of record

The Dashboard should reflect backend state and trigger backend actions.

Do not move core automation logic into the frontend.
Do not make the frontend the only place where critical workflows exist unless explicitly intended.

### 5. Preserve human-readable memory

Anima intentionally uses markdown/json memory files instead of a database-first design.

Do not introduce a database for convenience unless the change is explicitly justified by product scope.

## File and Ownership Boundaries

Use these boundaries when deciding where to implement a change.

### `core/brain/`

Owns:

- prompt context assembly
- LLM invocation
- capability-aware action selection
- environment summarization
- learning from history

Do not put transport concerns or UI-specific formatting here.

### `skills/`

Owns:

- device/domain knowledge
- decision prompts
- learning prompts
- chat prompts
- skill actions where relevant

When a change is about "how this device type should behave intelligently", start here.

### `adapters/`

Owns:

- protocol-specific discovery
- device instantiation
- state extraction
- command execution

When a change is about "how to talk to this hardware", start here.

### `core/api/`

Owns:

- HTTP exposure of backend capabilities
- onboarding/config flows
- orchestration of backend modules per request

Do not hide core decision policy in route handlers.

### `dashboard/`

Owns:

- presenting devices, environment, decisions, settings
- triggering backend actions
- onboarding and control flows for operators

Prefer thin UI over duplicated business logic.

## Current Product Strengths

Agents should protect these strengths instead of accidentally diluting them.

- Xiaomi onboarding is a real differentiator: local discovery + QR login + token activation
- Skill-based intelligence is the conceptual center of the product
- Capability reflection for MIoT gives the system flexible device control
- Environment snapshots let the Brain reason beyond a single device
- Auto-generation of missing system skills is part of the product identity

If a proposed change weakens one of these, reconsider the design.

## Known Constraints

### The frontend is polling-based

Current hooks poll REST endpoints.
Do not assume realtime subscriptions exist.
If adding realtime, treat it as a deliberate architecture upgrade, not a hidden side edit.

### MQTT exists but is not the main runtime path

There is MQTT code in `core/runtime/mqtt.py`, but the core system is not currently driven by MQTT in production flow.
Do not route new critical features through MQTT unless you are intentionally evolving the architecture.

### Rooms are weakly implemented

The product language references rooms, but current implementation is environment/device-centric rather than room-centric.
Do not design features that depend on robust room modeling unless you also add that model explicitly.

### Chat is task-routing, not a full assistant

The current chat layer is operational and narrow.
Do not assume broad natural-language control exists across all product areas.

## Change Heuristics

When making changes, use this decision order:

1. Is this a hardware/protocol concern?
   Put it in `adapters/`.
2. Is this autonomous behavior or domain reasoning?
   Put it in `skills/` and possibly `core/brain/`.
3. Is this deterministic safety logic?
   Put it in `core/rules/`.
4. Is this exposure / transport / request orchestration?
   Put it in `core/api/`.
5. Is this presentation or operator workflow?
   Put it in `dashboard/`.

## Things Agents Should Avoid

- Do not bypass the Skill system just because a feature is faster to hardcode.
- Do not move product semantics into one-off frontend conditionals.
- Do not treat README roadmap items as implemented APIs.
- Do not add persistent storage layers casually.
- Do not break the unified `Device / Capability / Sensor / DeviceCommand` model without strong reason.
- Do not make MIoT-specific assumptions leak everywhere if the code can stay adapter-agnostic.
- Do not silently replace existing onboarding flows with manual-only alternatives.

## Preferred Extension Paths

### Add support for a new device type

Usually requires:

- adapter mapping or capability extraction updates
- a system skill for that device type
- optional dashboard labeling/icon tweaks
- tests for discovery, capability reflection, and decision path

### Add a new autonomous behavior

Usually requires:

- skill prompt / knowledge updates
- possibly Brain context improvements
- optionally a fast safety rule if latency matters
- tests around decision parsing and capability sanitization

### Add a new operator workflow

Usually requires:

- API endpoint if backend state/action is needed
- dashboard UI
- preserving the backend as the source of truth

## Testing Expectations

Before considering work complete:

- run relevant tests under `tests/`
- prefer adding or updating tests when changing Brain, adapter, API, or onboarding logic
- protect end-to-end behavior, not just unit-level helpers

Current suite covers integration, brain behavior, MIoT adapter behavior, and environment refresh. Respect that coverage model.

## Practical Notes for Future Agents

- Read `README.md` for product framing, but trust code for implementation truth.
- Read `ARCHITECTURE_GUARDRAILS.md` alongside this file for higher-level constraints.
- If a request conflicts with the current architecture, state the tradeoff explicitly before changing direction.
- If you need to choose between a quick patch and preserving the Skill-centered design, prefer preserving the design unless the user asks for a tactical shortcut.

## In One Sentence

Anima is currently a Skill-centered, MIoT-led, single-process hardware intelligence system with a polling dashboard and a stronger backend architecture than its UI might suggest.
