"""设置页定时轮换控件的静态断言测试。

只读取仓库中的 `pages/settings/`、`README.md` 与 `_conf_schema.json`，
不写任何文件；用于防止后续改动把轮换开关、分钟输入或配置读写逻辑弄丢。
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_INDEX_HTML = (_REPO_ROOT / "pages" / "settings" / "index.html").read_text(
    encoding="utf-8"
)
_APP_JS = (_REPO_ROOT / "pages" / "settings" / "app.js").read_text(encoding="utf-8")
_STYLE_CSS = (_REPO_ROOT / "pages" / "settings" / "style.css").read_text(
    encoding="utf-8"
)
_README = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")
_SCHEMA = json.loads(
    (_REPO_ROOT / "_conf_schema.json").read_text(encoding="utf-8")
)


class SettingsRotationMarkupTest(unittest.TestCase):
    def test_rotation_switch_present(self) -> None:
        self.assertIn('id="background-rotation-enabled"', _INDEX_HTML)
        self.assertIn('name="background_rotation_enabled"', _INDEX_HTML)

    def test_rotation_interval_input_bounds(self) -> None:
        match = re.search(
            r'<input[^>]*id="background-rotation-interval"[^>]*>',
            _INDEX_HTML,
            re.S,
        )
        self.assertIsNotNone(match, "缺少轮换间隔输入框")
        tag = match.group(0)
        self.assertIn('type="number"', tag)
        self.assertIn('min="1"', tag)
        self.assertIn('max="1440"', tag)
        self.assertIn('step="1"', tag)
        self.assertIn('inputmode="numeric"', tag)

    def test_rotation_styles_present(self) -> None:
        self.assertIn(".rotation-settings", _STYLE_CSS)
        self.assertIn(".rotation-interval", _STYLE_CSS)
        self.assertIn(":disabled", _STYLE_CSS)


class SettingsRotationFormLogicTest(unittest.TestCase):
    def test_config_from_form_reads_rotation_fields(self) -> None:
        match = re.search(
            r"function configFromForm\(\) \{(?P<body>.*?)\n\}",
            _APP_JS,
            re.S,
        )
        self.assertIsNotNone(match)
        body = match.group("body")
        self.assertIn("background_rotation_enabled", body)
        self.assertIn("background_rotation_interval_minutes", body)

    def test_apply_form_writes_rotation_fields(self) -> None:
        match = re.search(
            r"function applyForm\(config\) \{(?P<body>.*?)\n\}",
            _APP_JS,
            re.S,
        )
        self.assertIsNotNone(match)
        body = match.group("body")
        self.assertIn("background_rotation_enabled", body)
        self.assertIn("background_rotation_interval_minutes", body)
        self.assertIn("syncRotationInputs()", body)

    def test_render_status_shows_rotation_summary(self) -> None:
        match = re.search(
            r"function renderStatus\(status, config\) \{(?P<body>.*?)\n\}",
            _APP_JS,
            re.S,
        )
        self.assertIsNotNone(match)
        body = match.group("body")
        self.assertIn("定时轮换", body)
        self.assertIn("分钟随机切换", body)

    def test_interval_fallback_and_clamp(self) -> None:
        match = re.search(
            r"function rotationIntervalFromInput\(\) \{(?P<body>.*?)\n\}",
            _APP_JS,
            re.S,
        )
        self.assertIsNotNone(match, "缺少间隔读取辅助函数")
        body = match.group("body")
        self.assertIn("return 30;", body)
        self.assertIn("1440", body)


class RotationSchemaAndDocsTest(unittest.TestCase):
    def test_conf_schema_declares_rotation_fields(self) -> None:
        enabled = _SCHEMA.get("background_rotation_enabled")
        self.assertIsNotNone(enabled)
        self.assertEqual(enabled["type"], "bool")
        self.assertIs(enabled["default"], False)

        interval = _SCHEMA.get("background_rotation_interval_minutes")
        self.assertIsNotNone(interval)
        self.assertEqual(interval["type"], "int")
        self.assertEqual(interval["default"], 30)
        self.assertEqual(interval["minimum"], 1)
        self.assertEqual(interval["maximum"], 1440)
        # AstrBot 配置渲染器支持 slider 元数据约束数值控件；
        # minimum/maximum 仅为文档声明，边界由后端规范化兜底。
        self.assertEqual(interval["slider"], {"min": 1, "max": 1440, "step": 1})

    def test_readme_documents_rotation_fields(self) -> None:
        self.assertIn("background_rotation_enabled", _README)
        self.assertIn("background_rotation_interval_minutes", _README)


if __name__ == "__main__":
    unittest.main()
