"""第三方插件页面（iframe 页面）的主题适配。

AstrBot 的插件页面在 Dashboard 里是 `sandbox` iframe，父文档的样式进不去，
调色盘的通用规则只能把 iframe 外壳染透明，页面内部仍是它自己的实心底色。
这里针对已适配的插件页面，把一段样式写进页面 HTML，让页面底色跟着壁纸透出来。

样式写进页面文件时会带标记，可重复执行、可撤销；插件自身更新覆盖掉页面后，
调色盘下次启动或保存配置时会重新写入。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .constants import PLUGIN_NAME

START_MARKER = f"<!-- {PLUGIN_NAME}:plugin-page:start -->"
END_MARKER = f"<!-- {PLUGIN_NAME}:plugin-page:end -->"
STYLE_ID = "astrbot-palette-plugin-page"
SCRIPT_ID = "astrbot-palette-plugin-page-bridge"

_BLOCK_RE = re.compile(
    r"^[ \t]*"
    + re.escape(START_MARKER)
    + r".*?^[ \t]*"
    + re.escape(END_MARKER)
    + r"[ \t]*\r?\n",
    flags=re.DOTALL | re.MULTILINE,
)


def _newline_for(text: str) -> str:
    return "\r\n" if text.count("\r\n") > text.count("\n") / 2 else "\n"


# 调色盘主题色的兜底值，配置缺失或不是合法 #rrggbb 时使用。
DEFAULT_PRIMARY = "#7daabf"
DEFAULT_SECONDARY = "#707db8"
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _safe_hex(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    return text.lower() if _HEX_RE.match(text) else fallback


def _livingmemory_css(primary: str, secondary: str) -> str:
    """LivingMemory 页面：底色交给壁纸，卡片改用半透明玻璃色。

    页面本身只由一套 CSS 变量驱动（`--bg-app` / `--bg-card` / `--accent` / ...），
    所以覆盖变量就能让所有页面（图谱、记忆、设置、弹窗）一起变透明、换主题色、
    换圆角，无需逐个选择器点名。毛玻璃模糊来自调色盘在 iframe 外壳上加的
    backdrop-filter，iframe 内部拿不到父文档的背景，只能靠半透明色层。

    `primary` / `secondary` 是写入时的主题色快照；父页面拿到实时值后会通过
    postMessage 覆盖（见 `_THEME_SYNC_SCRIPT`）。
    """

    template = """
/* AstrBot 调色盘 · LivingMemory 面板适配。整段由调色盘写入，可重复覆盖。 */
html,
body {
  background: transparent !important;
}

/* 页面原来的 48px 网格纹理叠在壁纸上会显脏，这里换成一层压暗，
   保证小号文字不被壁纸的花纹吃掉。 */
body::before {
  position: fixed !important;
  inset: 0 !important;
  background-image: none !important;
  background-color: rgba(8, 10, 7, 0.34) !important;
  opacity: 1 !important;
}

#app,
.main-content,
.page-header {
  background: transparent !important;
}

/* 主题色：这两个是写入时的快照，父页面会推实时值把它们覆盖掉。 */
html {
  --palette-accent: __PRIMARY__;
  --palette-accent-2: __SECONDARY__;
  --palette-accent-soft: color-mix(in srgb, var(--palette-accent) 24%, transparent);
  --palette-accent-2-soft: color-mix(in srgb, var(--palette-accent-2) 24%, transparent);
}

/* 圆角：对齐调色盘的档位（面板 18、卡片 14、按钮/输入 10、小标签 8）。 */
html {
  --radius-sm: 8px !important;
  --radius-md: 10px !important;
  --radius-lg: 16px !important;
  --radius-xl: 20px !important;
  --theme-radius: 16px !important;
}

/* editorial 风格把圆角写死成 0~4px，这里按板块逐类拉齐。 */
html :is(.table-container, .graph-canvas-container, .system-panel, .settings-group,
    .settings-quick, .recall-form-section, .prompt-editor, .memory-transfer) {
  border-radius: 18px !important;
}

html :is(.stat-card, .recall-result-item, .prompt-item, .memory-selection,
    #transfer-feedback, .appearance-card, .session-item, .backup-item,
    .edit-history-item, .peek-related-item, .memory-detail-content) {
  border-radius: 14px !important;
}

