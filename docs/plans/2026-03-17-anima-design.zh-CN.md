[English](./2026-03-17-anima-design.md) | [中文](./2026-03-17-anima-design.zh-CN.md)

# Anima — Make Every Hardware Intelligent

> 一个开源的 Agent OS，自动发现你的硬件设备，为每一台设备赋予 AI 技能，使它们能够自主感知、决策与协作。

## 项目名称：Anima

**Anima** — 拉丁语，意为"灵魂"。这个名字精准传达了项目的核心使命：为你拥有的每一件硬件注入智能，**Make Every Hardware Intelligent**。正如"anima"赋予无生命之物以生命，本项目赋予被动设备以自主智能。

为什么叫 Anima：
- **语义契合**："为硬件注入灵魂"与"让每一件硬件都拥有智能"完美呼应
- **简短易记**：5 个字母，任何语言都容易发音
- **国际化友好**：拉丁词根，全球通用
- **品牌潜力**：辨识度强，与"Home Assistant / OpenHAB / Domoticz"形成鲜明区分

---

## 核心理念

**"Intelligence scales with what you have."**

系统的前提不是"你需要什么传感器"，而是 **"what do you have — I'll use it."**

- 零前置条件——无需指定硬件
- 1 台设备 = 控制 1 台，8 台设备 = 控制 8 台
- 高级功能（生物识别、空间映射）仅在用户拥有相应硬件时才激活
- 用户可随时添加新设备；系统自动发现并集成
- 自适应智能层，而非僵化的自动化平台

---

## 架构概览：薄核心 + MQTT 设备层

```
┌─────────────────────────────────────────────────────────────┐
│                        核心（单进程）                         │
│                                                             │
│  ┌───────────┐   ┌───────────┐   ┌────────────┐            │
│  │  发现服务  │   │  事件总线  │   │   调度器    │            │
│  │ (设备扫描) │──▶│ (内部神经  │◀──│ (定时/周期) │            │
│  └───────────┘   │   系统)   │   └────────────┘            │
│                   └─────┬─────┘                             │
│            ┌────────────┼────────────┐                      │
│            ▼            ▼            ▼                      │
│  ┌───────────┐  ┌────────────┐  ┌───────────┐              │
│  │  规则引擎  │  │  LLM 大脑  │  │   记忆体   │              │
│  │ (快速通道, │  │ (AI 决策   │  │ (用户偏好, │              │
│  │  安全保障) │─▶│   引擎)    │◀─│  历史记录, │              │
│  └───────────┘  └────────────┘  │  学习成果) │              │
│                        │         └───────────┘              │
│            ┌───────────┼───────────┐                        │
│            ▼           ▼           ▼                        │
│  ┌───────────┐  ┌───────────┐  ┌────────────┐              │
│  │  控制面板  │  │ 聊天 API  │  │ MQTT 客户端 │              │
│  │ (Web UI)  │  │ (Telegram │  │ (设备通信)  │              │
│  │           │  │  /微信)    │  │            │              │
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
                  │适配器 │ │适配器 │ │桥接器  │
                  └──────┘ └──────┘ └───────┘
```

### 设计理由

- **单进程核心**：部署简单（一个容器），参照 OpenClaw
- **MQTT 设备层**：IoT 行业标准；Zigbee2MQTT、Z-Wave JS 等可原生接入
- **社区友好**：贡献者只需编写一个适配器（3 个方法）或一个技能（3 个文件），无需触碰核心代码
- **第一阶段一体化**：`docker compose up` 全部搞定。适配器后续可拆分为独立进程

---

## 核心模块

### 发现服务（Discovery）

- 启动时自动扫描本地网络：mDNS（Matter/HomeKit）+ MIoT 扫描（小米）+ SSDP（UPnP）
- 发现新设备 → 发送事件到事件总线 → 自动匹配对应技能
- 周期性重新扫描（设备可能上线/离线）
- 也支持手动添加设备（输入 IP/token）

### 事件总线（EventBus）

