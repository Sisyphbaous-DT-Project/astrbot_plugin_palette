# AstrBot调色盘

AstrBot调色盘是一个 AstrBot WebUI 美化插件。当前版本聚焦于背景图库、透明界面、文字可读性增强和壁纸主题色联动，让 Dashboard 可以在不修改 AstrBot 源码的前提下换上自定义壁纸。

> 当前版本：`0.3.0`
>
> 兼容 AstrBot：`>=4.26.0-beta1`

## 功能

- 上传多张 WebUI 背景图片，并通过缩略图库一键切换。
- 支持打开或刷新 WebUI 时从图库随机切换背景。
- 调整背景填充方式、位置、遮罩、模糊、灰度、亮度、对比度和饱和度。
- 将 Dashboard 常驻面板透明化，支持完全透明的悬浮文字效果。
- 提供文字和图标可读性增强，包括柔和阴影和强力描边。
- 自动读取当前壁纸主题色，并同步 AstrBot 主色与辅色。
- 提供插件设置页，可在 AstrBot 插件详情页中直接配置。
- 首次注入后自动推荐切换到 AstrBot 深色主题，用户仍可在 AstrBot 设置中改回其他主题。

## 效果展示


![1](docs/images/dashboard-transparent.png)


![2](docs/images/plugin-settings-gallery.png)


![3](docs/images/webchat-transparent.png)


![4](docs/images/theme-color-sync.png)

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
- 版本：`0.3.0`

## 使用

1. 打开 AstrBot WebUI。
2. 进入插件管理，找到 `AstrBot调色盘`。
3. 打开插件设置页。
4. 上传一张或多张背景图片。
5. 在缩略图库中点击图片，切换当前 WebUI 背景。
6. 按喜好调整透明度、遮罩、背景滤镜、文字增强、随机背景和主题色联动。
7. 保存后刷新 WebUI，背景会自动应用到 Dashboard。

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
| `background_images` | 背景图库文件名列表 | `[]` |
| `background_fit` | 背景填充方式，可选 `cover`、`contain`、`stretch`、`auto` | `cover` |
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
| `random_background_on_load` | 打开或刷新 WebUI 时随机背景 | `false` |
| `auto_theme_enabled` | 是否自动同步壁纸主题色 | `true` |
| `theme_primary` | 自动生成的 AstrBot 主色，格式为 `#RRGGBB` | `""` |
| `theme_secondary` | 自动生成的 AstrBot 辅色，格式为 `#RRGGBB` | `""` |
| `advanced_css` | 追加到主题 CSS 末尾的高级自定义 CSS | `""` |

## 主题色联动

`0.3.0` 会在当前壁纸切换后读取图片主题色，生成一组适合 UI 使用的主色和辅色。主题色联动开启时，插件会把这两个颜色写入 AstrBot 已有的浏览器本地配置：

```text
themePrimary
themeSecondary
```

同时，插件会注入一小段运行时样式，让按钮、强调色和部分 Vuetify 主题变量无需刷新也能马上跟随壁纸变化。

关闭“主题色联动”或禁用调色盘时，插件会恢复启用联动前保存的 AstrBot 主色和辅色。没有上传壁纸时，主题色联动不会主动改色。

如果更换了图片但想手动重新读取颜色，可以在设置页点击“重新读取壁纸主题色”。

## 背景图库

上传图片只会加入图库，不会自动切换当前背景。点击缩略图后，插件会把该图片保存为当前背景，并重新读取主题色。

开启“打开或刷新时随机背景”后，Dashboard 每次重新打开或整页刷新都会从图库随机选一张，并写回当前背景。页面内路由切换不会触发随机，避免使用过程中频繁换图。

“拉伸铺满”会让图片完整铺满窗口且不裁切，但可能改变原图比例。

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
| `POST` | `/astrbot_plugin_palette/upload-background` | 上传背景图片到图库 |
| `POST` | `/astrbot_plugin_palette/backgrounds/select` | 切换当前背景图片 |
| `POST` | `/astrbot_plugin_palette/backgrounds/delete` | 删除图库背景图片 |
| `POST` | `/astrbot_plugin_palette/backgrounds/random-select` | 随机切换并写回当前背景 |
| `POST` | `/astrbot_plugin_palette/theme-colors/recalculate` | 重新读取当前壁纸主题色 |
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

## 更新日志

完整更新日志见 [CHANGELOG.md](CHANGELOG.md)。版本化记录保存在 [changelogs](changelogs) 目录。

## 版本计划

`0.1.0` 已提供背景图上传、运行时注入、透明化和可读性增强。

`0.2.0` 新增壁纸主题色联动，可以自动读取壁纸颜色并同步 AstrBot 主色与辅色。

`0.3.0` 新增多背景图库、缩略图切换、刷新随机背景和拉伸铺满。

后续版本会继续补齐更多页面的透明化细节，并探索更完整的主题色板推导。

## 作者

`C₂₂H₂₅NO₆`