html :is(.btn, .input, .nav-item, .lang-options, .graph-toolbar, .toast,
    .memory-detail-edit-area, .peek-related-item) {
  border-radius: 10px !important;
}

html :is(.btn-sm, .graph-canvas-state, .lang-option, .memory-detail-select,
    .memory-detail-reason, .origin-tag, .settings-default-value) {
  border-radius: 8px !important;
}

html :is(.appearance-dialog, .discard-dialog) {
  border-radius: 20px !important;
}

/* 本来就是胶囊/圆点的保持圆形，别被上面的档位压成方块。 */
html :is(.importance-bar-track, .importance-bar-fill, .legend-chip, .status-pill,
    .badge, .badge-custom, .badge-json-warn, .peek-node-badge, .settings-badge,
    .recall-route-chip, .memory-detail-importance, .result-score-badge,
    .recall-result-score, .preview-pill) {
  border-radius: 999px !important;
}

html .status-pill::before,
html .legend-chip .dot,
html .peek-fact-item::before {
  border-radius: 50% !important;
}

html[data-theme="dark"] body {
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.5);
}

/* 玻璃面板内的文字不需要增强阴影：面板本身有半透明底色，而这些面板里
   常有几百个文本节点，带阴影时滚动重绘没法复用绘制结果。面板外的裸标题
   仍然继承 body 的阴影。 */
html :is(.table-container, .graph-canvas-container, .system-panel, .settings-group,
    .settings-quick, .recall-form-section, .prompt-editor, .memory-transfer,
    .stat-card, .recall-result-item, .prompt-item, .memory-selection,
    .appearance-card, .session-item, .backup-item, .edit-history-item,
    .peek-related-item, .memory-detail-content, .nav-item, .btn,
    .graph-toolbar, .lang-options) {
  text-shadow: none !important;
}

