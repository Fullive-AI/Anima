<div align="center">

<!-- LOGO_PLACEHOLDER: 替换为 Anima Logo -->
<!-- <img src="./assets/logo.png" alt="Anima Logo" width="200"> -->

# Anima

### 让每一个硬件都拥有智慧

开源 **Agentic AI 硬件操作系统** — 自动发现设备、赋予每个设备 AI 大脑，让它们自主感知、决策、进化。

[English](./README.md) | [中文](./README.zh-CN.md)

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](./LICENSE)
[![CI](https://github.com/fulai-tech/Anima/actions/workflows/ci.yml/badge.svg)](https://github.com/fulai-tech/Anima/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](./docker-compose.yml)

<!-- DEMO_GIF_PLACEHOLDER: 替换为演示 GIF 或截图 -->
<!-- <img src="./assets/demo.gif" alt="Anima Dashboard Demo" width="800"> -->

**[快速开始](#-快速开始)** · **[文档](#-开发)** · **[贡献指南](./CONTRIBUTING.md)** · **[路线图](#-路线图)**

</div>

---

## 为什么选择 Anima？

大多数智能家居系统只是"遥控器" — 切换开关、执行固定时间表。Anima 不一样。

**Anima**（拉丁语"灵魂"）为你的硬件注入真正的智能。它不问 _"你要设什么规则？"_，而是问 **_"你有什么设备？让我来搞定。"_**

### 三大核心能力

<table>
<tr>
<td width="33%" align="center">
<h3>🧠 技能驱动的 AI 大脑</h3>
<p>每种设备类型都获得<strong>专业领域知识</strong> — 不只是开关控制。加湿器知道舒适湿度范围、季节调整、空调联动；灯光理解昼夜节律。AI 大脑加载这些技能并自主决策。</p>
</td>
<td width="33%" align="center">
<h3>🔌 零配置发现</h3>
<p><strong>插入设备，Anima 自动找到它。</strong>通过 mDNS 自动发现设备，识别类型，加载匹配技能，开始管理 — 无需 YAML 配置，无需手动设置。目前支持小米/MIoT，Matter 和 HomeAssistant 即将到来。</p>
</td>
<td width="33%" align="center">
<h3>🧬 学习与进化</h3>
<p>Anima <strong>记住你的偏好</strong>并持续进化。它从你的决策中提取模式，按设备类型构建偏好画像，持续优化行为。用得越多，越智能。</p>
</td>
</tr>
</table>

---

## 架构

```
┌────────────────────────────────────────────────────────────────────┐
│                     Anima Core（单进程架构）                        │
│                                                                    │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    │
│  │  设备发现 │───▶│  事件总线 │◀───│  调度器   │    │  记忆系统 │    │
│  └──────────┘    └────┬─────┘    └──────────┘    └────┬─────┘    │
│                       │                               │          │
│         ┌─────────────┴───────────────────────────────┘          │
│         │                                                        │
│         │     ┌──────────────────────────────┐                   │
│         │     │         LLM 大脑              │                   │
│         │     │  ┌────────┐  ┌───────────┐   │                   │
│         │     │  │ 规划器  │  │  执行器    │   │                   │
│         │     │  │(技能)   │  │(LangGraph)│   │                   │
│         │     │  └────────┘  └───────────┘   │                   │
│         │     └──────────────────────────────┘                   │
│         │                                                        │
│         │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐     │
│         │  │ REST API │  │   Chat   │  │    Dashboard     │     │
│         │  │ (8080)   │  │  (WS)    │  │   (Vite/3000)   │     │
│         │  └──────────┘  └──────────┘  └──────────────────┘     │
│         └────────────────────────────────────────────────────────│
└──────────────────────────┬─────────────────────────────────────────┘
                           │ MQTT
                    ┌──────┴──────┐
                    │ MQTT Broker │
                    └──┬─────┬───┘
                       │     │
              ┌────────┘     └────────┐
        ┌─────┴─────┐         ┌──────┴──────┐
        │   MIoT    │         │   Virtual   │
        │  适配器    │         │   适配器     │
        └───────────┘         └─────────────┘
        小米设备                演示/测试
```

---

## 快速开始

### 环境要求

- [Node.js](https://nodejs.org/) >= 18 + [pnpm](https://pnpm.io/) >= 8
- [Python](https://www.python.org/) >= 3.11（uv 由 pnpm 自动安装）

### 安装与运行

```bash
# 克隆项目
git clone https://github.com/fulai-tech/Anima.git
cd Anima

# 安装所有依赖（前端 + 后端）
pnpm install

# 配置 LLM API 密钥
cp .env.example .env
# 编辑 .env，设置 ANIMA_LLM_API_KEY

# 启动（MQTT Broker + 后端 + Dashboard 一起启动）
pnpm dev
```

打开 **http://localhost:3000** — Anima Dashboard 已就绪。

> **没有设备？** 没问题 — 使用 Dashboard 添加虚拟设备即可体验完整演示。在聊天栏中让 Anima 帮你创建设备。

### Docker 部署

```bash
cp .env.example .env  # 填入 API 密钥

docker compose up -d
```

---

## 配置

```env
# 必填：任何 OpenAI 兼容的 API 密钥
ANIMA_LLM_API_KEY=sk-xxx

# 可选：模型名称（默认：gpt-4o）
ANIMA_LLM_MODEL=gpt-4o

# 可选：自定义 API 端点（DeepSeek / 豆包 / Ollama 等）
ANIMA_LLM_BASE_URL=https://api.deepseek.com/v1
```

**支持的 LLM 提供商**（任何 OpenAI 兼容 API）：

| 提供商 | 模型 | Base URL |
|--------|------|----------|
| OpenAI | `gpt-4o` | _（留空）_ |
| DeepSeek | `deepseek-chat` | `https://api.deepseek.com/v1` |
| 豆包 | `doubao-seed-2-0-lite-260215` | `https://ark.cn-beijing.volces.com/api/v3` |
| Ollama（本地） | `llama3` | `http://localhost:11434/v1` |

---

## 技能系统

每个技能教会 Anima **如何让一种设备类型变得自主智能** — 不只是开关控制。

### 内置技能

| 技能 | 智能 |
|------|------|
| **加湿器** | 舒适范围 (40-60%)、季节调整、空调联动、水位预警 |
| **空调** | 节能优化、昼夜温度曲线、湿度协调 |
| **灯光** | 昼夜节律照明 (2200K–5000K)、分时亮度、平滑过渡 |
| **空气净化器** | 人在感知净化、睡眠静音、AQI 启发式 |
| **音箱** | 播放导向行为、安静时段保护、安全默认 |
| **协调器** | 跨设备编排 — 防止冲突、创造协同 |

### 编写自定义技能

```bash
cp -r skills/custom/_template skills/custom/my-skill
# 编辑 skills/custom/my-skill/SKILL.md
# 重启 Anima — 自动发现新技能
```

---

## 开发

| 命令 | 说明 |
|------|------|
| `pnpm install` | 安装所有依赖 |
| `pnpm dev` | 启动 Broker + 后端 + Dashboard |
| `pnpm dev:frontend` | 仅 Dashboard (端口 3000) |
| `pnpm dev:backend` | 仅后端 (端口 8080) |
| `pnpm build` | 构建前端 |
| `uv run pytest tests/ -v` | 运行测试 |

---

## 路线图

| 版本 | 里程碑 | 状态 |
|------|--------|------|
| **v0.1** | **"它活了"** — 核心框架、MIoT 适配器、Dashboard、LLM 大脑、记忆学习、内置技能 | **当前** |
| v0.2 | **"更聪明"** — Matter 适配器、实时 WebSocket、房间管理 | 计划中 |
| v0.3 | **"社区来了"** — 技能商店、适配器插件、Telegram Bot、HA 桥接 | 计划中 |
| v0.4 | **"更强大"** — 多用户、树莓派镜像、安全加固 | 计划中 |

---

## 贡献

欢迎贡献！最简单的参与方式：

- **编写技能** — 教 Anima 认识新设备类型
- **编写适配器** — 添加新设备协议支持（3 个方法：`discover()`, `subscribe()`, `execute()`）
- 通过 [Issues](https://github.com/fulai-tech/Anima/issues) **报告 Bug** 或 **建议功能**

查看 [CONTRIBUTING.md](./CONTRIBUTING.md) 了解完整指南。

---

## 关于

Anima 由 [**Fullive.AI**](https://fullive.ai/)（福来数创）构建，一家空间 Agentic AI 公司，由高瓴创投、慕华科创、智元机器人、北大苏南研究院等共同投资。

> _我们坚信，让环境主动进化以适应人类，是人类应得的科技特权。_

Fullive.AI 以空间 Agentic AI 架构为核心，赋予物理空间自主感知、决策、执行、进化的能力，实现空间与人类的无感交互范式变革。

---

## 许可证

[Apache License 2.0](./LICENSE) — Anima 完全免费且开源。

---

<!-- STAR_HISTORY_PLACEHOLDER -->
<!-- [![Star History Chart](https://api.star-history.com/svg?repos=fulai-tech/Anima&type=Date)](https://star-history.com/#fulai-tech/Anima&Date) -->
