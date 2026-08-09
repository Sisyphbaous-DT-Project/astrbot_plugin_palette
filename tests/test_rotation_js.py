"""`palette.injector` 内嵌 bootstrap JS 的语法与定时轮换结构回归测试。

bootstrap 脚本是以 f-string 形式内嵌在 Python 源码中的前端 JS，仓库的
`node --check` 只覆盖 `pages/settings/`，无法发现注入脚本自身的语法错误。
本测试把 `_build_bootstrap_script` 的输出写到系统临时文件后用子进程执行
`node --check`，并对定时轮换（领导权、跨标签同步、递归计时器、有界缓存）
所需的关键结构做静态断言，防止后续改动静默丢失这些机制。

临时文件只落在系统临时目录，不在仓库留下产物。
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_ASTRBOT_PATH_MODULE = "astrbot.core.utils.astrbot_path"


def _import_injector():
    """与 tests/test_injector.py 相同的最小 stub 导入。"""

    try:
        import astrbot.core.utils.astrbot_path  # noqa: F401
    except ImportError:
        stub = types.ModuleType(_ASTRBOT_PATH_MODULE)
        stub.get_astrbot_data_path = lambda: ""
        stub.get_astrbot_plugin_data_path = lambda: ""
        had_original = _ASTRBOT_PATH_MODULE in sys.modules
        original = sys.modules.get(_ASTRBOT_PATH_MODULE)
        sys.modules[_ASTRBOT_PATH_MODULE] = stub
        try:
            from palette import injector as module
        finally:
            if had_original:
                sys.modules[_ASTRBOT_PATH_MODULE] = original
            else:
                sys.modules.pop(_ASTRBOT_PATH_MODULE, None)
    else:
        from palette import injector as module
    return module


injector = _import_injector()

_SCRIPT = injector._build_bootstrap_script(
    "/api/v1/plugins/extensions/astrbot_plugin_palette/config",
    "/api/v1/plugins/extensions/astrbot_plugin_palette/backgrounds/random-select",
    "/api/v1/plugins/extensions/astrbot_plugin_palette/theme",
    "/api/v1/plugins/extensions/astrbot_plugin_palette/token-stats",
)


class BootstrapScriptSyntaxTest(unittest.TestCase):
    """注入脚本必须通过 node --check，语法错误直接失败。"""

    def test_bootstrap_script_passes_node_check(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", encoding="utf-8", delete=False
        ) as handle:
            handle.write(_SCRIPT)
            script_path = Path(handle.name)
        try:
            result = subprocess.run(
                ["node", "--check", str(script_path)],
                capture_output=True,
                text=True,
                timeout=60,
            )
        finally:
            script_path.unlink(missing_ok=True)
        self.assertEqual(
            result.returncode,
            0,
            f"node --check 失败：\n{result.stderr}",
        )


class BootstrapRotationStructureTest(unittest.TestCase):
    """定时轮换机制的静态结构断言。"""

    def test_rotation_leadership_channel(self) -> None:
        self.assertIn("astrbot-palette-background-rotation-leader", _SCRIPT)
        self.assertIn("navigator.locks", _SCRIPT)

    def test_rotation_lease_fallback(self) -> None:
        self.assertIn("astrbot_palette_rotation_lease", _SCRIPT)
        self.assertIn("expiresAt", _SCRIPT)

    def test_cross_tab_sync_channel(self) -> None:
        self.assertIn("astrbot-palette-sync", _SCRIPT)
        self.assertIn("BroadcastChannel", _SCRIPT)
        self.assertIn("astrbot_palette_sync_event", _SCRIPT)

    def test_rotation_timer_is_recursive_timeout(self) -> None:
        self.assertIn("scheduleRotation", _SCRIPT)
        self.assertIn("clearTimeout(rotationTimer)", _SCRIPT)
        self.assertNotIn("rotationTimer = setInterval", _SCRIPT)

    def test_rotation_visibility_lifecycle(self) -> None:
        self.assertIn("stopRotation", _SCRIPT)
        self.assertIn("releaseLeadership", _SCRIPT)
        self.assertIn("visibilitychange", _SCRIPT)

    def test_bounded_object_url_cache(self) -> None:
        self.assertIn("MAX_BACKGROUND_OBJECT_URLS", _SCRIPT)
        self.assertIn("evictObjectUrlCache", _SCRIPT)

    def test_scheduled_request_flag(self) -> None:
        self.assertIn("scheduled", _SCRIPT)
        self.assertIn("rotationInFlight", _SCRIPT)


class BootstrapRotationConcurrencyTest(unittest.TestCase):
    """轮换并发互斥、降级与缓存保护修复的结构断言。"""

    def test_rotation_shares_loading_mutex_with_refresh(self) -> None:
        # 轮换与普通刷新共用同一把 loading 锁，释放统一走重放出口。
        self.assertIn("loading = true;\n      rotationInFlight = true;", _SCRIPT)
        self.assertIn("function releaseLoadingAndReplay()", _SCRIPT)
        after_tick = _SCRIPT.rsplit("rotationInFlight = false;", 1)[1]
        self.assertIn("releaseLoadingAndReplay();", after_tick[:200])

    def test_pending_refresh_merges_options(self) -> None:
        # 忙碌窗口的待处理刷新必须累积合并 options，动画不得退化为硬切。
        self.assertIn("function mergeRefreshOptions(base, extra)", _SCRIPT)
        self.assertIn("pendingRefreshOptions = mergeRefreshOptions(", _SCRIPT)
        self.assertIn("refreshPalette(replay);", _SCRIPT)
        self.assertNotIn("pendingRefresh = true", _SCRIPT)

    def test_refresh_reschedules_only_on_relevant_change(self) -> None:
        # 普通刷新不得无条件重排轮换计时；开关/间隔/当前背景变化才重排。
        self.assertIn("function rotationScheduleNeedsSync(previous, next)", _SCRIPT)
        self.assertIn(
            "scheduleSyncNeeded = rotationScheduleNeedsSync(previousConfig, config)",
            _SCRIPT,
        )

    def test_lock_async_failure_falls_back_to_lease(self) -> None:
        # Web Locks 异步失败校验身份后清空状态并降级 localStorage 租约。
        catch_block = _SCRIPT.split("定时轮换领导锁异常", 1)[1]
        self.assertIn("rotationLeadership === leadership", catch_block)
        self.assertIn("rotationLeadership = null;", catch_block)
        self.assertIn("acquireLeaseLeadership();", catch_block)

    def test_object_url_protection_is_reference_counted(self) -> None:
        # 在途/在用保护改为引用计数；图层引用按图层配平。
        self.assertIn("(backgroundInFlightObjectUrls[objectUrl] || 0) + 1", _SCRIPT)
        self.assertIn("inFlightCount > 1", _SCRIPT)
        self.assertIn("(backgroundInUseObjectUrls[objectUrl] || 0) + 1", _SCRIPT)
        self.assertIn("inUseCount > 1", _SCRIPT)
        self.assertIn("layer.__paletteObjectUrl !== nextUrl", _SCRIPT)


def _function_body(signature: str) -> str:
    """按签名截取顶层函数体（脚本内顶层函数以 4 空格缩进闭合）。"""

    match = re.search(
        re.escape(signature) + r"\s*\{\n(?P<body>.*?)\n    \}",
        _SCRIPT,
        re.S,
    )
    if not match:
        raise AssertionError(f"未找到函数：{signature}")
    return match.group("body")


# `unmark...(` 本身包含子串 `mark...(`，统计 mark 调用时需排除。
_MARK_IN_FLIGHT = re.compile(r"(?<!un)markObjectUrlInFlight\(")
_UNMARK_IN_FLIGHT = re.compile(r"unmarkObjectUrlInFlight\(")


class BootstrapRuntimeBalanceTest(unittest.TestCase):
    """引用计数与运行时行为的结构性断言（防止配平再次被改坏）。"""

    def test_inflight_marks_are_balanced(self) -> None:
        # fetchBackground 成功返回时持有标记并移交调用方：初始命中、blob 后
        # 胜出、新建三条路径各标一次，函数内部不得解除（解除责任在调用方）。
        fetch_body = _function_body("async function fetchBackground(url, token)")
        self.assertEqual(len(_MARK_IN_FLIGHT.findall(fetch_body)), 3)
        self.assertEqual(len(_UNMARK_IN_FLIGHT.findall(fetch_body)), 0)

        # 并发同 URL：blob() 返回后必须复查缓存，已有胜出者直接复用，
        # 不得无条件覆盖 Map 造成孤儿 object URL。
        self.assertEqual(fetch_body.count("getCachedObjectUrl(url)"), 2)
        self.assertIn("winnerObjectUrl", fetch_body)

        # 调用方不再重复标记（避免微任务间隙的未保护窗口），finally 统一
        # 解除一次，任何出口都不残留计数。
        apply_body = _function_body(
            "async function applyDirectionalBackground(config, token, animate)"
        )
        self.assertEqual(len(_MARK_IN_FLIGHT.findall(apply_body)), 0)
        self.assertEqual(len(_UNMARK_IN_FLIGHT.findall(apply_body)), 1)
        self.assertIn("} finally {", apply_body)

    def test_refresh_updates_last_config_before_apply(self) -> None:
        # 调度以最新配置为准：GET 成功后、视觉应用前就更新 lastConfig，
        # 主题 CSS 失败也不能让轮换协调回退旧配置。
        body = _function_body("async function refreshPalette(options)")
        get_pos = body.index("resolveConfigForRefresh(")
        assign_pos = body.index("lastConfig = config;")
        apply_pos = body.index("applyResolvedConfig(")
        self.assertLess(get_pos, assign_pos)
        self.assertLess(assign_pos, apply_pos)

    def test_fetch_discards_after_cache_generation_change(self) -> None:
        # 禁用/卸载整体回收时递增缓存代数；fetchBackground 入口记录代数，
        # blob() 后校验在 createObjectURL 之前，过期请求不得回填缓存。
        revoke_body = _function_body("function revokeObjectUrls()")
        self.assertIn("backgroundCacheGeneration += 1", revoke_body)

        fetch_body = _function_body("async function fetchBackground(url, token)")
        capture_pos = fetch_body.index("requestGeneration = backgroundCacheGeneration")
        fetch_pos = fetch_body.index("await fetch(")
        check_pos = fetch_body.index(
            "requestGeneration !== backgroundCacheGeneration"
        )
        create_pos = fetch_body.index("URL.createObjectURL")
        self.assertLess(capture_pos, fetch_pos)
        self.assertLess(check_pos, create_pos)

    def test_refresh_reschedules_in_finally_regardless_of_apply(self) -> None:
        # 重排判定在配置 GET 成功后立即完成，在 finally 可靠出口执行，
        # 图片下载或落层失败不能跳过手动换图后的计时重排。
        body = _function_body("async function refreshPalette(options)")
        self.assertIn("scheduleSyncNeeded = rotationScheduleNeedsSync(", body)
        finally_part = body.rsplit("} finally {", 1)[1]
        self.assertIn("if (scheduleSyncNeeded) {", finally_part)
        self.assertIn("syncRotationSchedule();", finally_part)
        self.assertIn("releaseLoadingAndReplay();", finally_part)

    def test_next_background_frame_has_timeout_fallback(self) -> None:
        # 页面隐藏时 RAF 可能暂停，双帧等待必须有短超时兜底，否则轮换
        # in-flight 与 Web Lock 领导权无法释放。
        body = _function_body("function nextBackgroundFrame()")
        self.assertIn("requestAnimationFrame", body)
        self.assertIn("setTimeout(finish, 200)", body)

    def test_schedule_resyncs_on_manual_background_change(self) -> None:
        body = _function_body("function rotationScheduleNeedsSync(previous, next)")
        self.assertIn("background_image", body)
        self.assertIn("landscape_background_image", body)
        self.assertIn("portrait_background_image", body)

    def test_lease_renew_write_failure_releases_leadership(self) -> None:
        body = _function_body("function renewRotationLease(nonce)")
        self.assertIn("!renewed", body)
        self.assertIn("releaseLeadership", body)
        self.assertIn("scheduleLeaseRetry", body)


if __name__ == "__main__":
    unittest.main()