html[data-theme="dark"] {
  --bg-app: transparent !important;
  --bg-sidebar: rgba(8, 10, 7, 0.46) !important;
  --bg-card: rgba(21, 24, 18, 0.3) !important;
  --bg-hover: rgba(30, 35, 26, 0.5) !important;
  --bg-active: rgba(41, 49, 35, 0.62) !important;
  --bg-input: rgba(21, 24, 18, 0.55) !important;
  --bg-overlay: rgba(13, 15, 12, 0.8) !important;
  --bg-tint: rgba(24, 28, 22, 0.3) !important;
  --bg-toolbar: rgba(17, 20, 14, 0.42) !important;
  --bg-table-head: rgba(24, 28, 22, 0.42) !important;
  --graph-surface: rgba(17, 20, 14, 0.26) !important;
  /* 主题色：主色当强调色，辅色当高亮色；深色下按钮用深字。 */
  --accent: var(--palette-accent) !important;
  --accent-color: var(--palette-accent) !important;
  --accent-hover: color-mix(in srgb, var(--palette-accent) 82%, #ffffff) !important;
  --accent-light: var(--palette-accent-soft) !important;
  --signal: var(--palette-accent-2) !important;
  --signal-soft: var(--palette-accent-2-soft) !important;
  --border-focus: var(--palette-accent) !important;
}

/* 3D 图谱模式给侧栏写死了实心色，这里跟着一起透。 */
html[data-graph-view="3d"] .sidebar {
  background: rgba(8, 11, 18, 0.46) !important;
}

html[data-theme="light"] body::before {
  background-color: rgba(248, 251, 248, 0.58) !important;
}

html[data-theme="light"] body {
  text-shadow: 0 1px 3px rgba(255, 255, 255, 0.6);
}

html[data-theme="light"] {
  --bg-app: transparent !important;
  --bg-sidebar: rgba(240, 247, 242, 0.6) !important;
  --bg-card: rgba(255, 255, 253, 0.5) !important;
  --bg-hover: rgba(228, 242, 236, 0.66) !important;
  --bg-active: rgba(216, 236, 232, 0.78) !important;
  --bg-input: rgba(255, 255, 253, 0.72) !important;
  --bg-overlay: rgba(251, 253, 249, 0.88) !important;
  --bg-tint: rgba(240, 247, 242, 0.5) !important;
  --bg-toolbar: rgba(240, 247, 242, 0.58) !important;
  --bg-table-head: rgba(234, 243, 238, 0.62) !important;
  --graph-surface: rgba(255, 255, 253, 0.36) !important;
  /* 浅色下主色要压深才够对比：按钮上是白字，正文里的强调色也才看得清。 */
  --accent: color-mix(in srgb, var(--palette-accent) 62%, #0f1b18) !important;
  --accent-color: color-mix(in srgb, var(--palette-accent) 62%, #0f1b18) !important;
  --accent-hover: color-mix(in srgb, var(--palette-accent) 46%, #0f1b18) !important;
  --accent-light: var(--palette-accent-soft) !important;
  --signal: color-mix(in srgb, var(--palette-accent-2) 62%, #0f1b18) !important;
  --signal-soft: var(--palette-accent-2-soft) !important;
  --border-focus: color-mix(in srgb, var(--palette-accent) 62%, #0f1b18) !important;
}
"""
    return (
        template.replace("__PRIMARY__", primary)
        .replace("__SECONDARY__", secondary)
        .strip()
    )


def _memewiki_css(primary: str, secondary: str) -> str:
    """梗百科「自定义黑话」页面：底色交给壁纸，面板/输入框改成半透明玻璃。

    这个页面是一段自带样式的静态页，没有圆角变量，暗色也只靠
    `prefers-color-scheme`（跟随系统而不是面板主题），所以既要覆盖它的
    `--bg/--panel/--text/--border/--accent` 变量，也要给 `.panel`、输入框、
    按钮单独定圆角。AstrBot 打开插件页时会在 `<html>` 写上 `data-theme`，
    这里以它为准，深浅两套都给足，不依赖系统偏好。
    """

    template = """
/* AstrBot 调色盘 · 梗百科「自定义黑话」适配。整段由调色盘写入，可重复覆盖。 */
html,
body {
  background: transparent !important;
}

/* 插件页是独立文档：root 上写了 color-scheme: dark 时，Chrome 会把 iframe
   画布刷成不透明黑，父页壁纸透不过来；改成 normal 才能真透明（表单控件外观
   仍由这个页面自己的样式决定）。 */
html {
  color-scheme: normal !important;
}

/* 不再铺任何压暗：内容块之外的空白完全透明，直接露出壁纸（和面板页一致），
   可读性交给半透明面板与文字阴影。 */
body > .wrap {
  position: relative;
}

html {
  --palette-accent: __PRIMARY__;
  --palette-accent-2: __SECONDARY__;
  --palette-accent-soft: color-mix(in srgb, var(--palette-accent) 24%, transparent);
}

/* 圆角对齐调色盘档位：面板 18、输入框/按钮 10、小按钮 8。 */
html .panel {
  border-radius: 18px !important;
}

html input[type="text"],
html textarea,
html button {
  border-radius: 10px !important;
}

html button.del {
  border-radius: 8px !important;
}

html input[type="text"],
html textarea {
  background: var(--field) !important;
}

html input[type="text"]:focus,
html textarea:focus {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--palette-accent) 22%, transparent) !important;
}

/* 标题直接压在壁纸上，阴影给足一点，浅色壁纸下也压得住。 */
html[data-theme="dark"] body {
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.7), 0 0 12px rgba(0, 0, 0, 0.35);
}

html[data-theme="dark"] {
  --bg: transparent !important;
  --panel: rgba(21, 24, 18, 0.34) !important;
  --field: rgba(9, 12, 10, 0.42) !important;
  --text: #eef1f5 !important;
  --muted: #aeb8c6 !important;
  --border: rgba(255, 255, 255, 0.16) !important;
  --accent: var(--palette-accent) !important;
  --ok: #4ade80 !important;
  --danger: #f87171 !important;
}

/* 深色下强调色偏亮，主按钮改用深字才看得清。 */
html[data-theme="dark"] button.primary {
  color: #0b1013 !important;
}

/* 浅色下白描边会把小字糊掉，只用一层很淡的提亮，靠深色字自己撑对比。 */
html[data-theme="light"] body {
  text-shadow: 0 1px 2px rgba(255, 255, 255, 0.45);
}

html[data-theme="light"] {
  --bg: transparent !important;
  --panel: rgba(255, 255, 253, 0.52) !important;
  --field: rgba(255, 255, 255, 0.72) !important;
  --text: #1f2937 !important;
  --muted: #4b5566 !important;
  --border: rgba(15, 27, 24, 0.14) !important;
  /* 浅色下主色压深，白字按钮和正文强调色才有对比。 */
  --accent: color-mix(in srgb, var(--palette-accent) 62%, #0f1b18) !important;
  --ok: #047857 !important;
  --danger: #dc2626 !important;
}

/* 滚动条跟随调色盘的细圆角样式（iframe 里拿不到父页面的全局规则）。 */
html::-webkit-scrollbar,
html *::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

html::-webkit-scrollbar-track,
html *::-webkit-scrollbar-track {
  background: transparent;
}

html::-webkit-scrollbar-thumb,
html *::-webkit-scrollbar-thumb {
  background: color-mix(in srgb, var(--palette-accent) 45%, transparent);
  border-radius: 8px;
}

html::-webkit-scrollbar-thumb:hover,
html *::-webkit-scrollbar-thumb:hover {
  background: color-mix(in srgb, var(--palette-accent) 70%, transparent);
}

@supports not selector(::-webkit-scrollbar) {
  html {
    scrollbar-width: thin;
    scrollbar-color: color-mix(in srgb, var(--palette-accent) 45%, transparent) transparent;
  }
}
"""
    return (
        template.replace("__PRIMARY__", primary)
        .replace("__SECONDARY__", secondary)
        .strip()
    )


def _self_learning_css(primary: str, secondary: str) -> str:
    """Self Learning（自主学习）面板：底色交给壁纸，面板改半透明玻璃。

    这一页自带一套 Ark / endfield 设计（方角、信号黄、硬偏移阴影），
    但所有表面颜色都走 `--surface*` / `--border*` 变量，所以覆盖变量就能
    整体玻璃化；信号黄换成调色盘主色，方角按调色盘档位收圆，硬阴影换柔和。
    页面自己会用桥接层把 `data-theme` 设成 dark/light，明暗两套都写死更稳。
    """

    template = """
/* AstrBot 调色盘 · Self Learning 面板适配。整段由调色盘写入，可重复覆盖。 */
html,
body {
  background: transparent !important;
}

/* 这一页内容铺满整个 iframe，整页铺一层压暗保证正文小字可读。 */
body::before {
  content: "";
  position: fixed;
  inset: 0;
  z-index: -1;
  pointer-events: none;
  background-color: rgba(8, 10, 7, 0.34);
}

html {
  --palette-accent: __PRIMARY__;
  --palette-accent-2: __SECONDARY__;
  --palette-accent-soft: color-mix(in srgb, var(--palette-accent) 22%, transparent);
}

/* 圆角：面板对齐调色盘档位，方角仪器改成圆角卡片。 */
html :is(.topbar, .hero-copy, .panel, .stat-card, .module-card, .spring-stage,
    .modal-panel, .settings-group, .sidebar-footer, .code-preview,
    .empty-state, .toast, .review-item, .content-item, .table-row,
    .config-field, .pattern-column) {
  border-radius: 14px !important;
}

html :is(.icon-button, .ghost-button, .solid-button, .candidate-row,
    .sender-row, .settings-warning, .segment-control, input, select, textarea) {
  border-radius: 10px !important;
}

html :is(.status-pill, .mini-badge) {
  border-radius: 8px !important;
}

/* 侧栏导航保持「带 1px 分隔线的列表」：这一页有 14 个入口，收圆角会把
   分隔线两端翘成弧线，加间隙又会多占一屏、把最后一项顶出可视区。 */
/* 分段控制是连排按钮，圆角靠外层裁切，否则首尾会露方角。 */
html .segment-control {
  overflow: hidden !important;
}

html .bar-track,
html .bar-fill {
  border-radius: 999px !important;
}

/* ── 深色 ── */
html[data-theme="dark"] body {
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.45);
}

/* 玻璃面板内的文字不带阴影：面板本身有底色，阴影只会让滚动重绘变慢；
   面板之外的裸标题仍继承 body 的阴影。 */
html :is(.topbar, .hero-copy, .panel, .stat-card, .module-card, .spring-stage,
    .modal-panel, .settings-group, .sidebar-footer, .code-preview, .empty-state,
    .toast, .review-item, .content-item, .table-row, .config-field,
    .pattern-column, .icon-button, .ghost-button, .solid-button, .candidate-row,
    .sender-row, .segment-control) {
  text-shadow: none !important;
}

html[data-theme="dark"] {
  --bg: transparent !important;
  --surface: rgba(18, 18, 18, 0.52) !important;
  --surface-solid: rgba(20, 20, 20, 0.42) !important;
  --surface-alt: rgba(32, 32, 30, 0.4) !important;
  --surface-hover: rgba(48, 48, 44, 0.56) !important;
  --border: rgba(242, 242, 240, 0.16) !important;
  --border-strong: rgba(242, 242, 240, 0.32) !important;
  /* 信号黄 → 调色盘主色；ink 文字仍是近黑，放在浅色强调上正好。 */
  --signal: var(--palette-accent) !important;
  --ark-signal: var(--palette-accent) !important;
  --signal-soft: var(--palette-accent-soft) !important;
  /* 原来的硬偏移影子（0.4rem 0.4rem 0）压在壁纸上很脏，换成柔和投影。 */
  --shadow: 0 1px 2px rgba(0, 0, 0, 0.35) !important;
  --shadow-lg: 0 16px 38px rgba(0, 0, 0, 0.34) !important;
  /* 图表主序列原来是信号黄，跟着主题色走；其余数据色保留，多序列仍可分。 */
  --chart-1: var(--palette-accent) !important;
  --chart-5: var(--palette-accent-2) !important;
}

/* 顶栏是「反向坞」：深色主题下是白底深字，浅色主题下是黑底浅字。 */
html[data-theme="dark"] .topbar {
  background: rgba(242, 242, 240, 0.72) !important;
}

/* ── 浅色 ── */
html[data-theme="light"] body {
  text-shadow: 0 1px 2px rgba(255, 255, 255, 0.4);
}

html[data-theme="light"] body::before {
  background-color: rgba(248, 251, 248, 0.52) !important;
}

html[data-theme="light"] {
  --bg: transparent !important;
  --surface: rgba(247, 247, 244, 0.6) !important;
  --surface-solid: rgba(255, 255, 255, 0.52) !important;
  --surface-alt: rgba(239, 239, 236, 0.5) !important;
  --surface-hover: rgba(227, 227, 223, 0.66) !important;
  --border: rgba(25, 25, 25, 0.16) !important;
  --border-strong: rgba(25, 25, 25, 0.34) !important;
  --signal: var(--palette-accent) !important;
  --ark-signal: var(--palette-accent) !important;
  --signal-soft: var(--palette-accent-soft) !important;
  --shadow: 0 1px 2px rgba(25, 25, 25, 0.12) !important;
  --shadow-lg: 0 16px 34px rgba(25, 25, 25, 0.16) !important;
  --chart-1: var(--palette-accent) !important;
  --chart-5: var(--palette-accent-2) !important;
}

html[data-theme="light"] .topbar {
  background: rgba(20, 20, 20, 0.72) !important;
}
"""
    return (
        template.replace("__PRIMARY__", primary)
        .replace("__SECONDARY__", secondary)
        .strip()
    )


def _meme_manager_css(primary: str, secondary: str) -> str:
    """表情包管理器（meme_manager）：底色交给壁纸，面板改半透明玻璃。

    这一页的 `shared/ui.css` 已经是一套完整 token（surface / surface-glass /
    primary / border 全走变量，圆角档位也是 8/12/16/20/999，和调色盘一致），
    所以只覆盖颜色变量：表面换半透明、品牌绿换成调色盘主色，圆角不用动。
    它的四个子页面（管理 / 资源广场 / 语义化 / 设置）共用这份 ui.css，
    所以同一段样式要分别写进四个 HTML。
    """

    template = """
/* AstrBot 调色盘 · 表情包管理器适配。整段由调色盘写入，可重复覆盖。 */
html,
body {
  background-color: transparent !important;
}

/* 插件页是独立文档：root 上写了 color-scheme: dark 时，Chrome 会把 iframe
   画布刷成不透明黑，父页壁纸透不过来；改成 normal 才能真透明（表单控件外观
   仍由这个页面自己的样式决定）。 */
html {
  color-scheme: normal !important;
}

/* 原来 body 上撑着两团绿色/暖色氛围光斑，去掉；页面本身也不铺压暗，
   卡片之外的空白完全透明、直接露出壁纸，压暗只由半透明面板自己承担。 */
body {
  background-image: none !important;
}

html {
  --palette-accent: __PRIMARY__;
  --palette-accent-2: __SECONDARY__;
}

/* ── 深色 ── */
/* 标题与分区说明是裸文本，直接压在壁纸上，阴影给足一点。 */
html[data-theme="dark"] body {
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.7), 0 0 12px rgba(0, 0, 0, 0.35);
}

html[data-theme="dark"] {
  --surface: rgba(21, 23, 25, 0.5) !important;
  --surface-elevated: rgba(29, 32, 34, 0.44) !important;
  --surface-inset: rgba(25, 28, 30, 0.4) !important;
  --surface-hover: rgba(39, 44, 46, 0.56) !important;
  --surface-active: rgba(48, 55, 53, 0.64) !important;
  --surface-muted: rgba(36, 41, 43, 0.38) !important;
  --surface-glass: rgba(29, 32, 34, 0.5) !important;
  --surface-glass-strong: rgba(29, 32, 34, 0.66) !important;
  --border: rgba(231, 235, 232, 0.16) !important;
  --border-strong: rgba(231, 235, 232, 0.3) !important;
  --border-muted: rgba(231, 235, 232, 0.1) !important;

  /* 品牌绿 → 调色盘主色；深色主题本来就是「浅色强调 + 深字」，正好对上。 */
  --primary: var(--palette-accent) !important;
  --primary-hover: color-mix(in srgb, var(--palette-accent) 82%, #ffffff) !important;
  --primary-soft: color-mix(in srgb, var(--palette-accent) 18%, transparent) !important;
  --primary-soft-hover: color-mix(in srgb, var(--palette-accent) 26%, transparent) !important;
  --primary-soft-strong: color-mix(in srgb, var(--palette-accent) 32%, transparent) !important;
  --primary-border: color-mix(in srgb, var(--palette-accent) 40%, transparent) !important;
  --primary-border-strong: color-mix(in srgb, var(--palette-accent) 62%, transparent) !important;
  --on-primary: #0b1013 !important;
  --link: var(--palette-accent) !important;
  --accent: var(--palette-accent) !important;
  --focus-soft: color-mix(in srgb, var(--palette-accent) 24%, transparent) !important;
  --scrollbar: color-mix(in srgb, var(--palette-accent) 45%, transparent) !important;
}

/* ── 浅色 ── */
html[data-theme="light"] body {
  text-shadow: 0 1px 2px rgba(255, 255, 255, 0.45);
}

html[data-theme="light"] {
  --surface: rgba(247, 248, 250, 0.55) !important;
  --surface-elevated: rgba(255, 255, 255, 0.5) !important;
  --surface-inset: rgba(245, 246, 247, 0.45) !important;
  --surface-hover: rgba(240, 242, 243, 0.62) !important;
  --surface-active: rgba(232, 236, 234, 0.72) !important;
  --surface-muted: rgba(241, 243, 244, 0.45) !important;
  --surface-glass: rgba(255, 255, 255, 0.55) !important;
  --surface-glass-strong: rgba(255, 255, 255, 0.72) !important;
  --border: rgba(40, 50, 45, 0.14) !important;
  --border-strong: rgba(40, 50, 45, 0.28) !important;
  --border-muted: rgba(40, 50, 45, 0.08) !important;

  /* 浅色下原来是深绿配白字，主色必须压深，白字才有对比。 */
  --primary: color-mix(in srgb, var(--palette-accent) 58%, #0f1b18) !important;
  --primary-hover: color-mix(in srgb, var(--palette-accent) 44%, #0f1b18) !important;
  --primary-soft: color-mix(in srgb, var(--palette-accent) 16%, transparent) !important;
  --primary-soft-hover: color-mix(in srgb, var(--palette-accent) 24%, transparent) !important;
  --primary-soft-strong: color-mix(in srgb, var(--palette-accent) 30%, transparent) !important;
  --primary-border: color-mix(in srgb, var(--palette-accent) 38%, transparent) !important;
  --primary-border-strong: color-mix(in srgb, var(--palette-accent) 58%, transparent) !important;
  --on-primary: #ffffff !important;
  --link: color-mix(in srgb, var(--palette-accent) 58%, #0f1b18) !important;
  --accent: color-mix(in srgb, var(--palette-accent) 55%, #0f1b18) !important;
  --focus-soft: color-mix(in srgb, var(--palette-accent) 22%, transparent) !important;
  --scrollbar: color-mix(in srgb, var(--palette-accent) 45%, transparent) !important;
}
"""
    return (
        template.replace("__PRIMARY__", primary)
        .replace("__SECONDARY__", secondary)
        .strip()
    )


_THEME_SYNC_SCRIPT = """
/* 主题色跟随：向父页面要当前主/辅色，拿到就覆盖那两个快照。 */
(function () {
  var root = document.documentElement;
  var REQUEST = "astrbot-palette:plugin-page-theme-request";
  var MESSAGE = "astrbot-palette:plugin-page-theme";
  function applyTheme(colors) {
    if (!colors) { return; }
    if (colors.primary) { root.style.setProperty("--palette-accent", colors.primary); }
    if (colors.secondary) { root.style.setProperty("--palette-accent-2", colors.secondary); }
  }
  window.addEventListener("message", function (event) {
    var data = event && event.data;
    if (!data || data.type !== MESSAGE) { return; }
    applyTheme(data.colors);
  });
  function ask() {
    try { window.parent.postMessage({ type: REQUEST }, "*"); } catch (_) {}
  }
  ask();
  window.addEventListener("load", ask);
  setTimeout(ask, 900);
  setTimeout(ask, 2600);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") { ask(); }
  });
})();
""".strip()


@dataclass(frozen=True)
class PluginPageTarget:
    """一个已适配的第三方插件页面。

    AstrBot 的插件页面目录有两种命名（`views` 优先，`pages` 兼容），所以
    页面路径直接写成相对插件目录的路径，避免猜错。
    """

    plugin: str
    page: str
    css: str
    script: str = ""
    rel_path: str = ""

    @property
    def display_name(self) -> str:
        return f"{self.plugin}/{self.page}"

    @property
    def index_rel_path(self) -> str:
        return self.rel_path or f"pages/{self.page}/index.html"


def _targets(primary: object = "", secondary: object = "") -> tuple[PluginPageTarget, ...]:
    accent = _safe_hex(primary, DEFAULT_PRIMARY)
    accent_2 = _safe_hex(secondary, DEFAULT_SECONDARY)
    # 表情包管理器四个子页面共用同一份样式，只生成一次。
    meme_css = _meme_manager_css(accent, accent_2)
    return (
        PluginPageTarget(
            plugin="astrbot_plugin_livingmemory",
            page="dashboard",
            css=_livingmemory_css(accent, accent_2),
            script=_THEME_SYNC_SCRIPT,
        ),
        PluginPageTarget(
            plugin="astrbot_plugin_memewiki",
            page="slang",
            css=_memewiki_css(accent, accent_2),
            script=_THEME_SYNC_SCRIPT,
            rel_path="views/slang/index.html",
        ),
        PluginPageTarget(
            plugin="astrbot_plugin_self_learning",
            page="dashboard",
            css=_self_learning_css(accent, accent_2),
            script=_THEME_SYNC_SCRIPT,
            rel_path="pages/dashboard/index.html",
        ),
        # 表情包管理器是「一个外壳 + 四个独立子页面」，共用同一份 ui.css，
        # 所以四个 HTML 都要写一遍（页面间是普通站内跳转，不是 iframe 套 iframe）。
        *(
            PluginPageTarget(
                plugin="meme_manager",
                page=sub_page,
                css=meme_css,
                script=_THEME_SYNC_SCRIPT,
                rel_path=f"pages/app/{sub_page}/index.html",
            )
            for sub_page in ("a_manage", "catalog", "semantic", "settings")
        ),
    )


def _plugins_root() -> Path | None:
    try:
        from astrbot.core.utils.astrbot_path import get_astrbot_plugin_path

        return Path(get_astrbot_plugin_path())
    except Exception:
        # palette/plugin_pages.py -> palette -> astrbot_plugin_palette -> plugins
        fallback = Path(__file__).resolve().parents[2]
        return fallback if fallback.is_dir() else None


def page_index_file(target: PluginPageTarget) -> Path | None:
    root = _plugins_root()
    if root is None:
        return None
    return root / target.plugin / target.index_rel_path


def build_block(target: PluginPageTarget, newline: str = "\n") -> str:
    """样式块：标记顶格独占一行，写入/替换/撤销都能精确命中。"""

    lines = [
        START_MARKER,
        f'<style id="{STYLE_ID}">',
        target.css,
        "</style>",
    ]
    if target.script:
        lines += [f'<script id="{SCRIPT_ID}">', target.script, "</script>"]
    lines.append(END_MARKER)
    return "\n".join(lines).replace("\n", newline) + newline


def apply_block(content: str, block: str) -> str:
    """幂等写入：已有标记就替换整块，没有就插到 </head> 所在行的行首。"""
    newline = _newline_for(content)
    block = block.replace("\r\n", "\n").replace("\n", newline)
    if START_MARKER in content:
        return _BLOCK_RE.sub(lambda _: block, content, count=1)
    head_close = re.search(r"</head\s*>", content, flags=re.IGNORECASE)
    if head_close is None:
        raise ValueError("未找到 </head>，无法写入插件页面适配样式。")
    line_start = content.rfind("\n", 0, head_close.start()) + 1
    return content[:line_start] + block + content[line_start:]


def strip_block(content: str) -> str:
    if START_MARKER not in content:
        return content
    return _BLOCK_RE.sub("", content, count=1)


def _backup_once(backup_dir: Path, target: PluginPageTarget, content: str) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"plugin-page-{target.plugin}-{target.page}.html"
    if not backup.exists():
        backup.write_text(content, encoding="utf-8")


def _file_state(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


# 页面文件状态缓存：{路径: (mtime_ns, size, 上次写入时的 enabled)}。
# 保存设置会频繁走到这里，而十几个 HTML 加起来几百 KB；文件没被动过
# （插件没更新、也没被我们自己写过）就直接跳过读盘与比对。
_FILE_STATE: dict[str, tuple[int, int, bool]] = {}


def ensure_plugin_page_injection(
    enabled: bool,
    backup_dir: Path,
    primary: object = "",
    secondary: object = "",
) -> list[str]:
    """让已适配的插件页面跟随调色盘：写入或撤掉样式块。

    `primary` / `secondary` 是当前主题色，写进样式块当快照；父页面拿到实时值后
    还会通过 postMessage 覆盖。返回可直接写日志的说明，未命中（插件没装）时保持静默。
    """

    notes: list[str] = []
    for target in _targets(primary, secondary):
        index_file = page_index_file(target)
        if index_file is None or not index_file.is_file():
            continue

        cache_key = str(index_file)
        before = _file_state(index_file)
        cached = _FILE_STATE.get(cache_key)
        if (
            before is not None
            and cached is not None
            and cached[2] == enabled
            and (cached[0], cached[1]) == before
        ):
            continue

        try:
            try:
                content = index_file.read_text(encoding="utf-8")
            except OSError as exc:
                notes.append(f"{target.display_name} 页面读取失败：{exc}")
                continue

            if not enabled:
                if START_MARKER not in content:
                    continue
                try:
                    index_file.write_text(strip_block(content), encoding="utf-8")
                except OSError as exc:
                    notes.append(f"{target.display_name} 页面还原失败：{exc}")
                    continue
                notes.append(f"{target.display_name} 已还原为插件自带配色。")
                continue

            block = build_block(target, _newline_for(content))
            try:
                updated = apply_block(content, block)
            except ValueError as exc:
                notes.append(f"{target.display_name} 跳过：{exc}")
                continue
            if updated == content:
                continue
            try:
                if START_MARKER not in content:
                    _backup_once(backup_dir, target, content)
                index_file.write_text(updated, encoding="utf-8")
            except OSError as exc:
                notes.append(f"{target.display_name} 页面写入失败：{exc}")
                continue
            notes.append(f"{target.display_name} 已应用调色盘配色。")
        finally:
            after = _file_state(index_file)
            if after is not None:
                _FILE_STATE[cache_key] = (after[0], after[1], enabled)

    return notes


def is_injected(index_file: Path) -> bool:
    """页面里是否已经带着调色盘的样式块（设置页/测试用）。"""
    try:
        return START_MARKER in index_file.read_text(encoding="utf-8")
    except OSError:
        return False


__all__ = [
    "PluginPageTarget",
    "apply_block",
    "build_block",
    "ensure_plugin_page_injection",
    "is_injected",
    "page_index_file",
    "strip_block",
]
