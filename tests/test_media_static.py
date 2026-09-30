"""设置页媒体入口、配置、版本和静态预览约束。"""

from pathlib import Path
import json
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent.parent


class MediaSettingsTest(unittest.TestCase):
    def test_dynamic_config_and_form_contract(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text())
        self.assertEqual(schema["dynamic_background_enabled"]["type"], "bool")
        self.assertIs(schema["dynamic_background_enabled"]["default"], True)
        app = (ROOT / "pages/settings/app.js").read_text()
        self.assertIn("dynamic_background_enabled: dynamicBackgroundInput.checked", app)
        self.assertIn(
            "dynamicBackgroundInput.checked = config.dynamic_background_enabled !== false",
            app,
        )
        self.assertIn(
            'id="dynamic-background-enabled"',
            (ROOT / "pages/settings/index.html").read_text(),
        )
        self.assertIn(
            "| `dynamic_background_enabled` |", (ROOT / "README.md").read_text()
        )

    def test_upload_import_and_small_default_previews(self):
        app = (ROOT / "pages/settings/app.js").read_text()
        html = (ROOT / "pages/settings/index.html").read_text()
        self.assertIn('id="open-wallpaper-import"', html)
        self.assertIn("webkitdirectory", html)
        self.assertEqual(
            len(re.findall(r'accept="[^"]*video/mp4,video/webm"', html)), 2
        )
        self.assertIn("const upload = await prepareUpload(file)", app)
        self.assertIn("bridge.upload(`upload-background/${orientation}`, upload)", app)
        self.assertIn('bridge.apiGet("background-thumbnail", { filename })', app)
        self.assertIn("liquidGlass.updateFilter(imageUrl, config)", app)
        self.assertIn("mediaPreview.close()", app)

    def test_current_versions_are_consistent(self):
        self.assertIn('VERSION = "0.5.2"', (ROOT / "palette/constants.py").read_text())
        self.assertIn('version: "0.5.2"', (ROOT / "metadata.yaml").read_text())
        self.assertIn("当前版本：`0.5.2`", (ROOT / "README.md").read_text())
        self.assertTrue((ROOT / "changelogs/v0.5.2.md").is_file())

    def test_new_javascript_modules_parse(self):
        for path in (
            "palette/media_runtime.js",
            "palette/media_cache.js",
            "pages/settings/media.js",
            "pages/settings/wallpaper-import.js",
            "pages/settings/local-cache.js",
            "tests/media_cache_browser.cjs",
        ):
            with self.subTest(path=path):
                result = subprocess.run(
                    ["node", "--check", str(ROOT / path)],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_local_cache_is_browser_local_and_has_clear_entry(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text())
        self.assertNotIn("local_cache", schema)
        html = (ROOT / "pages/settings/index.html").read_text()
        self.assertIn('id="local-cache-status"', html)
        self.assertIn('id="clear-local-cache"', html)
        self.assertIn("1GiB", (ROOT / "README.md").read_text())
        self.assertIn("无需重新上传", (ROOT / "README.md").read_text())
        self.assertNotIn("local-cache-quota", html)
        self.assertNotIn("100MiB", html)
