# Anima 重大修改记录

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
