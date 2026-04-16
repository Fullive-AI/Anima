#!/usr/bin/env python3
"""Anima 记忆系统架构图 (L3 三层记忆) — Feishu 风格分层可视化"""

import os

import matplotlib

matplotlib.use('Agg')
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


# ── Chinese font setup ────────────────────────────────────────────────────────
def _find_cjk_font() -> str | None:
    available = {f.name for f in fm.fontManager.ttflist}
    for name in ("Microsoft YaHei", "SimHei", "PingFang SC",
                 "WenQuanYi Micro Hei", "Noto Sans CJK SC", "Arial Unicode MS"):
        if name in available:
            return name
    return None

cjk = _find_cjk_font()
if cjk:
    plt.rcParams['font.family'] = cjk
plt.rcParams['axes.unicode_minus'] = False

# ── Canvas ────────────────────────────────────────────────────────────────────
FW, FH = 20, 14
fig, ax = plt.subplots(figsize=(FW, FH))
ax.set_xlim(0, FW)
ax.set_ylim(0, FH)
ax.axis('off')
fig.patch.set_facecolor('#FFFFFF')

LABEL_W = 1.6    # width reserved for layer label on the left
BOX_L   = 1.9    # left edge of box area
BOX_R   = 19.4   # right edge of box area
BOX_W   = BOX_R - BOX_L  # usable width for boxes

# ── Helpers ───────────────────────────────────────────────────────────────────
def layer_bg(y: float, h: float, fill: str, label: str, lc: str = '#4A5568') -> None:
    """Draw a layer background band with a left-side label."""
    rect = FancyBboxPatch(
        (0.25, y), FW - 0.5, h,
        boxstyle='round,pad=0.08', linewidth=0,
        facecolor=fill, zorder=1,
    )
    ax.add_patch(rect)
    # vertical label text in the left zone
    ax.text(
        0.25 + LABEL_W / 2, y + h / 2, label,
        ha='center', va='center', fontsize=9.5, fontweight='bold',
        color=lc, zorder=3, multialignment='center',
    )
    # thin separator line between label zone and box zone
    ax.plot([BOX_L - 0.15, BOX_L - 0.15], [y + 0.12, y + h - 0.12],
            color=lc, linewidth=0.6, alpha=0.35, zorder=3)


def component_box(
    x: float, y: float, w: float, h: float,
    title: str, sub: str = '',
    bg: str = '#FFFFFF', bc: str = '#CBD5E0',
    tc: str = '#2D3748', sc: str = '#6B7280',
    tfs: float = 8.8, sfs: float = 7.2,
) -> None:
    """Draw a single component box."""
    r = FancyBboxPatch(
        (x, y), w, h,
        boxstyle='round,pad=0.06', linewidth=1.4,
        edgecolor=bc, facecolor=bg, zorder=4,
    )
    ax.add_patch(r)
    dy = 0.16 if sub else 0
    ax.text(x + w / 2, y + h / 2 + dy, title,
            ha='center', va='center', fontsize=tfs,
            color=tc, fontweight='bold', zorder=5)
    if sub:
        ax.text(x + w / 2, y + h / 2 - dy * 1.1, sub,
                ha='center', va='center', fontsize=sfs,
                color=sc, zorder=5)


def layer_arrow(y_from: float, y_to: float, color: str = '#B0BAC9') -> None:
    """Draw a downward/upward arrow between two layers."""
    mid = (BOX_L + BOX_R) / 2
    ax.annotate('', xy=(mid, y_to), xytext=(mid, y_from),
                arrowprops=dict(arrowstyle='->', color=color, lw=1.6),
                zorder=7)


def distribute(n: int, w: float, pad: float = 0.3) -> list[float]:
    """Return left-x positions for n boxes of width w, evenly spread."""
    avail = BOX_W - 2 * pad
    gap = (avail - n * w) / max(n - 1, 1)
    return [BOX_L + pad + i * (w + gap) for i in range(n)]


# ════════════════════════════════════════════════════════════════════════════════
# 图1风格配色方案 (统一黑字 + 柔和pastel层背景)
# ════════════════════════════════════════════════════════════════════════════════

# 层背景色 - 柔和pastel色调 (参考图1)
LAYER_COLORS = {
    'file':    {'bg': '#E8EEF7', 'border': '#B8C5D9'},  # 淡蓝色
    'service': {'bg': '#F0E6FA', 'border': '#D4C4E0'},  # 淡紫色
    'context': {'bg': '#FFF8E1', 'border': '#E8DCC0'},  # 淡黄色
    'combo':   {'bg': '#E8F5E9', 'border': '#C8E6C9'},  # 淡绿色
    'brain':   {'bg': '#E3F2FD', 'border': '#BBDEFB'},  # 淡蓝灰
}

# 统一文字颜色 - 黑色/深灰
TEXT_COLOR = '#2D3748'      # 主文字 - 深灰黑
SUBTEXT_COLOR = '#4A5568'   # 副文字 - 中灰

# ════════════════════════════════════════════════════════════════════════════════
# Layer y-positions and heights  (bottom → top)
# ════════════════════════════════════════════════════════════════════════════════
GAP = 0.28

y0, h0 = 0.30, 2.0    # 文件存储层
y1, h1 = y0+h0+GAP, 2.1    # 记忆服务层
y2, h2 = y1+h1+GAP, 2.5    # 三层上下文 API
y3, h3 = y2+h2+GAP, 1.55   # 组合接口层
y4, h4 = y3+h3+GAP, 1.55   # Brain Engine 调用层