- 内部神经系统；所有模块通过事件通信
- 事件类型：`device.discovered`、`sensor.updated`、`rule.triggered`、`action.executed`、`user.command`
- 异步处理，基于 Python asyncio

### 规则引擎（Rules Engine）

- **快速通道**：不涉及 LLM，毫秒级响应
- 安全兜底："温度 > 35°C → 立即开空调"
- 紧急警报："烟雾传感器触发 → 推送通知"
- 用户也可以自定义简单规则

### LLM 大脑（LLM Brain）

- 接收规则引擎无法处理的事件 → 加载相关技能的知识库 + 提示词
- 组装上下文：当前所有传感器数据 + 用户偏好 + 近期决策历史
- 调用 LLM API（用户自带密钥，模型无关：Claude / GPT / DeepSeek / 豆包）
- 解析返回的 Action JSON → 通过 MQTT 执行
- 协调者技能负责跨设备编排

### 记忆体（Memory）

- 借鉴 OpenClaw 的 Markdown 文件方案，不依赖数据库
- `preferences.md`：用户偏好（LLM 可读写）
- `history.json`：决策记录（LLM 学习的数据源）
- `learned.md`：LLM 生成的用户画像，定期更新
- 进化机制：LLM 每日/每周回顾历史，更新 learned.md

### 调度器（Scheduler）

- 周期性设备扫描（每 5 分钟）
- 周期性偏好学习（每天）
- 技能定义的定时任务（如"早上 7:30 起床流程"）

### 控制面板（Dashboard）

三栏布局：
- **左栏**：房间列表，附聚合传感器数据
- **中栏**：房间可视化（设备图标 + 数据，未来：热力图）+ 设备卡片
- **右栏**：AI 决策流（实时展示、可追溯）
- **底栏**：聊天输入框

主要页面：总览、设备管理、技能商店、我的偏好、决策历史、设置

### 聊天 API（Chat API）

- 嵌入控制面板（底部输入栏）
- 通过 HTTP API 对外暴露（`POST /api/chat`）
- 第一阶段：Telegram Bot
- 第二阶段：微信 / Slack / 其他

---

## 技能系统（核心差异化）

### 理念

技能不仅是"如何控制设备"——而是 **"这件硬件如何变得自主智能"**。每个技能包含领域知识、控制逻辑和用户个性化。

### 结构

```
skills/
  humidifier/
    skill.yaml            # 元数据：名称、兼容设备型号、能力声明
    knowledge.md          # 领域知识：舒适湿度范围、季节建议、
                          #   与温度的关系
    actions.py            # 可执行操作：set_humidity、set_mode、turn_on/off
    prompts/
      decide.md           # 决策提示词："当前湿度 {x}，目标 {y}，用户偏好 {z}，该怎么做？"
      learn.md            # 学习提示词："根据用户过去 7 天的行为，总结偏好"
  air_conditioner/
    skill.yaml
    knowledge.md          # 制冷/制热策略、能耗优化、湿度联动
    actions.py
    prompts/
  air_purifier/
    ...
  light/
    ...
  coordinator/            # 特殊技能：跨设备编排
    skill.yaml
    knowledge.md          # "空调开启时湿度下降——需要与加湿器协调"
    prompts/
      orchestrate.md      # 多设备协调决策
```

### 执行流程

```
传感器数据变化
  → 规则引擎：是否超过阈值？
  → 如果是 → 加载相关技能的 knowledge.md + 用户记忆
  → 组装提示词 → 发送到 LLM
  → LLM 返回决策（JSON 动作调用）
  → 执行动作 → 通过 MQTT 控制设备
  → 将结果记录到记忆体（用户偏好演化）
```

### 用户偏好演化

```
memory/
  users/
    default/
      preferences.md      # "偏好睡眠温度 23°C，起床时间 7:30"
      history.json         # 最近 30 天的决策 + 用户反馈
      learned.md           # LLM 总结的用户画像，定期更新
```

### 超越家庭：技能的想象空间

