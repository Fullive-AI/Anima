# Anima 架构护栏

这份文档是给后续在本仓库中工作的 AI / 代码代理看的。

在做架构改动之前先读这份文档。它的目标是保护当前系统的整体形状、模块职责和运行链路，避免后续增量开发把项目悄悄改成一个普通 CRUD 后端，或者一个结构松散的 AI Demo。

## 项目定位

Anima 不是一个普通 Web 后端，它是一个面向智能硬件的运行时编排器。

当前架构围绕下面这条主链路构建：

`设备发现 -> 传感器/事件更新 -> 规则快路径 -> LLM 慢路径 -> 命令执行 -> 记忆/历史 -> 控制台可见`

任何削弱、绕过或打散这条链路的修改，都应视为架构变更，而不是普通重构。

## 核心原则

1. 保持核心层轻量，并以编排为中心。
2. 协议和设备细节必须留在 adapters 内部。
3. 设备智能必须通过 `skills/` 以领域化方式表达。
4. 确定性自动化必须优先走规则，而不是优先问 LLM。
5. 命令执行必须经由 discovery/orchestrator 路由，不能让任意模块直接控设备。
6. 记忆必须是一个明确的子系统，由 brain 使用，不能散落在 API 或 UI 逻辑里。
7. 优先扩展现有模块，不要引入职责重复的平行系统。

## 标准运行时结构

主运行时组装点在 [core/main.py](C:/Users/kprig/fulai/Anima/core/main.py)。

预期的运行时组成如下：

- `SettingsStore`：运行时配置持久化
- `EventBus`：运行时模块之间的异步事件通道
- `MemoryStore`：偏好、历史、学习结果上下文
- `RulesEngine`：确定性的快路径自动化
- `SkillLoader`：加载按设备类型组织的智能包
- `Brain`：基于 LLM 的决策和偏好学习
- `Scheduler`：周期扫描和学习任务
- `DiscoveryOrchestrator`：设备注册表和命令路由
- `Adapter(s)`：设备/协议接入层，当前主要是 MIoT
- `FastAPI`：外部控制和观测入口

不要把业务编排逻辑迁移到前端、API 路由或 adapters 中。

## 模块职责

### `core/main.py`

负责进程装配和顶层运行时 wiring。

这里必须继续承担这些职责：

- 实例化核心子系统
- 注册事件订阅
- 触发初始扫描
- 注册定时任务
- 组装 API app state

不要把 `main.py` 改成协议逻辑、UI 逻辑或 prompt 逻辑承载点。

### `core/discovery.py`

负责系统级设备注册表和命令路由。

它应该负责：

- 聚合各 adapter 的发现结果
- 维护标准的 `device_id -> Device` 映射
- 维护 `device_id -> adapter` 路由映射
- 提供设备查询能力
- 把命令路由到正确 adapter

它不应该负责：

- 小米协议细节
- prompt 构造
- 直接做 LLM 决策

### `adapters/`

Adapter 只负责协议接入。

它们可以负责：

- 发现设备
- 订阅设备状态变化
- 把通用动作翻译成协议原生命令
- 把原始设备信息映射成标准 `Device` 模型

它们不应该负责：

- 决策策略
- 直接调用 LLM
- 管理用户记忆
- 绕过 orchestrator 直接形成私有控制链路

如果要接新协议，优先新增 adapter，不要把协议分支逻辑散落进 core 模块。

### `core/rules/engine.py`

负责确定性、低延迟、安全导向的自动化。

规则必须保持：

- 快
- 本地可执行
- 可预测
- 不依赖 LLM 可用性

不要把规则折叠进 prompt 逻辑，不要改成“先问模型再决定”。

### `core/brain/engine.py`

负责慢路径 AI 决策，以及周期性偏好学习。

Brain 应该：

- 接收标准 `Device` 和上下文/传感器数据
- 按设备类型加载 skill
- 用 skills + memory + device state 拼装 prompt 上下文
- 调用模型
- 把结构化输出解析成 `DeviceCommand`
- 把决策写入 memory/history

Brain 不应该：

- 直接处理协议细节
- 直接扫描网络
- 演化成一个脱离设备 skill 的通用聊天服务

### `core/brain/skill_loader.py` 和 `skills/`

`skills/` 是一等架构概念，不是可有可无的内容目录。

Skill 通过以下内容定义设备类型智能：

