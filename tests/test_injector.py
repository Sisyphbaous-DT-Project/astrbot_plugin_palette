"""`palette.injector` Dashboard 目标选择与注入行为的回归测试。

通过 mock 模块级兼容符号模拟 4.26.x / 4.27.x 环境，不依赖真实 Dashboard
文件，不写入仓库目录，也不在系统临时目录或 `sys.modules` 中留下产物。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_ASTRBOT_PATH_MODULE = "astrbot.core.utils.astrbot_path"


_MISSING = object()


def _snapshot_palette_modules() -> dict[str, object]:
    """记录导入前 palette 相关模块缓存与包属性，供导入后精确清理。"""

    package = sys.modules.get("palette")
    return {
        "palette.injector": sys.modules.get("palette.injector", _MISSING),
        "palette.paths": sys.modules.get("palette.paths", _MISSING),
        "injector_attr": (
            package.__dict__.get("injector", _MISSING)
            if package is not None
            else _MISSING
        ),
        "paths_attr": (
            package.__dict__.get("paths", _MISSING)
            if package is not None
            else _MISSING
        ),
    }


def _drop_new_palette_modules(before: dict[str, object]) -> None:
    """移除本次 stub 导入新增的 palette 模块缓存。

    只清理快照之后新出现的模块对象与包属性；导入前已存在的缓存（可能由
    其他用例创建）原样保留。
    """

    for name in ("palette.injector", "palette.paths"):
        current = sys.modules.get(name, _MISSING)
        if current is not _MISSING and current is not before[name]:
            sys.modules.pop(name, None)
    package = sys.modules.get("palette")
    if package is not None:
        for attr, key in (("injector", "injector_attr"), ("paths", "paths_attr")):
            current = package.__dict__.get(attr, _MISSING)
            if current is not _MISSING and current is not before[key]:
                package.__dict__.pop(attr, None)


def _import_injector():
    """导入被测模块。

    缺少真实 AstrBot 时，只在导入期间临时 stub 路径模块，导入完成后恢复
    `sys.modules`，并按导入前快照移除本次新增的 `palette.paths` /
    `palette.injector` 模块缓存：同进程后续导入会得到全新模块（有真实
    AstrBot 时即真实实现，没有则正常 ImportError），不会复用占位函数；
    导入前已存在的其他缓存原样保留。本测试模块继续通过局部引用使用被测
    对象。stub 函数在测试中不会被调用（路径由 `_FakePaths` 提供），返回
    占位字符串，不创建任何临时目录。
    """

    try:
        import astrbot.core.utils.astrbot_path  # noqa: F401
    except ImportError:
        stub = types.ModuleType(_ASTRBOT_PATH_MODULE)
        stub.get_astrbot_data_path = lambda: ""
        stub.get_astrbot_plugin_data_path = lambda: ""
        had_original = _ASTRBOT_PATH_MODULE in sys.modules
        original = sys.modules.get(_ASTRBOT_PATH_MODULE)
        sys.modules[_ASTRBOT_PATH_MODULE] = stub
        before = _snapshot_palette_modules()
        try:
            from palette import injector as module
        finally:
            if had_original:
                sys.modules[_ASTRBOT_PATH_MODULE] = original
            else:
                sys.modules.pop(_ASTRBOT_PATH_MODULE, None)
            _drop_new_palette_modules(before)
    else:
        from palette import injector as module
    return module


injector = _import_injector()
from palette.constants import (  # noqa: E402
    INJECTION_END_MARKER,
    INJECTION_START_MARKER,
)

_INDEX_HTML = (
    "<!DOCTYPE html>\n<html>\n<head>\n<title>t</title>\n</head>\n"
    "<body></body>\n</html>\n"
)


class _FakePaths:
    """与 `PalettePaths` 对齐的轻量路径 stub，全部落在临时目录。"""

    def __init__(self, root: Path) -> None:
        self.data_root = root / "data"
        self.plugin_data_dir = root / "plugin"
        self.background_dir = self.plugin_data_dir / "backgrounds"
        self.thumbnail_dir = self.plugin_data_dir / "thumbnails"
        self.patch_backup_dir = self.plugin_data_dir / "dashboard_backups"
        self.user_dashboard_dist = self.data_root / "dist"

    def ensure_runtime_dirs(self) -> None:
        self.patch_backup_dir.mkdir(parents=True, exist_ok=True)


class InjectorDashboardTargetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="palette-injector-case-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paths = _FakePaths(self.root)
        injector._PREPARED_FALLBACK_DISTS.clear()
        self.addCleanup(injector._PREPARED_FALLBACK_DISTS.clear)

    def _make_dist(self, name: str) -> Path:
        dist = self.root / name
        dist.mkdir(parents=True, exist_ok=True)
        (dist / "index.html").write_text(_INDEX_HTML, encoding="utf-8")
        return dist

    def _simulate(
        self,
        *,
        version: str = "4.27.1",
        resolver=None,
        bundled_getter=None,
        is_compatible=None,
        should_use_bundled=None,
    ):
        """mock 模块级兼容符号，模拟指定 AstrBot 版本的导入结果。"""

        return mock.patch.multiple(
            injector,
            ASTRBOT_VERSION=version,
            resolve_dashboard_dist=resolver,
            get_bundled_dashboard_dist_path=bundled_getter,
            is_dashboard_dist_compatible=is_compatible,
            should_use_bundled_dashboard_dist=should_use_bundled,
        )

    def test_public_resolver_selects_bundled_dist(self) -> None:
        """4.27.x：新解析器可用、旧函数缺失时选择解析器返回的内置目录。"""

        bundled = self._make_dist("bundled")
        with self._simulate(resolver=lambda: bundled):
            target = injector._resolve_dashboard_target(
                self.paths, allow_copy_fallback=False
            )
        self.assertEqual(target.dist, bundled)
        self.assertEqual(target.source, "bundled")
        self.assertIsNone(target.compatible)

    def test_legacy_helpers_select_bundled_dist(self) -> None:
        """4.26.x：新解析器缺失、旧函数可用时旧逻辑仍选择内置目录。"""

        bundled = self._make_dist("bundled")
        self._make_dist("data/dist")
        with self._simulate(
            version="4.26.7",
            bundled_getter=lambda: str(bundled),
            is_compatible=lambda dist, version: False,
            should_use_bundled=lambda user, version: True,
        ):
            target = injector._resolve_dashboard_target(
                self.paths, allow_copy_fallback=False
            )
        self.assertEqual(target.dist, bundled)
        self.assertEqual(target.source, "bundled")

    def test_custom_webui_dir_takes_priority(self) -> None:
        """自定义 --webui-dir 优先于新解析器和旧逻辑。"""

        custom = self._make_dist("custom")
        bundled = self._make_dist("bundled")
        argv = ["main.py", "--webui-dir", str(custom)]
        with (
            self._simulate(resolver=lambda: bundled),
            mock.patch.object(sys, "argv", argv),
        ):
            target = injector._resolve_dashboard_target(
                self.paths, allow_copy_fallback=False
            )
        self.assertEqual(target.source, "custom")
        self.assertEqual(target.dist, custom.resolve())

    def test_public_resolver_data_dist_source(self) -> None:
        """新解析器返回 data/dist 时状态来源为 data/dist。"""

        user_dist = self._make_dist("data/dist")
        with self._simulate(resolver=lambda: str(user_dist)):
            target = injector._resolve_dashboard_target(
                self.paths, allow_copy_fallback=False
            )
        self.assertEqual(target.source, "data/dist")
        self.assertEqual(target.dist, user_dist)

    def test_public_resolver_none_falls_back_to_legacy(self) -> None:
        """新解析器返回 None 时安全回退旧逻辑。"""

        bundled = self._make_dist("bundled")
        self._make_dist("data/dist")
        with self._simulate(
            version="4.26.7",
            resolver=lambda: None,
            bundled_getter=lambda: str(bundled),
            is_compatible=lambda dist, version: False,
            should_use_bundled=lambda user, version: True,
        ):
            target = injector._resolve_dashboard_target(
                self.paths, allow_copy_fallback=False
            )
        self.assertEqual(target.dist, bundled)
        self.assertEqual(target.source, "bundled")

    def test_public_resolver_error_falls_back_to_legacy(self) -> None:
        """新解析器抛异常时安全回退旧逻辑。"""

        def broken_resolver():
            raise RuntimeError("boom")

        bundled = self._make_dist("bundled")
        self._make_dist("data/dist")
        with self._simulate(
            version="4.26.7",
            resolver=broken_resolver,
            bundled_getter=lambda: str(bundled),
            is_compatible=lambda dist, version: False,
            should_use_bundled=lambda user, version: True,
        ):
            target = injector._resolve_dashboard_target(
                self.paths, allow_copy_fallback=False
            )
        self.assertEqual(target.dist, bundled)
        self.assertEqual(target.source, "bundled")

    def test_missing_target_reports_unsupported_without_writes(self) -> None:
        """目标目录不存在时不误报已注入，也不创建无关 Dashboard 文件。"""

        with self._simulate():
            status = injector.ensure_dashboard_injection(self.paths)
        self.assertFalse(status.supported)
        self.assertFalse(status.patched)
        self.assertFalse(status.index_exists)
        self.assertFalse(self.paths.data_root.exists())

    def test_repeated_injection_keeps_single_marker_block(self) -> None:
        """重复注入不产生多组标记，内容在首次缩进规整后收敛。"""

        user_dist = self.root / "data/dist"
        user_dist.mkdir(parents=True)
        # 真实 Dashboard 的 </head> 通常带缩进
        index = user_dist / "index.html"
        index.write_text(
            _INDEX_HTML.replace("</head>", "  </head>"), encoding="utf-8"
        )

        contents = []
        with self._simulate(resolver=lambda: user_dist):
            for _ in range(3):
                status = injector.ensure_dashboard_injection(self.paths)
                self.assertTrue(status.patched)
                contents.append(index.read_text(encoding="utf-8"))

        for content in contents:
            self.assertEqual(content.count(INJECTION_START_MARKER), 1)
            self.assertEqual(content.count(INJECTION_END_MARKER), 1)
        # 首次注入沿用 </head> 原有缩进，第二次完成缩进规整，之后收敛不再变化
        self.assertEqual(contents[1], contents[2])

    def test_incomplete_markers_reject_write(self) -> None:
        """只有开始或结束标记时拒绝写入，文件内容保持不变。"""

        user_dist = self._make_dist("data/dist")
        index = user_dist / "index.html"
        broken = _INDEX_HTML.replace(
            "</head>", f"  {INJECTION_START_MARKER}\n</head>"
        )
        index.write_text(broken, encoding="utf-8")
        with self._simulate(resolver=lambda: user_dist):
            status = injector.ensure_dashboard_injection(self.paths)
        self.assertFalse(status.supported)
        self.assertFalse(status.patched)
        self.assertIn("不完整", status.message)
        self.assertEqual(index.read_text(encoding="utf-8"), broken)

    def test_bundled_write_failure_prepares_data_dist_fallback(self) -> None:
        """内置目录写入失败时进入 data/dist 复制回退并写重启标记。"""

        bundled = self._make_dist("bundled")
        real_replace = Path.replace

        def flaky_replace(this, target):
            if str(target).startswith(str(bundled)):
                raise OSError("read-only filesystem")
            return real_replace(this, target)

        with (
            self._simulate(resolver=lambda: bundled),
            mock.patch.object(Path, "replace", flaky_replace),
        ):
            status = injector.ensure_dashboard_injection(self.paths)

        self.assertTrue(status.patched)
        self.assertTrue(status.restart_required)
        self.assertEqual(status.target_source, "data/dist")
        marker = self.paths.user_dashboard_dist / injector._FALLBACK_RESTART_MARKER
        self.assertTrue(marker.is_file())
        content = (self.paths.user_dashboard_dist / "index.html").read_text(
            encoding="utf-8"
        )
        self.assertEqual(content.count(INJECTION_START_MARKER), 1)

    def test_fallback_stays_stable_when_resolver_switches(self) -> None:
        """复制回退后解析器切换到 data/dist，重复调用状态保持稳定。"""

        bundled = self._make_dist("bundled")
        user_dist = self.paths.user_dashboard_dist
        real_replace = Path.replace

        def flaky_replace(this, target):
            if str(target).startswith(str(bundled)):
                raise OSError("read-only filesystem")
            return real_replace(this, target)

        def switching_resolver():
            # 复制完成后，AstrBot 解析器会改为选择 data/dist
            return user_dist if user_dist.exists() else bundled

        with (
            self._simulate(resolver=switching_resolver),
            mock.patch.object(Path, "replace", flaky_replace),
        ):
            first = injector.ensure_dashboard_injection(self.paths)
            second = injector.ensure_dashboard_injection(self.paths)
            inspect = injector.inspect_injection(self.paths)
            marker = user_dist / injector._FALLBACK_RESTART_MARKER

        # 只读检测也不得吞掉待重启状态：三种调用结论一致，标记保留
        for status in (first, second, inspect):
            self.assertTrue(status.patched)
            self.assertTrue(status.restart_required)
            self.assertEqual(status.target_source, "data/dist")
        self.assertTrue(marker.is_file())
        content = (user_dist / "index.html").read_text(encoding="utf-8")
        self.assertEqual(content.count(INJECTION_START_MARKER), 1)
        self.assertEqual(content.count(INJECTION_END_MARKER), 1)


_ENV_427 = '''
_mod("astrbot.core.config.default", VERSION="4.27.1-fake")
_mod("astrbot.core.dashboard_assets", resolve_dashboard_dist=lambda: None)
_mod("astrbot.core.utils.io")  # 4.27.x：旧函数已从此模块移除
_mod(
    "astrbot.core.utils.astrbot_path",
    get_astrbot_data_path=lambda: "",
    get_astrbot_plugin_data_path=lambda: "",
)

from palette import injector

assert injector.ASTRBOT_VERSION == "4.27.1-fake", injector.ASTRBOT_VERSION
assert injector.resolve_dashboard_dist is not None
assert injector.get_bundled_dashboard_dist_path is None
assert injector.is_dashboard_dist_compatible is None
assert injector.should_use_bundled_dashboard_dist is None
'''

_ENV_426 = '''
_mod("astrbot.core.config.default", VERSION="4.26.7-fake")
_mod(
    "astrbot.core.utils.io",
    get_bundled_dashboard_dist_path=lambda: "/bundled",
    is_dashboard_dist_compatible=lambda dist, version: True,
    should_use_bundled_dashboard_dist=lambda user, version: False,
)
_mod(
    "astrbot.core.utils.astrbot_path",
    get_astrbot_data_path=lambda: "",
    get_astrbot_plugin_data_path=lambda: "",
)

from palette import injector

assert injector.ASTRBOT_VERSION == "4.26.7-fake", injector.ASTRBOT_VERSION
assert injector.resolve_dashboard_dist is None
assert injector.get_bundled_dashboard_dist_path is not None
assert injector.is_dashboard_dist_compatible is not None
assert injector.should_use_bundled_dashboard_dist is not None
'''


class InjectorRealImportTest(unittest.TestCase):
    """真实导入路径的隔离验证。

    在干净子进程中构造不同 AstrBot 模块组合后真实导入 `palette.injector`，
    断言三组兼容导入互不影响，防止导入结构回归（例如三组导入被重新合并
    为同一个 `try` 后，旧函数缺失连带清空 AstrBot 版本号）。
    """

    def _run_fresh_import(self, env_setup: str) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        script = (
            "import sys, types\n"
            f"sys.path.insert(0, {json.dumps(str(repo_root))})\n"
            "def _mod(name, **attrs):\n"
            "    module = types.ModuleType(name)\n"
            "    for key, value in attrs.items():\n"
            "        setattr(module, key, value)\n"
            "    sys.modules[name] = module\n"
            + env_setup
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            self.fail(
                "子进程导入验证失败：\n" + result.stdout + result.stderr
            )

    def test_427_env_keeps_version_and_public_resolver(self) -> None:
        """4.27.x：旧函数缺失时版本号保留、公开解析器可用。"""

        self._run_fresh_import(_ENV_427)

    def test_426_env_keeps_legacy_helpers(self) -> None:
        """4.26.x：公开解析器缺失时版本号保留、旧版函数可用。"""

        self._run_fresh_import(_ENV_426)


if __name__ == "__main__":
    unittest.main()
