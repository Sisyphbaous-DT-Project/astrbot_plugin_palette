# AstrBot调色盘

AstrBot调色盘是一个 AstrBot WebUI 美化插件。当前版本聚焦于运行时背景图、透明界面和文字可读性增强，让 Dashboard 可以在不修改 AstrBot 源码的前提下换上自定义壁纸。

> 当前版本：`0.1.0`
>
> 兼容 AstrBot：`>=4.25.5,<5`

## 功能

- 上传并启用 WebUI 背景图片。
- 调整背景填充方式、位置、遮罩、模糊、灰度、亮度、对比度和饱和度。
- 将 Dashboard 常驻面板透明化，支持完全透明的悬浮文字效果。
- 提供文字和图标可读性增强，包括柔和阴影和强力描边。
- 提供插件设置页，可在 AstrBot 插件详情页中直接配置。
- 首次注入后自动推荐切换到 AstrBot 深色主题，用户仍可在 AstrBot 设置中改回其他主题。

## 安装

进入 AstrBot 插件目录：

```bash
cd /path/to/AstrBot/data/plugins
git clone https://github.com/Sisyphbaous-DT-Project/astrbot_plugin_palette.git
```

然后在 AstrBot WebUI 中重载插件，或重启 AstrBot。

插件加载后，AstrBot 插件列表中应显示：

- 插件名：`astrbot_plugin_palette`
- 展示名：`AstrBot调色盘`
- 版本：`0.1.0`

## 使用

1. 打开 AstrBot WebUI。
2. 进入插件管理，找到 `AstrBot调色盘`。
3. 打开插件设置页。
4. 上传背景图片。
5. 按喜好调整透明度、遮罩、背景滤镜和文字增强。
6. 保存后刷新 WebUI，背景会自动应用到 Dashboard。

支持的背景图片格式：

- `jpg`
- `jpeg`
- `png`
- `webp`
- `gif`

单张图片最大 `10MB`。

## 配置项

| 配置项 | 说明 | 默认值 |
| --- | --- | --- |
| `enabled` | 是否启用 WebUI 美化 | `true` |
| `background_image` | 当前背景图片文件名 | `""` |
| `background_fit` | 背景填充方式，可选 `cover`、`contain`、`auto` | `cover` |
| `background_position` | 背景位置 | `center center` |
| `background_blur` | 背景模糊强度，单位 px | `0` |
| `background_dim` | 全局暗色遮罩强度 | `0.5` |
| `surface_opacity` | 常驻面板底色强度，`0` 为透明 | `0.0` |
| `text_enhancement_mode` | 文字增强模式，可选 `off`、`soft_shadow`、`stroke` | `soft_shadow` |
| `text_enhancement_strength` | 文字增强强度 | `1.0` |
| `background_grayscale` | 背景灰度 | `0.0` |
| `background_brightness` | 背景亮度 | `1.0` |
| `background_contrast` | 背景对比度 | `1.0` |
| `background_saturation` | 背景饱和度 | `1.0` |
| `advanced_css` | 追加到主题 CSS 末尾的高级自定义 CSS | `""` |

## 工作方式

本插件不会修改 AstrBot 源码。

为了让 Dashboard 主页面能加载插件主题，本插件会在运行时向 AstrBot 的 `data/dist/index.html` 注入一段带标记的启动脚本。注入前会在插件数据目录中备份原始 `index.html`，之后重复注入会替换已有标记块，避免重复写入。

注入标记如下：

```html
<!-- astrbot_plugin_palette:start -->
...
<!-- astrbot_plugin_palette:end -->
```

背景图片保存在插件数据目录下：

```text
data/plugin_data/astrbot_plugin_palette/backgrounds
```

Dashboard 入口备份保存在：

```text
data/plugin_data/astrbot_plugin_palette/dashboard_backups
```

## Web API

插件通过 AstrBot 插件 Web API 暴露接口。实际访问路径由 AstrBot 转发到 `/api/v1/plugins/extensions/...`。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/astrbot_plugin_palette/status` | 获取插件版本、路径和注入状态 |
| `GET` | `/astrbot_plugin_palette/config` | 获取当前公开配置 |
| `POST` | `/astrbot_plugin_palette/config` | 保存配置 |
| `GET` | `/astrbot_plugin_palette/theme.css` | 获取运行时主题 CSS |
| `GET` | `/astrbot_plugin_palette/background-preview` | 获取当前背景预览 |
| `POST` | `/astrbot_plugin_palette/upload-background` | 上传背景图片 |
| `GET` | `/astrbot_plugin_palette/backgrounds/<filename>` | 读取背景图片 |

## 深色主题提示

透明背景更适合搭配 AstrBot 深色模式。插件注入脚本第一次运行时，会向浏览器 `localStorage` 写入：

```text
themeMode=dark
uiTheme=PurpleThemeDark
astrbot_palette_dark_theme_bootstrapped=1
```

这只执行一次。用户之后在 AstrBot WebUI 中手动改回浅色或跟随系统，插件不会反复覆盖。

## 安全边界

- 不修改 AstrBot 源码。
- 只写入 AstrBot 运行时 Dashboard 入口 `data/dist/index.html` 和插件自己的数据目录。
- 高级 CSS 会拦截 `@import` 和外链 `url()`，避免引入外部资源。
- 背景文件名会被限制为插件生成的本地文件名，避免路径穿越。
- 上传图片会检查扩展名、大小和文件头。

## 开发检查

在插件仓库根目录运行：

```bash
PYTHONPATH=/path/to/AstrBot python -m py_compile main.py palette/*.py
node --check pages/settings/app.js
python -m json.tool _conf_schema.json
git diff --check
```

如果要在本地 AstrBot 中测试，建议复制插件目录到 `data/plugins/astrbot_plugin_palette`，不要使用软链接或 bind mount。

## 版本计划

`0.1.0` 已提供背景图上传、运行时注入、透明化和可读性增强骨架。后续版本会继续补齐更多页面的透明化细节，并把首次深色主题切换逻辑调整得更精确。

## 作者

`C₂₂H₂₅NO₆`