- `skills/system/` 用于系统内置 skill
- `skills/custom/` 用于用户新增 skill
- `SKILL.md`
- `references/knowledge.md`
- `references/decide.md`
- `references/learn.md`
- 可选 `scripts/actions.py`

当要支持新的“智能设备类型”时：

- 优先新增或扩展 skill
- 不要把设备类型专属决策硬编码进 `Brain`

### `core/memory/store.py`

负责用户上下文和决策历史持久化。

当前存储方式刻意保持简单，直接走文件。

它应该继续成为这些信息的唯一来源：

- preferences
- action history
- learned profile

不要把 memory 写入散落到各个无关模块中，统一走 `MemoryStore`。

### `core/api/routes.py`

API 是系统边界层，不是系统核心。

路由可以做的事：

- 暴露运行时状态
- 触发扫描
- 提交命令
- 暴露设置和历史

路由不应该做的事：

- 复制编排逻辑
- 承载本应属于 runtime 模块的业务规则
- 变成系统行为真正发生的唯一地方

### `dashboard/`

Dashboard 是运维/操作控制台。

它应该：

- 展示设备、决策、设置和控制入口
- 调用 API

它不应该：

- 藏业务逻辑
- 成为自动化决策的真实来源
- 依赖设备协议细节

## 标准事件与命令链路

自动行为的标准运行顺序应该是：

1. Adapter 发现设备，或检测到设备状态/传感器变化。
2. 运行时发出或接收标准事件。
3. discovery/runtime 状态中的设备传感器缓存被更新。
4. `RulesEngine` 先评估。
5. 如果规则没处理，再由 `Brain` 基于 skill + memory + model 决策。
6. 产生一个 `DeviceCommand`。
7. `DiscoveryOrchestrator.execute_command()` 将命令路由到所属 adapter。
8. Adapter 将通用命令翻译为协议调用并执行。
9. 结果和决策历史通过 memory/API/dashboard 对外可见。

不要引入这些旁路：

- adapter 根据私有策略直接执行命令
- API handler 直接控设备
- 前端逻辑绕过后端编排
- brain 直接写协议客户端

## 必须保持清晰的边界

这些边界是有意设计的，不要随意打散：

- `core/` 负责编排
- `adapters/` 负责协议和设备接入
- `skills/` 负责设备类型智能内容
- `dashboard/` 负责展示和交互
- `tests/` 应验证上述契约

## 推荐扩展路径

做新功能时，优先按下面的方式扩展：

### 新增设备协议

- 在 `adapters/` 下新增 adapter
- 在运行时装配时注册它
- 保持 discovery / execute 契约与 `BaseAdapter` 一致

### 新增智能设备类型

- 在 `skills/` 下新增 skill
- 在 adapter 中补设备类型映射
- 复用现有 brain 流程

### 新增自动化行为

- 如果是确定性、安全关键逻辑，写 rule
- 如果是上下文相关、偏好驱动逻辑，写 skill / prompt 扩展

### 新增 UI 功能

- 通过 API 暴露后端已有能力
- 前端继续保持为 runtime 的薄控制台

## 需要格外谨慎的改动

下面这些都应视为架构变更，在大改之前先明确记录理由：

- 替换事件驱动运行时模型
- 绕过 `DiscoveryOrchestrator` 直接分发命令
- 把 rules 和 brain 合并成一个无分层的决策层
- 把设备类型智能从 `skills/` 中抽走
- 把编排逻辑搬进 API handler 或前端组件
- 用其他存储替换文件 memory，且改变模块归属关系
- 在 discovery 之外再引入第二套设备真相源

## 给后续 AI 的审查清单

在动代码前，先检查：

1. 我是否保留了 `discover -> rules -> brain -> execute -> memory -> dashboard` 这条链？
2. 我是否把设备协议逻辑留在 adapter 内？
3. 我是否让 AI 行为继续由按设备类型组织的 skill 驱动？
4. 我是否让命令继续通过 discovery 路由，而不是直接控设备？
5. 我是在现有架构上做聚焦扩展，而不是平行造一套系统？

如果以上任一项答案是否定的，先停下来，明确说明这是架构变更，并给出理由。

## 后续工作的默认准则

默认采用局部、最小、保留架构的改法。

如果一个任务可以通过以下方式解决：

- 扩展 adapter
- 扩展 skill
- 扩展 rule
- 通过 API 暴露现有运行时能力
- 改进 dashboard，但不把业务逻辑搬进去

那么这就是优先路径。
