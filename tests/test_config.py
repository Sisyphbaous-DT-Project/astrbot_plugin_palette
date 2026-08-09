"""定时轮换后端配置与 random-select 接口回归测试。

stub `astrbot.api.star` / `astrbot.api.web` / `astrbot.core.utils.astrbot_path`
后以包形式导入 `astrbot_plugin_palette.main`；stub 路径函数读取可变单元，
让每个用例的 `PalettePaths` 都指向自己的系统临时目录，不在仓库写文件。
导入完成后按快照恢复 `sys.modules` 并移除本次新增的模块缓存。
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT.parent))

_STUBBED_MODULES = (
    "astrbot",
    "astrbot.api",
    "astrbot.api.star",
    "astrbot.api.web",
    "astrbot.core",
    "astrbot.core.utils",
    "astrbot.core.utils.astrbot_path",
)

# stub 路径函数读取该单元，测试用例按需指向自己的临时目录。
_PATHS_CELL = {"data": "", "plugin": ""}


def _json_response(data=None, *, status_code=200, headers=None):
    return {"status_code": status_code, "body": {} if data is None else data}


def _error_response(message, *, status_code=400, data=None, headers=None):
    return {
        "status_code": status_code,
        "error": True,
        "message": message,
        "body": {} if data is None else data,
    }


def _build_stub_modules() -> dict[str, types.ModuleType]:
    modules = {name: types.ModuleType(name) for name in _STUBBED_MODULES}

    star = modules["astrbot.api.star"]

    class _Context:  # noqa: D401 - 仅占位
        pass

    class _Star:
        def __init__(self, context) -> None:
            self.context = context

    def _register(*args, **kwargs):
        return lambda cls: cls

    star.Context = _Context
    star.Star = _Star
    star.register = _register

    web = modules["astrbot.api.web"]
    web.json_response = _json_response
    web.error_response = _error_response
    web.file_response = lambda *args, **kwargs: None
    web.stream_response = lambda *args, **kwargs: None
    web.request = None

    paths = modules["astrbot.core.utils.astrbot_path"]
    paths.get_astrbot_data_path = lambda: _PATHS_CELL["data"]
    paths.get_astrbot_plugin_data_path = lambda: _PATHS_CELL["plugin"]
    return modules


def _import_main():
    """导入被测模块，导入后恢复 sys.modules 并清理新增缓存。"""

    before = {name: sys.modules.get(name) for name in _STUBBED_MODULES}
    before.update(
        {
            name: sys.modules.get(name)
            for name in sys.modules
            if name == "astrbot_plugin_palette" or name.startswith("astrbot_plugin_palette.")
        }
    )
    stubs = _build_stub_modules()
    sys.modules.update(stubs)
    try:
        import astrbot_plugin_palette.main as module
    finally:
        for name in _STUBBED_MODULES:
            if before[name] is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = before[name]
        for name in list(sys.modules):
            if name == "astrbot_plugin_palette" or name.startswith(
                "astrbot_plugin_palette."
            ):
                if before.get(name) is None:
                    sys.modules.pop(name, None)
    return module


main = _import_main()


class _FakeRequest:
    def __init__(self, payload) -> None:
        self._payload = payload

    async def json(self, default=None):
        return self._payload


class _FakeThemeColors:
    def to_dict(self) -> dict[str, str]:
        return {"theme_primary": "#112233", "theme_secondary": "#445566"}


class PalettePluginTestCase(unittest.TestCase):
    """每个用例使用独立的临时目录与配置。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        _PATHS_CELL["data"] = str(root / "data")
        _PATHS_CELL["plugin"] = str(root / "plugins")
        self.background_dir = root / "plugins" / "astrbot_plugin_palette" / "backgrounds"
        self.background_dir.mkdir(parents=True, exist_ok=True)

    def _make_plugin(self, config: dict, files: tuple[str, ...] = ()):
        for filename in files:
            (self.background_dir / filename).write_bytes(b"\xff\xd8\xff")
        context = types.SimpleNamespace(register_web_api=lambda *args, **kwargs: None)
        with (
            mock.patch.object(main, "ensure_dashboard_injection", lambda paths: {}),
            mock.patch.object(
                main, "extract_theme_colors", lambda path: _FakeThemeColors()
            ),
        ):
            plugin = main.PalettePlugin(context, config)
        return plugin

    def _run_random_select(self, plugin, payload):
        request = _FakeRequest(payload)
        with (
            mock.patch.object(main, "request", request),
            mock.patch.object(
                main, "extract_theme_colors", lambda path: _FakeThemeColors()
            ),
        ):
            return asyncio.run(plugin.random_select_background())