- 扫地机器人技能："有人进门 → 延迟 30 分钟 → 清扫玄关"
- 智能门锁技能："陌生人多次尝试 → 通知用户 + 打开灯光"
- 智能音箱技能："用户醒来 → 播报天气 + 启动咖啡机"
- 工业传感器、办公设备、农业温室……

---

## 设备适配器层

### MQTT 主题设计

```
# ── 设备发现 ──
anima/discovery/announce            # 适配器上报已发现的设备
anima/discovery/scan                # 核心请求重新扫描

# ── 设备状态（适配器 → 核心）──
anima/devices/{device_id}/state     # 设备完整状态
anima/devices/{device_id}/online    # 在线/离线

# ── 设备控制（核心 → 适配器）──
anima/devices/{device_id}/command   # 控制命令

# ── 传感器数据 ──
anima/rooms/{room_id}/sensors       # 房间级聚合传感器数据

# ── 系统事件 ──
anima/system/brain/decisions        # AI 决策日志（控制面板订阅）
anima/system/brain/actions          # 已执行动作日志
```

### 统一设备模型

无论底层协议是小米还是 Matter，核心看到的都是相同的数据结构：

```yaml
# 设备发现报告
device_id: "miot_xiaomi_humidifier_01"
name: "卧室加湿器"
adapter: "miot"
room: null                          # 由用户后续分配
type: "humidifier"                  # 映射到对应技能
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
# 控制命令格式
device_id: "miot_xiaomi_humidifier_01"
action: "set_humidity"
params:
  value: 55
source: "brain"                     # 发起方：brain / rules / user
reason: "用户偏好 55%，当前 45%"     # AI 决策理由（可追溯）
```

### 适配器开发规范

每个适配器是一个独立的 Python 包，结构简洁：

```
adapters/
  miot/
    __init__.py
    adapter.py          # 必须实现 3 个方法：
                        #   discover() → List[Device]
                        #   subscribe(device_id) → 持续状态上报
                        #   execute(device_id, action, params) → 控制执行
    config.yaml         # 适配器配置（扫描间隔、认证方式等）
    README.md
  matter/
    adapter.py
    config.yaml
  homeassistant/
    adapter.py          # 通过 HA REST API 桥接
    config.yaml
```

### 适配器优先级

| 优先级 | 适配器 | 依赖库 | 覆盖范围 |
|--------|--------|--------|----------|
| P0 | MIoT | python-miio | 小米生态系统 |
| P0 | Matter | connectedhomeip | 所有 Matter 认证设备 |
| P1 | Home Assistant | httpx（REST API） | HA 用户已有的所有设备 |
| P2 | Tuya | TinyTuya | 涂鸦贴牌设备 |
| P2 | BLE | bleak | 蓝牙传感器 |

---

## 部署方案

### 第一阶段：Docker Compose

```yaml
services:
  core:
    image: anima/core
    ports:
      - "8080:8080"          # 控制面板 + API
    volumes:
      - ./data:/app/data      # 记忆体 + 配置持久化
    environment:
      - LLM_API_KEY=${LLM_API_KEY}
      - LLM_MODEL=claude-sonnet-4-20250514
      - LLM_BASE_URL=         # 可选自定义端点

  mqtt:
    image: eclipse-mosquitto:2
    ports:
      - "1883:1883"
```

### 用户上手流程

```bash
git clone https://github.com/xxx/anima
cp .env.example .env        # 填入 LLM_API_KEY
docker compose up -d
# 打开 http://localhost:8080
# 系统自动发现设备并开始工作
```

用户**不需要**：
- 手动配置任何设备（自动发现）
- 理解 MQTT（内部细节，对用户不可见）
- 编写任何代码或规则（AI 自主决策）

### 未来部署目标

| 阶段 | 部署方式 |
|------|----------|
| v1 | Docker Compose（任意机器） |
| v2 | 树莓派镜像（刷入 SD 卡即可运行） |
| v3 | NAS 套件（群晖 / 威联通应用商店） |
| v4 | 专用硬件（与硬件厂商合作） |

