# Anima 当前设计

> Anima 当前实现导向的设计文档。
>
> 本文描述 Anima 当前的系统结构。早期原始方案见
> [2026-03-17-anima-design.md](./2026-03-17-anima-design.md)。面向未来贡献者和 agent 的架构护栏见
> [ARCHITECTURE_GUARDRAILS.md](../../ARCHITECTURE_GUARDRAILS.md)。

## 1. 目标

Anima 是一个面向硬件智能的开源 Agent OS。它的设计目标是通过本地优先的运行时，把大语言模型与物理设备连接起来，使系统能够发现设备、理解设备状态、通过设备专属技能进行推理、执行安全动作，并随着时间学习用户偏好。

Anima 不只是一个设备仪表盘，也不只是套在智能家居 API 外面的聊天壳。它的核心目标是让硬件行为具备上下文感知能力：

```text
perceive -> plan -> act -> verify -> remember
感知 -> 规划 -> 执行 -> 验证 -> 记忆
```

当前实现重点覆盖智能家居设备，尤其是小米 / 米家 / MIoT 设备，同时保持适配器边界开放，以便未来接入更多协议。

## 2. 运行时概览

当前运行时由 `core/main.py` 组装为单个 Python 进程。Dashboard 是独立的 Vite/React 前端，通过 REST API 和 Server-Sent Events 与后端通信。

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
│  Brain ───── SkillLoader ─────Skills           │
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

MQTT 仍作为运行时基础设施保留在仓库中，但当前 MIoT 控制路径并不以 MQTT 为中心。主要命令路径是：

```text
Brain / API -> DiscoveryOrchestrator.execute_command() -> owning Adapter.execute() -> device protocol
```

## 3. 主要运行时组件

### `core/main.py`

`core/main.py` 负责进程组装和顶层运行时接线。它创建：

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
- `MIoTAdapter`、`VirtualAdapter` 等适配器
- FastAPI 应用状态

它还负责注册事件处理器和定时任务。

当前 scheduler 任务：

| 任务 | 函数 | 间隔 |
|---|---|---:|
| `device_scan` | `discovery.scan` | 7200 秒 |
| `environment_refresh` | `discovery.refresh_device_states` | 60 秒 |
| `learn_preferences` | `preference_learner.run_now` | 300 秒 |
| `brain_tick` | scheduler 驱动的 brain cycle | 60 秒 |

Scheduler 会直接调用注册函数。它不把 EventBus 当作计时机制。扫描、刷新或命令执行过程中，这些函数可以进一步产生事件。

### `DiscoveryOrchestrator`

`core/devices/discovery.py` 维护规范设备注册表和命令路由。

它负责：

- 请求适配器发现设备
- 维护 `device_id -> Device`
- 维护 `device_id -> adapter`
- 通过适配器的 `subscribe()` 刷新设备状态
- 发出设备和传感器事件
- 把命令路由给拥有目标设备的适配器

这个边界防止任意模块直接控制协议客户端。

### `EventBus`

`core/events/bus.py` 是进程内异步事件总线。它用于运行时可见性，以及模块之间的响应式协作。

重要事件类别包括：

- 设备发现
- 传感器更新
- 动作执行

EventBus 不是唯一运行路径。例如，定时任务直接注册在 Scheduler 中，设备命令通过 `DiscoveryOrchestrator` 路由。

### `RulesEngine`

`core/rules/engine.py` 是本地自动化和安全导向逻辑的确定性快速路径。规则应保持本地、可预测，并且不依赖 LLM 可用性。

长期架构方向是：

```text
rules first -> LLM slow path only when reasoning is needed
规则优先 -> 只有需要推理时才进入 LLM 慢路径
```

### `Brain`

`core/brain/engine.py` 是慢路径推理层。它组合：

- 用户消息或 scheduler 任务
- 当前设备状态
- 环境快照
- 可用技能
- 记忆上下文
- LLM 输出解析
- 动作执行与验证
- history / memory 记录

Brain 不应包含协议专属控制逻辑。它负责规划动作，并通过 skill 与 discovery/adapter 边界委托执行。

当前 Brain 支持：

