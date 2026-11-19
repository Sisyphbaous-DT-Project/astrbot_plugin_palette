"""`palette.plugin_pages` 的行为回归测试：写入幂等、可撤销、不误伤页面。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from palette import plugin_pages  # noqa: E402

_PAGE = """\ufeff<!DOCTYPE html>
<html>
  <head>
    <meta charset="UTF-8" />
    <link rel="stylesheet" href="./assets/styles.min.css" />
  </head>
  <body><div id="app"></div></body>
</html>
"""


class ApplyBlockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.target = plugin_pages._targets()[0]
        self.block = plugin_pages.build_block(self.target)

    def test_inserts_before_head_close_and_keeps_bom(self) -> None:
        updated = plugin_pages.apply_block(_PAGE, self.block)
        self.assertIn(plugin_pages.START_MARKER, updated)
        self.assertIn(plugin_pages.END_MARKER, updated)
        self.assertTrue(updated.startswith("\ufeff<!DOCTYPE html>"))
        self.assertLess(
            updated.index(plugin_pages.START_MARKER),
            updated.index("</head>"),
        )
        self.assertEqual(
            updated.count(f'<style id="{plugin_pages.STYLE_ID}">'), 1
        )

    def test_reapply_replaces_block_instead_of_stacking(self) -> None:
        once = plugin_pages.apply_block(_PAGE, self.block)
        twice = plugin_pages.apply_block(once, self.block)
        self.assertEqual(once, twice)
        self.assertEqual(twice.count(plugin_pages.START_MARKER), 1)

    def test_strip_restores_original(self) -> None:
        patched = plugin_pages.apply_block(_PAGE, self.block)
        self.assertEqual(plugin_pages.strip_block(patched), _PAGE)

    def test_crlf_page_keeps_crlf(self) -> None:
        crlf = _PAGE.replace("\n", "\r\n")
        updated = plugin_pages.apply_block(crlf, self.block)
        self.assertNotIn("\n", updated.replace("\r\n", ""))
        self.assertIn(plugin_pages.START_MARKER, updated)

    def test_page_without_head_close_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            plugin_pages.apply_block("<html><body></body></html>", self.block)


class EnsureInjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.page = self.root / "pages" / "dashboard" / "index.html"
        self.page.parent.mkdir(parents=True)
        self.page.write_text(_PAGE, encoding="utf-8")
        self.backup = self.root / "backups"

    def _ensure(self, enabled: bool) -> list[str]:
        original_index = plugin_pages.page_index_file
        original_targets = plugin_pages._targets
        target = plugin_pages._targets()[0]
        plugin_pages.page_index_file = lambda t: self.page
        plugin_pages._targets = lambda primary="", secondary="": (target,)
        self.addCleanup(setattr, plugin_pages, "page_index_file", original_index)
        self.addCleanup(setattr, plugin_pages, "_targets", original_targets)
        return plugin_pages.ensure_plugin_page_injection(enabled, self.backup)

    def test_writes_once_and_stays_quiet_on_second_run(self) -> None:
        self.assertTrue(self._ensure(True))
        self.assertEqual(self._ensure(True), [])
        self.assertIn(plugin_pages.START_MARKER, self.page.read_text("utf-8"))
        self.assertTrue(list(self.backup.glob("plugin-page-*.html")))

    def test_disable_restores_page(self) -> None:
        self._ensure(True)
        notes = self._ensure(False)
        self.assertTrue(notes)
        self.assertEqual(self.page.read_text("utf-8"), _PAGE)

    def test_missing_page_is_skipped(self) -> None:
        self.page.unlink()
        self.assertEqual(self._ensure(True), [])


class CssContentTests(unittest.TestCase):
    def test_css_makes_page_transparent_and_keeps_readability_layer(self) -> None:
        css = plugin_pages._livingmemory_css("#7daabf", "#707db8")
        # 底色必须交给壁纸，列表/卡片改为半透明，网格纹理换成压暗层。
        self.assertIn("background: transparent !important;", css)
        self.assertIn("body::before", css)
        self.assertIn('html[data-theme="dark"]', css)
        self.assertIn('html[data-theme="light"]', css)
        self.assertNotIn("!important !important", css)

    def test_css_bakes_theme_colors_and_radius(self) -> None:
        css = plugin_pages._livingmemory_css("#123456", "#abcdef")
        # 主题色写进快照，运行时由父页面推实时值覆盖。
        self.assertIn("--palette-accent: #123456;", css)
        self.assertIn("--palette-accent-2: #abcdef;", css)
        self.assertIn("--accent: var(--palette-accent) !important;", css)
        self.assertIn("--signal: var(--palette-accent-2) !important;", css)
        # 圆角对齐调色盘档位，且 editorial 写死的小圆角被逐类覆盖。
        self.assertIn("--radius-lg: 16px !important;", css)
        self.assertIn("border-radius: 18px !important;", css)
        self.assertIn("border-radius: 999px !important;", css)

    def test_block_includes_theme_bridge_script(self) -> None:
        target = plugin_pages._targets("#123456", "#abcdef")[0]
        block = plugin_pages.build_block(target)
        self.assertIn(f'<script id="{plugin_pages.SCRIPT_ID}">', block)
        self.assertIn("astrbot-palette:plugin-page-theme-request", block)
        # 颜色非法时回退到调色盘默认色，不能把脏值写进 CSS。
        fallback = plugin_pages._targets("oops", None)[0]
        self.assertIn(plugin_pages.DEFAULT_PRIMARY, fallback.css)
        self.assertIn(plugin_pages.DEFAULT_SECONDARY, fallback.css)


class TargetPathTests(unittest.TestCase):
    def test_page_roots_cover_views_and_pages_layouts(self) -> None:
        # AstrBot 两种目录名都要支持：livingmemory 用 pages/，memewiki 用 views/。
        paths = {t.display_name: t.index_rel_path for t in plugin_pages._targets()}
        self.assertEqual(
            paths["astrbot_plugin_livingmemory/dashboard"],
            "pages/dashboard/index.html",
        )
        self.assertEqual(paths["astrbot_plugin_memewiki/slang"], "views/slang/index.html")
        self.assertEqual(
            paths["astrbot_plugin_self_learning/dashboard"],
            "pages/dashboard/index.html",
        )
        # 表情包管理器是一个外壳 + 四个独立子页面，四个都要写。
        for sub in ("a_manage", "catalog", "semantic", "settings"):
            self.assertEqual(
                paths[f"meme_manager/{sub}"],
                f"pages/app/{sub}/index.html",
            )

    def test_index_file_joins_rel_path(self) -> None:
        target = next(
            t for t in plugin_pages._targets() if t.plugin == "astrbot_plugin_memewiki"
        )
        resolved = plugin_pages.page_index_file(target)
        self.assertIsNotNone(resolved)
        self.assertTrue(
            str(resolved)
            .replace("\\", "/")
            .endswith("astrbot_plugin_memewiki/views/slang/index.html")
        )


class MemewikiCssTests(unittest.TestCase):
    def test_css_follows_dashboard_theme_not_os_preference(self) -> None:
        css = plugin_pages._memewiki_css("#7daabf", "#707db8")
        # 原页面只有 prefers-color-scheme，这里必须换成 data-theme 才跟面板走。
        self.assertIn('html[data-theme="dark"]', css)
        self.assertIn('html[data-theme="light"]', css)
        self.assertNotIn("prefers-color-scheme", css)

    def test_css_makes_page_glass_and_keeps_readability(self) -> None:
        css = plugin_pages._memewiki_css("#7daabf", "#707db8")
        self.assertIn("background: transparent !important;", css)
        # 不再铺任何压暗：卡片之外的空白直接露壁纸，压暗只由面板自己承担。
        self.assertNotIn("body::before", css)
        self.assertNotIn(".wrap::before", css)
        # iframe 画布会按 color-scheme 刷黑，必须改成 normal 才真透明。
        self.assertIn("color-scheme: normal !important;", css)
        self.assertIn("--panel: rgba(", css)
        self.assertIn("--field: rgba(", css)

    def test_css_bakes_theme_colors_and_radius(self) -> None:
        css = plugin_pages._memewiki_css("#123456", "#abcdef")
        self.assertIn("--palette-accent: #123456;", css)
        self.assertIn("--palette-accent-2: #abcdef;", css)
        self.assertIn("--accent: var(--palette-accent) !important;", css)
        self.assertIn("border-radius: 18px !important;", css)
        self.assertIn("border-radius: 10px !important;", css)
        # 深色下主按钮必须换成深字，否则浅色强调色配白字看不清。
        self.assertIn('html[data-theme="dark"] button.primary', css)
        self.assertNotIn("!important !important", css)


class SelfLearningCssTests(unittest.TestCase):
    def test_page_becomes_transparent_with_scrim(self) -> None:
        css = plugin_pages._self_learning_css("#7daabf", "#707db8")
        self.assertIn("background: transparent !important;", css)
        # 这一页内容铺满，压暗整页铺即可，但不能是 position: fixed 之外的怪层级。
        self.assertIn("body::before", css)
        self.assertIn("--bg: transparent !important;", css)

    def test_signal_follows_theme_color(self) -> None:
        css = plugin_pages._self_learning_css("#123456", "#abcdef")
        self.assertIn("--palette-accent: #123456;", css)
        self.assertIn("--palette-accent-2: #abcdef;", css)
        # 信号黄（--signal / --ark-signal）必须换成调色盘主色。
        self.assertIn("--signal: var(--palette-accent) !important;", css)
        self.assertIn("--ark-signal: var(--palette-accent) !important;", css)
        # 图表主序列也要跟随，否则柱状图还是黄的。
        self.assertIn("--chart-1: var(--palette-accent) !important;", css)

    def test_surfaces_and_radius(self) -> None:
        css = plugin_pages._self_learning_css("#7daabf", "#707db8")
        self.assertIn("--surface-solid: rgba(", css)
        self.assertIn("--surface: rgba(", css)
        self.assertIn("border-radius: 14px !important;", css)
        self.assertIn("border-radius: 10px !important;", css)
        # 导航是 14 项连排列表，圆角会让分隔线翘成弧线，不能收。
        self.assertNotIn(".nav-item,", css)
        self.assertNotIn("gap: 2px", css)

    def test_theme_switch_uses_data_theme(self) -> None:
        css = plugin_pages._self_learning_css("#7daabf", "#707db8")
        self.assertIn('html[data-theme="dark"]', css)
        self.assertIn('html[data-theme="light"]', css)
        self.assertNotIn("prefers-color-scheme", css)
        self.assertNotIn("!important !important", css)


class MemeManagerCssTests(unittest.TestCase):
    def test_page_becomes_transparent_without_ambient_gradients(self) -> None:
        css = plugin_pages._meme_manager_css("#7daabf", "#707db8")
        self.assertIn("background-color: transparent !important;", css)
        # 原来 body 上的绿色/暖色氛围光斑必须去掉，否则壁纸会发绿。
        self.assertIn("background-image: none !important;", css)
        # 卡片之外的空白要完全透明，不能整页铺压暗。
        self.assertNotIn("body::before", css)

    def test_surfaces_become_glass(self) -> None:
        css = plugin_pages._meme_manager_css("#7daabf", "#707db8")
        for token in (
            "--surface: rgba(",
            "--surface-elevated: rgba(",
            "--surface-glass: rgba(",
            "--border: rgba(",
        ):
            self.assertIn(token, css)

    def test_brand_tokens_follow_theme_color(self) -> None:
        css = plugin_pages._meme_manager_css("#123456", "#abcdef")
        self.assertIn("--palette-accent: #123456;", css)
        # 品牌绿整套跟着主色走，深色下强调色+深字，浅色下压深保证白字。
        self.assertIn("--primary: var(--palette-accent) !important;", css)
        self.assertIn("--on-primary: #0b1013 !important;", css)
        self.assertIn("--on-primary: #ffffff !important;", css)
        self.assertIn("--primary-soft: color-mix(", css)
        self.assertIn("--link: var(--palette-accent) !important;", css)
        self.assertNotIn("!important !important", css)

    def test_radius_is_left_alone(self) -> None:
        # 这一页的圆角档位（8/12/16/20/999）本来就和调色盘一致，不重复覆盖。
        css = plugin_pages._meme_manager_css("#7daabf", "#707db8")
        self.assertNotIn("border-radius", css)


if __name__ == "__main__":
    unittest.main()
