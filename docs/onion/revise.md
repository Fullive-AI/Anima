# Anima 重大修改记录

> 最后更新：2026-04-15

---

## 8. README 全面重写 + Logo 设计（2026-04-15）

### 改动文件
- `README.md` — 英文版全面重写
- `README.zh-CN.md` — 中文版全面重写
- `docs/images/logo.svg` — 新建 SVG Logo

### 改进内容

**Logo（`docs/images/logo.svg`）**
- 紫青渐变圆形背景，五个电路节点象征硬件设备
- 中心灵魂光环 + 大写字母 A
- 节点带 CSS 脉冲动画效果，可直接在 GitHub Markdown 渲染

**README 结构重构（参考 G-Master 风格）**
- 顶部 Hero 区：Logo + 标题 + Slogan + 语言切换 + Badges 居中展示
- 新增 FAQ 区（Why Anima?）：彩色 `for-the-badge` 图标组 + 可折叠 `<details>` 块，回答用户核心疑问
- 快速开始：精简步骤，去掉冗余介绍
- 架构章节：保留 ASCII 图，新增 Mermaid 流程图可视化数据流
- REST API：折叠进 `<details>` 避免页面过长
- 技能系统：独立成一级章节，含创建自定义 Skill 的目录结构说明
- 路线图：v0.1 标记 ✅ 当前状态
- 底部加入 `Made with ❤️` 结尾

---

> 日期：2026-04-12

---

## 1. 虚拟设备系统（Virtual Device Adapter）

新增 `adapters/virtual/` 适配器，支持在没有真实硬件的情况下创建、持久化、删除虚拟设备。

- `VirtualAdapter` 注册到主进程，随 Anima 启动自动恢复已持久化的虚拟设备
- API：`POST /api/admin/virtual-devices`、`DELETE /api/admin/virtual-devices/{id}`
- 支持手动推送传感器数据：`POST /api/devices/{id}/sensors`，触发 `SENSOR_UPDATED` 事件驱动 Brain 自动化循环

---

## 2. 多设备自动化扩展（Brain Engine）

`core/brain/engine.py` 的启动自动化从仅支持空气净化器扩展为三类设备并行：

| 设备 | 触发条件 |
|------|---------|
| 空气净化器 | AQI > 5 开启 / AQI ≤ 5 关闭 |
| 空调 | 温度 ≥ 28°C 开启制冷 / ≤ 16°C 关闭 |
| 加湿器 | 湿度 < 35% 开启 / ≥ 70% 关闭 |

自动化消息改为中文，贴近用户语境。

---

## 3. 房间管理系统（Rooms API）

后端新增完整 CRUD：

- `GET/POST /api/rooms` — 列出 / 创建房间
- `PUT /api/rooms/{id}` — 重命名房间
- `DELETE /api/rooms/{id}` — 删除房间（自动解绑设备）
- `PUT /api/devices/{id}/room` — 设备分配到房间，持久化到 settings store

前端 `DeviceList` 支持：
- 按房间折叠/展开分组
- 拖拽设备到房间
- 右键菜单：重命名设备、删除设备、重命名/删除房间
- 新增房间内联输入

---

## 4. 设备管理 API 补全

- `PATCH /api/devices/{id}/rename` — 重命名设备（虚拟设备同步持久化）
- `DELETE /api/devices/{id}` — 删除设备（虚拟设备同步清理 adapter + store）

---

## 5. SSE 流式推送

- `GET /api/brain/events` — Brain 主动通知前端的 SSE 流（含 ping keepalive）
- `POST /api/chat` 新增 `stream: true` 参数，支持流式对话响应（`StreamingResponse`）

---

## 6. 前端 UI 全面升级

- `DeviceCard`：传感器徽章视觉重设计，on/off 值显示为"开/关"，圆角、阴影、hover 动效
- `DeviceList`：房间分组 + 拖拽 + 右键菜单完整交互
- `useApi.ts`：补全 Room 类型及所有房间/虚拟设备相关 API 方法
- `index.css`：样式补充

---

## 7. 内存与偏好本地化

`core/memory/store.py` 默认偏好配置全面中文化：
- 舒适度默认值（温度 24°C、湿度 50%）
- 作息时间（起床 07:00、睡觉 22:30）
- Cold-start 提示语改为中文

## 记忆系统超级改进

层级	说明	注入方式
L1 常驻层	核心偏好摘要（温度/湿度/作息等一句话版）+ 在家状态	每次都在 system prompt 里
L2 摘要层	学习档案名录 + 记忆清单（仅标题/类别）	放在初始上下文，agent 按需 get_memory 取详情
L3 按需层	完整学习档案、历史记录、记忆详情	只在 agent 调用工具时才加载（如 execute_skill 时加载对应设备的学习档案）

## TODO LIST
1. 感知层 亮点
后续改进：
通过对话修改阈值和偏好
而不是硬编码Prompt
2. README 架构图+看看记忆机制需不需要画出来
3. skill creater