- LangGraph planner/executor 流程
- 带工具调用的 ReAct 风格流式聊天
- scheduler 驱动的 brain tick
- skill 上下文构造
- 动作执行重试与验证
- 聊天轮次记录
- OpenAI 兼容 LLM 后端

## 4. 设备适配器层

适配器把 Anima 的规范动作和设备模型翻译为具体设备协议调用。

抽象接口位于 `adapters/base.py`：

```python
async def discover() -> list[Device]
async def subscribe(device: Device) -> None
async def execute(device_id: str, action: str, params: dict) -> ActionResult
```

### 当前 MIoT 适配器

当前 MIoT 适配器位于 `adapters/miot/`。

它支持多种设备来源：

- 持久化配置中的手动设备
- 缓存的小米云设备
- 凭据可用时的小米云发现
- 本地 MIoT UDP 广播发现
- 用于小米云设备和 token 同步的二维码登录流程

对普通 MIoT 设备控制而言，Anima 仍然需要可访问的本地 IP 和有效 token。小米云登录主要用于同步设备元数据和 token。如果小米云没有返回某个设备的有效 token，该设备可能停留在 `needs_token` 状态，并需要手动激活。

### 虚拟适配器

虚拟适配器提供本地测试/演示设备，便于在不依赖物理硬件的情况下验证运行时。

### 未来适配器

新协议应作为新适配器添加，而不是把协议逻辑分支写进 Core。

候选未来适配器包括：

- Matter
- Home Assistant bridge
- BLE 传感器
- HTTP API 设备
- 私有厂商 API

## 5. 技能系统

Skills 是 Anima 的设备智能包。它们定义某类设备应该如何被推理，而不仅仅是如何开关设备。

当前 skill 结构：

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

自定义 skills 使用同样结构，位于：

```text
skills/custom/
```

当前内置 skills 包括：

- `light`
- `humidifier`
- `air_conditioner`
- `air_purifier`
- `speaker`
- `coordinator`
- `device_discovery`
- `skill_creator`

### Skill 生命周期

Skills 参与多个运行阶段：

1. **发现 / 加载**：`SkillLoader` 发现 system 和 custom skills。
2. **规划**：Brain 读取轻量 skill 摘要并选择相关 skill。
3. **上下文构造**：Brain 根据当前设备状态、memory、learned profile 和 skill references 构建设备专属上下文。
4. **决策**：LLM 基于 skill prompt 产出结构化决策。
5. **执行**：skill action 代码把决策转换成可执行设备命令。
6. **反馈**：执行结果、验证状态和 history 记录进入 memory 与未来学习流程。

### Skill Creator

`skill_creator` 可以根据用户请求搭建或生成自定义 skill 包。它的作用是在不修改 Core 的情况下扩展 Anima 的行为层。生成的 skills 仍应遵守标准 skill 结构和动作边界。

## 6. 记忆系统

Anima 的 memory 是文件型系统，并刻意保持简单。默认用户记忆目录是：

```text
data/memory/users/default/
```

重要文件：

| 文件 | 作用 |
|---|---|
| `preferences.md` | 人类可读的偏好笔记 |
| `history.json` | 最近决策、聊天轮次、动作和验证记录 |
| `learned.json` | 按设备类型归一化的 learned profiles |
| `memory_state.json` | 提取 cursor/state |
| `memories/{slug}.json` | 按主题组织的长期记忆条目 |

### 三层上下文 API

当前 memory 系统组织为分层上下文 API：

| 层级 | 作用 | 典型用途 |
|---|---|---|
| L1 核心上下文 | 始终加载的小上下文，例如偏好摘要和最后交互 | planner 和 chat 上下文 |
| L2 摘要层 | learned profile 类型和 memory topic 目录 | 帮助 planner 知道有哪些 memory |
| L3 按需详情 | 详细的 confirmed memories 和 learned profiles | 设备专属 skill 决策时加载 |

这个设计让 prompt 保持较小，同时只在相关时检索详细长期记忆。

### 证据与过度学习控制

长期记忆使用结构化字段，例如：

- `claim_type`
- `status`
- `confidence`
- `evidence_count`
- `positive_evidence`
- `negative_evidence`
- `device_types`
- `device_ids`
- `scenes`