# ── Title ─────────────────────────────────────────────────────────────────────
ax.text(FW / 2, FH - 0.48,
        'Anima  记忆系统架构  ·  L3 三层记忆上下文',
        ha='center', va='center', fontsize=15, fontweight='bold',
        color='#1A202C', zorder=10)

# ── Layer 5 — 文件存储层 ──────────────────────────────────────────────────────
lc = LAYER_COLORS['file']
layer_bg(y0, h0, lc['bg'], '文件\n存储层', TEXT_COLOR)

FILES = [
    ('preferences.md',     '偏好 Markdown\n自然语言文本'),
    ('history.json',       '决策历史\n最多 1000 条'),
    ('learned.json',       '设备学习档案\nper-device-type'),
    ('memory_state.json',  '提取游标\nhistory cursor'),
    ('memories/\n{slug}.json', '按主题长期记忆\n每个 topic 一个文件'),
]
bw0, xs0 = 2.7, distribute(5, 2.7)
for i, (t, s) in enumerate(FILES):
    component_box(xs0[i], y0+0.30, bw0, 1.38,
                  t, s, bg='#FFFFFF', bc=lc['border'], tc=TEXT_COLOR, sc=SUBTEXT_COLOR)

# ── Layer 4 — 记忆服务层 ──────────────────────────────────────────────────────
lc = LAYER_COLORS['service']
layer_bg(y1, h1, lc['bg'], '记忆\n服务层', TEXT_COLOR)

SVCS = [
    ('MemoryStore',                 '读写所有记忆文件\n纯文件 I/O，无外部依赖'),
    ('MemoryExtractionService',     '历史 → 结构化长期记忆\n后台调度，批次 ≤ 50 条'),
    ('PreferenceLearningService',   '历史 + 记忆 → 学习档案\n先调用 MES，再更新 learned.json'),
]
bw1, xs1 = 4.6, distribute(3, 4.6)
for i, (t, s) in enumerate(SVCS):
    component_box(xs1[i], y1+0.32, bw1, 1.44,
                  t, s, bg='#FFFFFF', bc=lc['border'], tc=TEXT_COLOR, sc=SUBTEXT_COLOR)

# ── Layer 3 — 三层上下文 API ──────────────────────────────────────────────────
lc = LAYER_COLORS['context']
layer_bg(y2, h2, lc['bg'], '三层\n上下文\nAPI', TEXT_COLOR)

CTXS = [
    ('L1  常驻层',
     'get_core_identity()\npreferences_summary\n+ last_interaction\n~200 tokens，每次 LLM 调用必带'),
    ('L2  摘要层',
     'get_memory_directory()\nlearned_profile_types\n+ memory_topics 目录索引\nAgent 了解有哪些记忆可用'),
    ('L3  按需层',
     'get_memory_detail()\nlearned_profile 完整档案\n+ memory_detail + history\n仅 Agent 主动调用时才加载'),
]
bw2, xs2 = 4.6, distribute(3, 4.6)
for i, (t, s) in enumerate(CTXS):
    component_box(xs2[i], y2+0.30, bw2, 1.88,
                  t, s, bg='#FFFFFF', bc=lc['border'], tc=TEXT_COLOR, sc=SUBTEXT_COLOR, tfs=9.5, sfs=7.4)

# ── Layer 2 — 组合接口层 ──────────────────────────────────────────────────────
lc = LAYER_COLORS['combo']
layer_bg(y3, h3, lc['bg'], '组合\n接口层', TEXT_COLOR)

COMBOS = [
    ('get_planner_context()',
     'L1 + L2  →  供调度器 / Chat Planner 使用'),
    ('get_skill_context(device_type)',
     'L1 + L3  →  供 Skill 动作决策使用'),
]
bw3, xs3 = 7.5, distribute(2, 7.5)
for i, (t, s) in enumerate(COMBOS):
    component_box(xs3[i], y3+0.25, bw3, 1.05,
                  t, s, bg='#FFFFFF', bc=lc['border'], tc=TEXT_COLOR, sc=SUBTEXT_COLOR, tfs=9.5, sfs=7.8)

# ── Layer 1 — Brain Engine 调用层 ─────────────────────────────────────────────
lc = LAYER_COLORS['brain']
layer_bg(y4, h4, lc['bg'], 'Brain\nEngine\n调用层', TEXT_COLOR)

BRAIN = [
    ('run_cycle()',              '→ get_planner_context'),
    ('_graph_chat_planner()',    '→ get_planner_context'),
    ('_graph_chat_executor()',   '→ get_planner_context'),
    ('execute_device_skill()',   '→ get_skill_context'),
]
bw4, xs4 = 3.5, distribute(4, 3.5)
for i, (t, s) in enumerate(BRAIN):
    component_box(xs4[i], y4+0.25, bw4, 1.05,
                  t, s, bg='#FFFFFF', bc=lc['border'], tc=TEXT_COLOR, sc=SUBTEXT_COLOR)

# ── Between-layer connection arrows ──────────────────────────────────────────
for ylo, hlo, yhi in [
    (y0, h0, y1), (y1, h1, y2), (y2, h2, y3), (y3, h3, y4),
]:
    layer_arrow(ylo + hlo, yhi)

# ── Save ──────────────────────────────────────────────────────────────────────
os.makedirs(os.path.join(os.path.dirname(__file__)), exist_ok=True)
out = os.path.join(os.path.dirname(__file__), 'memory_architecture.png')
plt.savefig(out, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
print(f"[OK] Saved to: {out}")
plt.close()