class RotationConfigDefaultsTest(PalettePluginTestCase):
    def test_legacy_config_uses_defaults(self) -> None:
        plugin = self._make_plugin({})
        public = plugin._public_config()
        self.assertIs(public["background_rotation_enabled"], False)
        self.assertEqual(public["background_rotation_interval_minutes"], 30)

    def test_normalize_interval_clamps_and_defaults(self) -> None:
        normalize = main.PalettePlugin._normalize_rotation_interval
        self.assertEqual(normalize(0), 1)
        self.assertEqual(normalize(-5), 1)
        self.assertEqual(normalize(9999), 1440)
        self.assertEqual(normalize(1440), 1440)
        self.assertEqual(normalize(45), 45)
        self.assertEqual(normalize("60"), 60)
        self.assertEqual(normalize("abc"), 30)
        self.assertEqual(normalize(None), 30)
        self.assertEqual(normalize(True), 30)
        self.assertEqual(normalize(45.9), 45)

    def test_normalize_config_applies_new_fields(self) -> None:
        plugin = self._make_plugin({})
        normalized = plugin._normalize_config(
            {
                "background_rotation_enabled": "on",
                "background_rotation_interval_minutes": 0,
            }
        )
        self.assertIs(normalized["background_rotation_enabled"], True)
        self.assertEqual(normalized["background_rotation_interval_minutes"], 1)

        normalized = plugin._normalize_config({})
        self.assertIs(normalized["background_rotation_enabled"], False)
        self.assertEqual(normalized["background_rotation_interval_minutes"], 30)

    def test_public_config_normalizes_native_out_of_range_interval(self) -> None:
        # 原生配置入口可绕过设置页写入越界值（AstrBot 渲染器不读取
        # minimum/maximum）；公开配置必须与运行时夹取口径一致，
        # 避免设置页显示“每 0 分钟”而运行时实际按 1 分钟执行。
        plugin = self._make_plugin({"background_rotation_interval_minutes": 0})
        public = plugin._public_config()
        self.assertEqual(public["background_rotation_interval_minutes"], 1)
        plugin = self._make_plugin({"background_rotation_interval_minutes": 99999})
        public = plugin._public_config()
        self.assertEqual(public["background_rotation_interval_minutes"], 1440)
        plugin = self._make_plugin({"background_rotation_interval_minutes": "abc"})
        public = plugin._public_config()
        self.assertEqual(public["background_rotation_interval_minutes"], 30)

    def test_new_fields_preserve_existing_background_fields(self) -> None:
        config = {
            "background_image": "legacy.jpg",
            "background_images": ["legacy.jpg"],
            "landscape_background_image": "wide.jpg",
            "landscape_background_images": ["wide.jpg"],
            "portrait_background_image": "tall.jpg",
            "portrait_background_images": ["tall.jpg"],
            "background_rotation_enabled": True,
            "background_rotation_interval_minutes": 15,
        }
        plugin = self._make_plugin(
            config, files=("legacy.jpg", "wide.jpg", "tall.jpg")
        )
        normalized = plugin._normalize_config(plugin._public_config())
        self.assertEqual(normalized["background_images"], ["legacy.jpg"])
        self.assertEqual(normalized["landscape_background_images"], ["wide.jpg"])
        self.assertEqual(normalized["portrait_background_images"], ["tall.jpg"])
        self.assertIs(normalized["background_rotation_enabled"], True)
        self.assertEqual(normalized["background_rotation_interval_minutes"], 15)


class RandomBackgroundPoolTest(PalettePluginTestCase):
    def test_orientation_priority_order(self) -> None:
        plugin = self._make_plugin({})
        config = {
            "background_image": "legacy.jpg",
            "background_images": ["legacy.jpg"],
            "landscape_background_image": "wide.jpg",
            "landscape_background_images": ["wide.jpg"],
            "portrait_background_image": "tall.jpg",
            "portrait_background_images": ["tall.jpg"],
        }
        pool, current, images = plugin._random_background_pool(config, "landscape")
        self.assertEqual((pool, current, images), ("landscape", "wide.jpg", ["wide.jpg"]))
        pool, current, images = plugin._random_background_pool(config, "portrait")
        self.assertEqual((pool, current, images), ("portrait", "tall.jpg", ["tall.jpg"]))
        pool, current, images = plugin._random_background_pool(config, "legacy")
        self.assertEqual((pool, current, images), ("legacy", "legacy.jpg", ["legacy.jpg"]))

    def test_orientation_falls_back_to_next_non_empty_pool(self) -> None:
        plugin = self._make_plugin({})
        config = {
            "background_image": "",
            "background_images": [],
            "landscape_background_image": "",
            "landscape_background_images": [],
            "portrait_background_image": "tall.jpg",
            "portrait_background_images": ["tall.jpg"],
        }
        pool, current, _ = plugin._random_background_pool(config, "landscape")
        self.assertEqual((pool, current), ("portrait", "tall.jpg"))

        with self.assertRaises(ValueError):
            plugin._random_background_pool(
                {
                    "background_images": [],
                    "landscape_background_images": [],
                    "portrait_background_images": [],
                },
                "landscape",
            )