---

## 开源策略

### 许可证：Apache 2.0

- 与 OpenClaw、Matter SDK 一致
- 允许商业使用（吸引企业贡献者）
- 专利保护（比 MIT 更安全）

### 仓库结构

```
anima/
├── core/                        # 核心进程
│   ├── brain/                   # LLM 决策引擎
│   ├── events/                  # 事件总线
│   ├── rules/                   # 规则引擎
│   ├── memory/                  # 用户记忆系统
│   ├── scheduler/               # 定时任务
│   └── api/                     # HTTP + WebSocket API
├── adapters/                    # 设备适配器
│   ├── miot/
│   ├── matter/
│   └── homeassistant/
├── skills/                      # 技能包
│   ├── humidifier/
│   ├── air_conditioner/
│   ├── light/
│   ├── air_purifier/
│   └── coordinator/
├── dashboard/                   # 前端（React）
├── docker-compose.yml
├── .env.example
├── CLAUDE.md
└── docs/
    ├── getting-started.md
    ├── write-a-skill.md
    ├── write-an-adapter.md
    └── architecture.md
```

### 社区增长（借鉴 OpenClaw 经验）

| 阶段 | 策略 |
|------|------|
| 冷启动 | 3 分钟演示视频："从 docker compose up 到 AI 自动控制我的小米设备"——发布到 Twitter / V2EX / Hacker News |
| 首批贡献者 | 让编写技能和适配器极其简单（3 个方法 / 3 个文件） |
| 生态飞轮 | 技能商店——社区技能一键安装 |
| 国际化 | 英文优先（README、文档、代码注释），中文为第二语言 |

---

## 路线图

### v0.1 —— "它活了"（MVP）

- [ ] 核心框架（事件总线 + 规则引擎 + 调度器）
- [ ] MIoT 适配器（小米设备发现 + 状态 + 控制）
- [ ] 2-3 个基础技能（加湿器 / 空调 / 灯光）
- [ ] LLM 大脑基础决策循环
- [ ] 记忆系统（偏好读写）
- [ ] CLI 交互（极客模式）
- [ ] Docker Compose 部署
- **目标**：`docker compose up` → 自动发现小米设备 → AI 自动调节

### v0.2 —— "现在你能看到了"

- [ ] 控制面板 MVP（设备列表 + 房间管理 + AI 决策日志）
- [ ] 控制面板内嵌聊天
- [ ] Matter 适配器
- [ ] 基于房间的空间数据模型
- [ ] 用户偏好演化（LLM 周期性学习）
- [ ] 更多技能（空气净化器 / 扫地机器人 / 窗帘）

### v0.3 —— "社区来了"

- [ ] 技能商店（在线安装社区技能）
- [ ] 适配器插件系统（`pip install anima-adapter-tuya`）
- [ ] Home Assistant 桥接适配器
- [ ] Telegram Bot 集成
- [ ] 2D 房间热力图（探索性功能）
- [ ] 文档：编写技能指南 / 编写适配器指南

### v0.4 —— "越来越强"

- [ ] 协调者技能增强（复杂多设备场景）
- [ ] 树莓派镜像
- [ ] 多用户支持（家庭成员有不同偏好）
- [ ] 更多聊天平台集成
- [ ] 安全加固（设备控制权限、API 认证）

---

## 主要参考

- [OpenClaw](https://en.wikipedia.org/wiki/OpenClaw) — Agent OS 架构灵感来源（Gateway + Brain + Memory + Skills + Heartbeat）
- [Matter 协议](https://project-chip.github.io/connectedhomeip-doc/index.html) — 开源物联网互操作标准
- [python-miio](https://github.com/rytilahti/python-miio) — 小米 MIoT 本地控制库
- [Home Assistant](https://www.home-assistant.io/) — 可选设备桥接（通过 REST API）
- [Eclipse Mosquitto](https://mosquitto.org/) — MQTT Broker
- [NetDisco](https://github.com/home-assistant-libs/netdisco) — 设备发现库
