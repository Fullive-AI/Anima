# Anima Architecture Guardrails

This document is for future AI/code agents working in this repository.

Read this before making architectural changes. The goal of this file is to preserve the current system shape, module responsibilities, and runtime chain so that incremental work does not silently collapse the design into a generic CRUD app or a loosely structured AI demo.

## Purpose

Anima is not a standard web backend. It is a runtime orchestrator for intelligent hardware.

The current architecture is built around this chain:

`device discovery -> sensor/event update -> rules fast path -> LLM slow path -> command execution -> memory/history -> dashboard visibility`

Any change that weakens or bypasses this chain should be treated as an architectural change, not a refactor.

## Core Principles

1. Keep the core thin and orchestration-focused.
2. Keep protocol/device specifics inside adapters.
3. Keep device intelligence domain-specific through `skills/`.
4. Keep deterministic automation in rules before LLM decisions.
5. Keep command execution routed through discovery/orchestration, not directly from random modules.
6. Keep memory as an explicit subsystem used by the brain, not hidden inside API handlers or UI logic.
7. Prefer extending the existing modules over introducing parallel systems that duplicate responsibility.

## Canonical Runtime Shape

The main runtime is assembled in [core/main.py](C:/Users/kprig/fulai/Anima/core/main.py).

The intended composition is:

- `SettingsStore`: runtime configuration persistence
- `EventBus`: async event channel between runtime modules
- `MemoryStore`: preferences/history/learned context
- `RulesEngine`: deterministic fast-path automation
- `SkillLoader`: loads device-specific intelligence packages
- `Brain`: LLM-based decision-making and preference learning
- `Scheduler`: periodic scan / learning jobs
- `DiscoveryOrchestrator`: device registry + command routing
- `Adapter(s)`: device/protocol integration, currently MIoT
- `FastAPI`: external control and observation surface

Do not move business orchestration into the frontend, API routes, or adapters.

## Module Responsibilities

### `core/main.py`

Owns process assembly and top-level runtime wiring.

Must remain the place where:

- core subsystems are instantiated
- event subscriptions are registered
- the initial scan is triggered
- scheduler jobs are registered
- API app state is assembled

Do not turn `main.py` into protocol logic, UI logic, or prompt logic.

### `core/discovery.py`

Owns the system-wide device registry and command routing.

It should:

- aggregate discovered devices from adapters
- maintain the canonical `device_id -> Device` mapping
- maintain the `device_id -> adapter` routing map
- expose lookup APIs for devices
- route commands to the correct adapter

It should not:

- contain protocol-specific Xiaomi logic
- contain prompt construction
- make direct LLM decisions

### `adapters/`

Adapters are responsible for protocol integration only.

They may:

- discover devices
- subscribe to device state changes
- translate generic actions into protocol-native calls
- map raw device details into canonical `Device` models

They should not:

- decide policy
- call the LLM directly
- own user memory
- bypass the orchestrator for command execution

If a new protocol is added, prefer a new adapter rather than branching protocol logic through core modules.

### `core/rules/engine.py`

Owns deterministic, low-latency, safety-oriented automation.

Rules must remain:

- fast
- local
- predictable
- independent of LLM availability

Do not fold rules into prompt logic. Do not replace rules with "ask the model first".

### `core/brain/engine.py`

Owns slow-path AI decision-making and periodic preference learning.

The brain should:

- receive a canonical `Device` and sensor/context data
- load the relevant skill by device type
- assemble prompt context from skills + memory + device state
- call the model
- parse structured output into `DeviceCommand`
- record decisions to memory/history

The brain should not:

- directly control protocol details
- scan the network
- become a generic chat server disconnected from device skills

### `core/brain/skill_loader.py` and `skills/`

`skills/` is a first-class architecture concept, not optional content.

Skills define device-type intelligence through:

- `skill.yaml`
- `knowledge.md`
- `prompts/decide.md`
- `prompts/learn.md`
- optional `actions.py`

When adding support for a new intelligent device type:

- add or extend a skill first
- do not hardcode device-specific decision logic into `Brain`

### `core/memory/store.py`

Owns persistent user context and decision history.

Current storage is intentionally simple and file-based.

It should remain the source of:

- preferences
- action history
- learned profile content

Do not scatter memory writes across random modules. Route them through `MemoryStore`.

### `core/api/routes.py`

The API is a boundary layer, not the core of the system.

Routes may:

- expose runtime state
- trigger scans
- submit commands
- expose settings and history

Routes should not:

- duplicate orchestration logic
- embed business rules that belong in runtime modules
- become the only place where the system behavior exists

### `dashboard/`

The dashboard is an operator console.

It should:

- visualize devices, decisions, settings, and controls
- call the API

It should not:

- contain hidden business logic
- become the source of truth for automation decisions
- depend on device protocol details

## Canonical Event and Command Chain

This is the intended runtime order for automatic behavior:

1. An adapter detects a device or sensor/state update.
2. The runtime emits or receives a canonical event.
3. Device sensor cache is updated in discovery/runtime state.
4. `RulesEngine` evaluates first.
5. If no rule handles the case, `Brain` decides using skill + memory + model.
6. A `DeviceCommand` is produced.
7. `DiscoveryOrchestrator.execute_command()` routes the command to the owning adapter.
8. The adapter translates and executes the protocol call.
9. The result and decision history remain observable through memory/API/dashboard.

Do not introduce side paths where:

- adapters execute commands based on private policy
- API handlers call devices directly
- frontend logic bypasses backend orchestration
- the brain writes directly to protocol clients

## Stable Boundaries To Preserve

These boundaries are intentional and should not be blurred casually.

- `core/` owns orchestration
- `adapters/` own protocol/device integration
- `skills/` own device-type intelligence content
- `dashboard/` owns presentation and operator interaction
- `tests/` should validate the above contracts

## Preferred Extension Paths

When implementing new work, prefer these shapes:

### Add a new device protocol

- add a new adapter under `adapters/`
- register it in runtime assembly
- keep discovery and execute contracts aligned with `BaseAdapter`

### Add a new intelligent device type

- add a new skill under `skills/`
- map the device type in the adapter
- reuse the existing brain flow

### Add a new automation behavior

- if deterministic and safety-critical, add a rule
- if contextual and preference-based, add or extend a skill/prompt path

### Add UI functionality

- expose backend capability through API
- keep frontend as a thin console over the runtime

## Changes That Require Extra Caution

Treat the following as architectural changes and document them before editing broadly:

- replacing the event-driven runtime model
- bypassing `DiscoveryOrchestrator` for command dispatch
- merging rules and brain into one undifferentiated decision layer
- moving device-specific intelligence out of `skills/`
- moving orchestration logic into API handlers or frontend components
- replacing file-based memory with another store in a way that changes module ownership
- introducing a second source of truth for devices outside discovery

## Code Review Heuristics For Future AI

Before making a change, check:

1. Am I preserving the chain `discover -> rules -> brain -> execute -> memory -> dashboard`?
2. Am I keeping device protocol logic inside adapters?
3. Am I keeping AI behavior device-type-driven through skills?
4. Am I routing commands through discovery rather than direct device calls?
5. Am I adding a focused extension to the existing architecture instead of creating a parallel subsystem?

If the answer to any of the above is no, stop and justify the architecture change explicitly.

## Practical Rule For Future Work

Default to local, minimal, architecture-preserving changes.

If a task can be solved by:

- extending an adapter
- extending a skill
- extending a rule
- exposing an existing runtime capability through the API
- improving the dashboard without moving business logic into it

then that is the preferred path.