class ScheduledRandomSelectTest(PalettePluginTestCase):
    def _enabled_config(self, **overrides) -> dict:
        config = {
            "enabled": True,
            "background_rotation_enabled": True,
            "background_rotation_interval_minutes": 10,
            "landscape_background_image": "a.jpg",
            "landscape_background_images": ["a.jpg", "b.jpg"],
        }
        config.update(overrides)
        return config

    def test_scheduled_rotation_switches_and_saves(self) -> None:
        config = self._enabled_config()
        plugin = self._make_plugin(config, files=("a.jpg", "b.jpg"))
        response = self._run_random_select(
            plugin, {"orientation": "landscape", "scheduled": True}
        )
        self.assertEqual(response["status_code"], 200)
        self.assertEqual(response["body"]["orientation"], "landscape")
        # 候选排除当前图，唯一候选是 b.jpg，必须写回配置。
        self.assertEqual(config["landscape_background_image"], "b.jpg")
        self.assertEqual(response["body"]["config"]["theme_primary"], "#112233")

    def test_scheduled_rotation_disabled_is_silent_noop(self) -> None:
        config = self._enabled_config(background_rotation_enabled=False)
        plugin = self._make_plugin(config, files=("a.jpg", "b.jpg"))
        response = self._run_random_select(
            plugin, {"orientation": "landscape", "scheduled": True}
        )
        self.assertEqual(response["status_code"], 200)
        self.assertNotIn("orientation", response["body"])
        self.assertEqual(config["landscape_background_image"], "a.jpg")

    def test_scheduled_plugin_disabled_is_silent_noop(self) -> None:
        config = self._enabled_config(enabled=False)
        plugin = self._make_plugin(config, files=("a.jpg", "b.jpg"))
        response = self._run_random_select(
            plugin, {"orientation": "landscape", "scheduled": True}
        )
        self.assertEqual(response["status_code"], 200)
        self.assertNotIn("orientation", response["body"])
        self.assertEqual(config["landscape_background_image"], "a.jpg")

    def test_scheduled_single_image_is_noop(self) -> None:
        config = self._enabled_config(landscape_background_images=["a.jpg"])
        plugin = self._make_plugin(config, files=("a.jpg",))
        response = self._run_random_select(
            plugin, {"orientation": "landscape", "scheduled": True}
        )
        self.assertEqual(response["status_code"], 200)
        self.assertIn("无需随机切换", response["body"]["message"])
        self.assertEqual(config["landscape_background_image"], "a.jpg")

    def test_scheduled_empty_gallery_is_silent_noop(self) -> None:
        config = self._enabled_config(
            landscape_background_image="", landscape_background_images=[]
        )
        plugin = self._make_plugin(config)
        response = self._run_random_select(
            plugin, {"orientation": "landscape", "scheduled": True}
        )
        self.assertEqual(response["status_code"], 200)
        self.assertNotIn("orientation", response["body"])

    def test_manual_random_ignores_rotation_switch(self) -> None:
        # 手动随机（无 scheduled）不受新开关影响，保持既有语义。
        config = self._enabled_config(background_rotation_enabled=False)
        plugin = self._make_plugin(config, files=("a.jpg", "b.jpg"))
        response = self._run_random_select(plugin, {"orientation": "landscape"})
        self.assertEqual(response["status_code"], 200)
        self.assertEqual(response["body"]["orientation"], "landscape")
        self.assertEqual(config["landscape_background_image"], "b.jpg")

    def test_manual_empty_gallery_still_errors(self) -> None:
        config = self._enabled_config(
            landscape_background_image="", landscape_background_images=[]
        )
        plugin = self._make_plugin(config)
        response = self._run_random_select(plugin, {"orientation": "landscape"})
        self.assertTrue(response.get("error"))
        self.assertEqual(response["status_code"], 400)


if __name__ == "__main__":
    unittest.main()