默认只有 confirmed memories 应影响设备 skill 决策。Candidate memories 可以用于调试或审阅展示，但不应被当作稳定偏好。

## 7. API 和 Dashboard

FastAPI 应用创建于 `core/api/routes.py`。它暴露运行时状态和控制界面。

重要 API 区域包括：

- 设备列表和命令执行
- 房间/设备元数据
- 虚拟设备管理
- 环境刷新
- 聊天和流式聊天
- memory 检查
- skill 检查与编辑
- LLM 设置
- 小米二维码登录和 token 同步

Dashboard 是 React/Vite 操作控制台。它展示：

- 设备和设备控制
- 环境状态
- assistant/chat 回复
- 执行 trace
- memory 状态
- 设置和小米接入流程

前端不应拥有业务逻辑。它应保持为后端运行时之上的控制和观察界面。

## 8. 当前执行流程

### 用户聊天流程

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

### Scheduler 流程

```text
Scheduler
  -> environment_refresh / brain_tick / learn_preferences / device_scan
  -> direct function call
  -> optional EventBus events
  -> Brain or Memory services where relevant
```

### 传感器更新流程

```text
Adapter refresh
  -> DiscoveryOrchestrator updates cached sensor values
  -> EventBus emits SENSOR_UPDATED
  -> main runtime may request a throttled brain cycle
  -> Brain evaluates whether any action is needed
```

### 设备命令流程

```text
Brain or API
  -> DiscoveryOrchestrator.execute_command(device_id, action, params)
  -> owning Adapter.execute()
  -> protocol-specific command
  -> ActionResult
  -> ACTION_EXECUTED event
  -> history/memory recording
```

## 9. 身份与设备 ID

MIoT 设备身份是 token-aware 的。当有效 token 可用时，适配器会构建稳定的 token-based device ID，而不会暴露原始 token。没有有效 token 的待激活设备，可能临时使用 DID/IP-based ID，直到激活或与云端数据对齐。

这很重要，因为本地 IP 地址可能变化，而 token 派生的 ID 在重启和网络变化之间更稳定。

## 10. 开发与扩展指南

### 添加 Skill

当新工作涉及设备智能、领域推理或用户个性化控制时，应添加 skill。

使用：

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

不要把设备专属推理硬编码进 `Brain`。

### 添加适配器

当新工作涉及协议集成时，应添加 adapter。

Adapters 可以：

- 发现设备
- 把原始设备能力映射到 Anima 规范 `Device`
- 刷新状态
- 执行协议命令

Adapters 不应：

- 调用 LLM
- 拥有用户 memory
- 决定策略
- 绕过 `DiscoveryOrchestrator`

### 添加 Memory 行为

Memory 读写应通过 `MemoryStore` 和相关 services。避免把 memory 逻辑分散到 API routes、adapters 或前端组件里。

## 11. 当前限制

Anima 仍处于早期阶段。当前限制包括：

- 普通设备控制下，MIoT 支持依赖有效本地 IP 和 token。
- 小米云 token 可用性可能受账号、地区和设备影响。
- 并非每个设备类型都有成熟的内置 skill。
- 长期 memory 基于文件，默认单用户。
- 安全控制刻意保守，但生产级加固仍需增强。
- 远程访问不应直接暴露到公网。
- MQTT 还不是当前 MIoT 执行的规范 adapter 边界。

## 12. 未来方向

可能的未来工作包括：

- 更丰富的 adapter 生态
- Matter / Home Assistant 集成
- 更强的房间和多用户模型
- 面向用户的 memory 审阅和修正
- 高风险设备的权限与安全策略
- 更好的验证和不确定性报告
- skill marketplace 或社区 skill 安装
- 面向树莓派、NAS 或 appliance 风格安装的部署打包

## 13. 设计原则总结

让 Anima 的架构围绕清晰边界展开：

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

中文理解：

```text
前端负责观察和发起请求。
API 暴露运行时能力。
Brain 负责推理。
Skills 编码设备智能。
Memory 存储用户上下文。
Discovery 路由命令。
Adapters 负责硬件协议。
设备始终是物理真相的来源。
```

这种分离让 Anima 能够从智能家居原型逐步成长为更广义的硬件智能 Agent OS。
