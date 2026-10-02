"""大素材分块上传后端回归：会话、块边界、完成/取消竞态、过期与重启恢复。

复用 test_config 的 AstrBot stub 与临时 PalettePaths、test_media 的上传
辅助；通过插件真实 hooks 驱动 UploadManager，验证真实媒体保存与图库
合并，不只做函数名/路由字符串检查。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

from test_config import PalettePluginTestCase, _FakeRequest, main
from test_media import Upload, bundle, image_bytes

_FIXTURES = Path(__file__).with_name("fixtures")

USERNAME = "tester"
# stub 导入机制不允许二次 import 包，常量经模块命名空间获取。
_uploads_ns = main.UploadManager.__init__.__globals__
RECEIVING_IDLE_TTL = _uploads_ns["RECEIVING_IDLE_TTL_SECONDS"]
COMMITTED_RECEIPT_TTL = _uploads_ns["COMMITTED_RECEIPT_TTL_SECONDS"]


class ChunkedUploadTestCase(PalettePluginTestCase):
    def _make_manager(self, plugin, chunk_size=None):
        kwargs = {} if chunk_size is None else {"chunk_size": chunk_size}
        return main.UploadManager(
            plugin.paths,
            main.UploadHooks(
                save_material=plugin._save_material_with_id,
                commit_material=plugin._commit_prepared_background,
                build_result=plugin._build_upload_result,
                cleanup_candidate=plugin._cleanup_candidate_material,
                find_committed_material=plugin._find_committed_material,
            ),
            **kwargs,
        )

    def _init_payload(self, data, orientation="landscape", request_id="req-1"):
        return {
            "client_request_id": request_id,
            "orientation": orientation,
            "total_bytes": len(data),
            "filename": "sample.bin",
        }

    def _chunked_flow(
        self,
        manager,
        data,
        orientation="landscape",
        username=USERNAME,
        request_id="req-1",
    ):
        """完整走 init→逐块→complete→等待入库任务，返回会话。"""

        async def flow():
            init = await manager.init_session(
                username, self._init_payload(data, orientation, request_id)
            )
            upload_id = init["upload_id"]
            chunk_size = init["chunk_size"]
            for index in range((len(data) + chunk_size - 1) // chunk_size):
                chunk = data[index * chunk_size : (index + 1) * chunk_size]
                await manager.append_chunk(
                    username, upload_id, str(index), Upload(chunk)
                )
            await manager.complete(username, upload_id)
            session = manager._sessions[upload_id]
            if session.task is not None:
                await session.task
            return manager, session

        return asyncio.run(flow())

    @staticmethod
    def _run(coro):
        return asyncio.run(coro)


class UploadProtocolTest(ChunkedUploadTestCase):
    def test_declared_size_over_4gib_has_no_total_limit_or_preallocation(self):
        plugin = self._make_plugin({})
        payload = self._init_payload(b"x")
        payload["total_bytes"] = 5 * 1024**3
        receipt = self._run(plugin._uploads.init_session(USERNAME, payload))
        session = plugin._uploads._sessions[receipt["upload_id"]]
        self.assertEqual(session.total_bytes, payload["total_bytes"])
        self.assertEqual(session.payload_path.stat().st_size, 0)
        self.assertEqual(session.chunk_digests, [])

    def test_status_declares_chunked_protocol(self):
        plugin = self._make_plugin({})
        injection = types.SimpleNamespace(to_dict=lambda: {})
        with mock.patch.object(main, "ensure_dashboard_injection", lambda paths: injection):
            status = self._run(plugin.get_status())
        protocol = status["body"]["upload_protocol"]
        self.assertIs(protocol["chunked"], True)
        self.assertEqual(protocol["chunk_size"], 8 * 1024 * 1024)
        self.assertEqual(protocol["threshold"], 16 * 1024 * 1024)

    def test_routes_registered_with_path_params(self):
        routes = {}
        context = types.SimpleNamespace(
            register_web_api=lambda route, handler, methods, desc: routes.setdefault(
                (route, tuple(methods)), handler
            )
        )
        with mock.patch.object(main, "ensure_dashboard_injection", lambda paths: {}):
            main.PalettePlugin(context, {})
        prefix = "/astrbot_plugin_palette"
        for route, methods in (
            (f"{prefix}/uploads/init", ("POST",)),
            (f"{prefix}/uploads/<upload_id>/chunk/<index>", ("POST",)),
            (f"{prefix}/uploads/<upload_id>/status", ("GET",)),
            (f"{prefix}/uploads/<upload_id>/complete", ("POST",)),
            (f"{prefix}/uploads/<upload_id>/cancel", ("POST",)),
        ):
            self.assertIn((route, methods), routes, route)

    def test_init_route_uses_authenticated_username(self):
        plugin = self._make_plugin({})
        request = types.SimpleNamespace(
            username="alice",
            json=lambda default=None: asyncio.sleep(
                0, self._init_payload(image_bytes())
            ),
        )

        async def fake_json(default=None):
            return self._init_payload(image_bytes())

        request.json = fake_json
        with mock.patch.object(main, "request", request):
            response = self._run(plugin.init_chunked_upload())
        self.assertEqual(response["status_code"], 200)
        session = next(iter(plugin._uploads._sessions.values()))
        self.assertEqual(session.username, "alice")
        # 其它用户拿不到这个会话。
        with self.assertRaises(main.UploadError):
            self._run(plugin._uploads.get_status("bob", session.upload_id))

    def test_init_validation(self):
        plugin = self._make_plugin({})
        manager = plugin._uploads
        bad_payloads = [
            {"client_request_id": "", "orientation": "landscape", "total_bytes": 10},
            {"client_request_id": "x" * 200, "orientation": "landscape", "total_bytes": 10},
            {"client_request_id": "a", "orientation": "sideways", "total_bytes": 10},
            {"client_request_id": "a", "orientation": "landscape", "total_bytes": 0},
            {"client_request_id": "a", "orientation": "landscape", "total_bytes": -5},
            {"client_request_id": "a", "orientation": "landscape", "total_bytes": True},
            {"client_request_id": "a", "orientation": "landscape", "total_bytes": "abc"},
        ]
        for payload in bad_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(main.UploadError):
                    self._run(manager.init_session(USERNAME, payload))

    def test_init_idempotent_and_conflicting_params_rejected(self):
        plugin = self._make_plugin({})
        manager = plugin._uploads
        data = image_bytes()
        first = self._run(manager.init_session(USERNAME, self._init_payload(data)))
        again = self._run(manager.init_session(USERNAME, self._init_payload(data)))
        self.assertEqual(first["upload_id"], again["upload_id"])
        conflict = self._init_payload(data)
        conflict["total_bytes"] = len(data) + 1
        with self.assertRaises(main.UploadError):
            self._run(manager.init_session(USERNAME, conflict))
        # 不同 request_id 是新会话；不同用户互不影响。
        other = self._run(
            manager.init_session(USERNAME, self._init_payload(data, request_id="req-2"))
        )
        self.assertNotEqual(first["upload_id"], other["upload_id"])

    def test_failed_session_frees_request_id_for_retry(self):
        plugin = self._make_plugin({})
        manager = self._make_manager(plugin, chunk_size=64)
        data = bundle(b"fake ftyp")  # 内容非法，入库必失败
        _, session = self._chunked_flow(manager, data)
        self.assertEqual(session.state, "failed")
        retry = self._run(
            manager.init_session(USERNAME, self._init_payload(data))
        )
        self.assertNotEqual(session.upload_id, retry["upload_id"])

    def test_session_limits_per_user(self):
        plugin = self._make_plugin({})
        manager = plugin._uploads
        data = image_bytes()
        self._run(manager.init_session("a", self._init_payload(data, request_id="r1")))
        self._run(manager.init_session("a", self._init_payload(data, request_id="r2")))
        with self.assertRaisesRegex(main.UploadError, "过多"):
            self._run(manager.init_session("a", self._init_payload(data, request_id="r3")))
        # 其他用户不受「a」的槽位影响。
        self._run(manager.init_session("b", self._init_payload(data, request_id="r1")))


class ChunkWriteTest(ChunkedUploadTestCase):
    def test_single_chunk_image_commits_and_builds_cover(self):
        plugin = self._make_plugin({})
        data = image_bytes()
        _, session = self._chunked_flow(plugin._uploads, data)
        self.assertEqual(session.state, "committed")
        filename = session.saved_filename
        self.assertTrue(filename.endswith(".png"))
        self.assertEqual(session.orientation, "landscape")
        self.assertEqual(
            plugin.config["landscape_background_images"], [filename]
        )
        self.assertEqual(plugin.config["landscape_background_image"], filename)
        self.assertTrue(plugin._public_config()["theme_primary"])
        self.assertFalse(session.payload_path.exists())

    def test_video_bundle_spans_small_chunks_with_exact_boundaries(self):
        plugin = self._make_plugin({})
        video = (_FIXTURES / "sample.mp4").read_bytes()
        data = bundle(video)
        manager = self._make_manager(plugin, chunk_size=64)
        _, session = self._chunked_flow(manager, data, orientation="portrait")
        self.assertEqual(session.state, "committed")
        filename = session.saved_filename
        self.assertTrue(filename.endswith(".mp4"))
        saved = plugin._resolve_background(filename)
        self.assertEqual(saved.read_bytes(), video)
        self.assertEqual(plugin.config["portrait_background_images"], [filename])
        self.assertIsNotNone(
            main.find_cover(plugin.paths.cover_dir, filename)
            if hasattr(main, "find_cover")
            else None
        )

    def test_exact_multiple_chunk_count(self):
        plugin = self._make_plugin({})
        data = image_bytes()
        chunk_size = 128
        padded = data + b"\0" * (-len(data) % chunk_size or chunk_size)
        manager = self._make_manager(plugin, chunk_size=chunk_size)
        init = self._run(
            manager.init_session(USERNAME, self._init_payload(padded))
        )
        self.assertEqual(len(padded) % init["chunk_size"], 0)
        _, session = self._chunked_flow(manager, padded)
        self.assertEqual(session.state, "committed")
        # 附加的尾部零字节不影响真实 PNG 校验（尾部数据允许存在）。
        self.assertTrue(session.saved_filename.endswith(".png"))

    def _receiving_session(self, manager, data):
        return self._run(
            manager.init_session(USERNAME, self._init_payload(data))
        )["upload_id"]

    def test_out_of_order_and_out_of_range_rejected(self):
        plugin = self._make_plugin({})
        data = image_bytes() * 4
        manager = self._make_manager(plugin, chunk_size=256)
        upload_id = self._receiving_session(manager, data)
        with self.assertRaisesRegex(main.UploadError, "顺序"):
            self._run(manager.append_chunk(USERNAME, upload_id, "1", Upload(data[256:512])))
        total_chunks = (len(data) + 255) // 256
        with self.assertRaisesRegex(main.UploadError, "超出范围"):
            self._run(
                manager.append_chunk(
                    USERNAME, upload_id, str(total_chunks), Upload(b"x" * 256)
                )
            )
        with self.assertRaises(main.UploadError):
            self._run(manager.append_chunk(USERNAME, upload_id, "abc", Upload(b"x")))

    def test_wrong_length_empty_and_oversized_chunks_rejected(self):
        plugin = self._make_plugin({})
        data = image_bytes() * 4
        manager = self._make_manager(plugin, chunk_size=256)
        upload_id = self._receiving_session(manager, data)
        with self.assertRaisesRegex(main.UploadError, "为空"):
            self._run(manager.append_chunk(USERNAME, upload_id, "0", Upload(b"")))
        with self.assertRaisesRegex(main.UploadError, "长度"):
            self._run(manager.append_chunk(USERNAME, upload_id, "0", Upload(data[:100])))
        with self.assertRaisesRegex(main.UploadError, "长度"):
            self._run(
                manager.append_chunk(USERNAME, upload_id, "0", Upload(data[: 256 + 10]))
            )
        # 失败的尝试不推进确认位置，后续正确块继续。
        receipt = self._run(
            manager.append_chunk(USERNAME, upload_id, "0", Upload(data[:256]))
        )
        self.assertEqual(receipt["next_index"], 1)
        self.assertEqual(receipt["received_bytes"], 256)

    def test_duplicate_chunk_same_digest_confirmed_different_conflicts(self):
        plugin = self._make_plugin({})
        data = image_bytes() * 4
        manager = self._make_manager(plugin, chunk_size=256)
        upload_id = self._receiving_session(manager, data)
        self._run(manager.append_chunk(USERNAME, upload_id, "0", Upload(data[:256])))
        duplicate = self._run(
            manager.append_chunk(USERNAME, upload_id, "0", Upload(data[:256]))
        )
        self.assertEqual(duplicate["next_index"], 1)
        conflicting = bytearray(data[:256])
        conflicting[0] ^= 0xFF
        with self.assertRaisesRegex(main.UploadError, "不一致"):
            self._run(
                manager.append_chunk(USERNAME, upload_id, "0", Upload(bytes(conflicting)))
            )

    def test_receipt_loss_continues_from_status(self):
        plugin = self._make_plugin({})
        data = image_bytes() * 4
        manager = self._make_manager(plugin, chunk_size=256)
        upload_id = self._receiving_session(manager, data)
        self._run(manager.append_chunk(USERNAME, upload_id, "0", Upload(data[:256])))
        # 回执丢失：客户端先查 status 再决定下一块。
        status = self._run(manager.get_status(USERNAME, upload_id))
        self.assertEqual(status["next_index"], 1)
        self.assertEqual(status["received_bytes"], 256)
        self.assertEqual(status["state"], "receiving")
        receipt = self._run(
            manager.append_chunk(USERNAME, upload_id, "1", Upload(data[256:512]))
        )
        self.assertEqual(receipt["next_index"], 2)

    def test_unknown_session_and_path_like_id_rejected(self):
        plugin = self._make_plugin({})
        manager = plugin._uploads
        for bad_id in ("../etc", "0" * 32, "not-a-session"):
            with self.subTest(bad_id=bad_id):
                with self.assertRaises(main.UploadError):
                    self._run(manager.get_status(USERNAME, bad_id))


class FileThreadCancellationTest(ChunkedUploadTestCase):
    def test_chunk_cancel_waits_for_thread_before_close_rollback_and_unlock(self):
        plugin = self._make_plugin({})
        manager = plugin._uploads
        data = image_bytes()
        started, release = threading.Event(), threading.Event()
        original = _uploads_ns["run_file_task"]

        async def gated_file_task(function, *args, **kwargs):
            if function.__name__ == "_write" and not started.is_set():
                def gated():
                    started.set()
                    if not release.wait(3):
                        raise TimeoutError("测试门闩超时")
                    return function(*args, **kwargs)
                return await original(gated)
            return await original(function, *args, **kwargs)

        async def flow():
            init = await manager.init_session(USERNAME, self._init_payload(data))
            session = manager._sessions[init["upload_id"]]
            writing = asyncio.create_task(
                manager.append_chunk(USERNAME, session.upload_id, "0", Upload(data))
            )
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 3))
                writing.cancel()
                await asyncio.sleep(0.02)
                writing.cancel()
                await asyncio.sleep(0.02)
                self.assertFalse(writing.done())
                self.assertTrue(session.lock.locked())
                self.assertEqual(session.next_index, 0)
            finally:
                release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await writing
            self.assertEqual(session.payload_path.stat().st_size, 0)
            self.assertFalse(session.lock.locked())
            receipt = await manager.append_chunk(
                USERNAME, session.upload_id, "0", Upload(data)
            )
            self.assertEqual(receipt["next_index"], 1)
            self.assertEqual(session.payload_path.read_bytes(), data)

        with mock.patch.dict(_uploads_ns, run_file_task=gated_file_task):
            self._run(flow())

    def test_reader_cancel_finishes_read_before_closing_handle(self):
        plugin = self._make_plugin({})
        plugin.paths.ensure_runtime_dirs()
        path = plugin.paths.upload_dir / "reader-test"
        path.write_bytes(image_bytes())
        reader = _uploads_ns["FileUploadReader"](path)
        handle = path.open("rb")
        started, release = threading.Event(), threading.Event()
        ended = threading.Event()

        class GatedHandle:
            def seek(self, offset):
                return handle.seek(offset)

            def read(self, size):
                started.set()
                if not release.wait(3):
                    raise TimeoutError("测试门闩超时")
                data = handle.read(size)
                ended.set()
                return data

            def close(self):
                self_test.assertTrue(ended.is_set())
                handle.close()

        self_test = self
        reader._handle = GatedHandle()

        async def flow():
            async def read_and_close():
                try:
                    await reader.read(20)
                finally:
                    await reader.close()
            task = asyncio.create_task(read_and_close())
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 3))
                task.cancel()
                await asyncio.sleep(0.02)
                self.assertFalse(task.done())
                self.assertFalse(handle.closed)
            finally:
                release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            self.assertTrue(handle.closed)
        self._run(flow())

    def test_terminate_waits_for_real_cover_thread_then_cleans_candidate(self):
        plugin = self._make_plugin({})
        manager = plugin._uploads
        data = bundle((_FIXTURES / "sample.mp4").read_bytes())
        media = main.save_background_upload.__globals__
        original_save_cover = media["save_cover_image"]
        started, release = threading.Event(), threading.Event()

        def gated_cover(*args):
            started.set()
            if not release.wait(3):
                raise TimeoutError("测试门闩超时")
            return original_save_cover(*args)

        async def flow():
            init = await manager.init_session(USERNAME, self._init_payload(data))
            await manager.append_chunk(USERNAME, init["upload_id"], "0", Upload(data))
            await manager.complete(USERNAME, init["upload_id"])
            stopping = None
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 3))
                stopping = asyncio.create_task(plugin.terminate())
                await asyncio.sleep(0.02)
                self.assertFalse(stopping.done(), "真实封面线程结束前不能完成终止")
                self.assertTrue(list(plugin.paths.background_dir.iterdir()))
            finally:
                release.set()
                if stopping:
                    await stopping
            self.assertEqual(list(plugin.paths.background_dir.iterdir()), [])
            self.assertEqual(list(plugin.paths.cover_dir.iterdir()), [])
            self.assertEqual(plugin.config.get("landscape_background_images", []), [])
        with mock.patch.dict(media, save_cover_image=gated_cover):
            self._run(flow())


class CompleteCancelTest(ChunkedUploadTestCase):
    def test_new_intent_reuploads_deleted_material(self):
        plugin = self._make_plugin({})
        _, first = self._chunked_flow(plugin._uploads, image_bytes())
        with mock.patch.object(
            main, "request", _FakeRequest({"background_image": first.saved_filename})
        ):
            self.assertEqual(self._run(plugin.delete_background())["status_code"], 200)
        _, second = self._chunked_flow(
            plugin._uploads, image_bytes(), request_id="new-intent"
        )
        self.assertEqual(second.state, "committed")
        self.assertNotEqual(first.saved_filename, second.saved_filename)
        self.assertTrue(plugin._resolve_background(second.saved_filename).is_file())
        self.assertEqual(
            plugin.config["landscape_background_images"], [second.saved_filename]
        )

    def test_old_committed_receipt_uses_latest_config_and_real_form(self):
        plugin = self._make_plugin({})
        manager, first = self._chunked_flow(plugin._uploads, image_bytes())
        _, second = self._chunked_flow(
            manager, image_bytes(), request_id="second-upload"
        )
        with mock.patch.object(
            main, "request",
            _FakeRequest({"background_image": first.saved_filename}),
        ):
            self._run(plugin.delete_background())
        with mock.patch.object(
            main, "request", _FakeRequest({"background_dim": 0.25})
        ):
            self._run(plugin.save_config())
        result = self._run(manager.get_status(USERNAME, first.upload_id))["result"]
        self.assertEqual(result["background_image"], first.saved_filename)
        self.assertEqual(result["config"]["background_dim"], 0.25)
        self.assertEqual(
            result["config"]["landscape_background_images"], [second.saved_filename]
        )
        # 真实 applyForm 回填回执后再读取真实保存 payload。
        script = r"""
const fs = require("node:fs"), vm = require("node:vm");
const app = fs.readFileSync(process.argv[1], "utf8");
const config = JSON.parse(fs.readFileSync(0, "utf8"));
const context = {
  currentConfig: {}, latestStatus: null,
  orientationNames: {landscape: {}, portrait: {}}, recalculateThemeButton: {},
  numberFromInput: (input, fallback) => Number(input.value) || fallback,
  rotationIntervalFromInput: () => 30,
  getThemeBackgroundFilename: c => c.landscape_background_image,
};
for (const name of ["enabled","dynamicBackground","fit","position","blur","dim",
  "surface","statsCardBlur","mobileSidebarGlass","textMode","textStrength",
  "grayscale","brightness","contrast","saturation","randomBackground",
  "rotationEnabled","rotationInterval","autoTheme","detailedTokenStats","advancedCss"])
  context[name + "Input"] = {value: "", checked: false};
for (const name of ["syncRotationInputs","syncCustomSelect","syncThemeColorPreview",
  "renderGallery","syncPreviewOrientationButtons","syncRangeLabels","updatePreview"])
  context[name] = () => {};
vm.createContext(context);
vm.runInContext(app.slice(app.indexOf("function configFromForm("),
  app.indexOf("function getOrientationConfigKeys(")) +
  app.slice(app.indexOf("function applyForm("), app.indexOf("function syncRangeLabels(")),
  context);
context.applyForm(config);
process.stdout.write(JSON.stringify(context.configForSave()));
"""
        form = subprocess.run(
            ["node", "-e", script, str(_FIXTURES.parent.parent / "pages/settings/app.js")],
            input=json.dumps(result["config"]), text=True, capture_output=True,
            timeout=10, check=True,
        )
        payload = json.loads(form.stdout)
        self.assertEqual(payload["background_dim"], 0.25)
        self.assertNotIn("landscape_background_images", payload)
        with mock.patch.object(main, "request", _FakeRequest(payload)):
            saved = self._run(plugin.save_config())["body"]["config"]
        self.assertEqual(saved["background_dim"], 0.25)
        self.assertEqual(saved["landscape_background_images"], [second.saved_filename])

    def test_temporary_result_failure_recovers_on_next_query(self):
        plugin = self._make_plugin({})
        manager, session = self._chunked_flow(plugin._uploads, image_bytes())
        with mock.patch.object(
            manager._hooks, "build_result", side_effect=OSError("暂不可读")
        ):
            fallback = self._run(manager.complete(USERNAME, session.upload_id))
        self.assertNotIn("config", fallback["result"])
        result = self._run(manager.get_status(USERNAME, session.upload_id))["result"]
        self.assertIn("config", result)
        self.assertEqual(result["background_image"], session.saved_filename)
        self.assertTrue(plugin._resolve_background(session.saved_filename).is_file())

    def test_complete_requires_all_chunks(self):
        plugin = self._make_plugin({})
        data = image_bytes() * 4
        manager = self._make_manager(plugin, chunk_size=256)
        upload_id = self._run(
            manager.init_session(USERNAME, self._init_payload(data))
        )["upload_id"]
        self._run(manager.append_chunk(USERNAME, upload_id, "0", Upload(data[:256])))
        with self.assertRaisesRegex(main.UploadError, "未确认"):
            self._run(manager.complete(USERNAME, upload_id))

    def test_duplicate_and_concurrent_complete_ingest_once(self):
        plugin = self._make_plugin({})
        data = image_bytes()

        async def flow():
            manager = plugin._uploads
            init = await manager.init_session(USERNAME, self._init_payload(data))
            upload_id = init["upload_id"]
            await manager.append_chunk(USERNAME, upload_id, "0", Upload(data))
            first, second = await asyncio.gather(
                manager.complete(USERNAME, upload_id),
                manager.complete(USERNAME, upload_id),
            )
            session = manager._sessions[upload_id]
            if session.task is not None:
                await session.task
            # 入库成功后再重复 complete：返回同一素材身份，不重复入库。
            again = await manager.complete(USERNAME, upload_id)
            status = await manager.get_status(USERNAME, upload_id)
            return first, second, again, status

        first, second, again, status = self._run(flow())
        self.assertIn(first["state"], {"processing", "committed"})
        self.assertIn(second["state"], {"processing", "committed"})
        filename = again["result"]["background_image"]
        self.assertEqual(status["result"]["background_image"], filename)
        self.assertEqual(plugin.config["landscape_background_images"], [filename])
        self.assertEqual(len(list(plugin.paths.background_dir.iterdir())), 1)

    def test_cancel_after_commit_keeps_formal_material(self):
        plugin = self._make_plugin({})
        _, session = self._chunked_flow(plugin._uploads, image_bytes())
        filename = session.saved_filename
        response = self._run(plugin._uploads.cancel(USERNAME, session.upload_id))
        self.assertEqual(response["state"], "committed")
        self.assertTrue(plugin._resolve_background(filename).is_file())
        self.assertEqual(plugin.config["landscape_background_images"], [filename])

    def test_user_deleted_material_old_receipt_does_not_readd(self):
        plugin = self._make_plugin({})
        _, session = self._chunked_flow(plugin._uploads, image_bytes())
        filename = session.saved_filename
        with mock.patch.object(
            main,
            "request",
            _FakeRequest({"orientation": "landscape", "background_image": filename}),
        ):
            self.assertEqual(self._run(plugin.delete_background())["status_code"], 200)
        self.assertEqual(plugin.config["landscape_background_images"], [])
        # 旧回执只确认历史身份，不把素材重新加入或选中。
        again = self._run(plugin._uploads.complete(USERNAME, session.upload_id))
        self.assertEqual(again["result"]["background_image"], filename)
        self.assertEqual(plugin.config["landscape_background_images"], [])
        self.assertEqual(plugin.config["landscape_background_image"], "")

    def test_invalid_content_marks_failed_and_cleans_candidate(self):
        plugin = self._make_plugin({})
        manager, session = self._chunked_flow(
            self._make_manager(plugin, chunk_size=64), bundle(b"fake ftyp")
        )
        self.assertEqual(session.state, "failed")
        self.assertTrue(session.error)
        self.assertEqual(list(plugin.paths.background_dir.iterdir()), [])
        self.assertEqual(list(plugin.paths.cover_dir.iterdir()), [])
        self.assertEqual(plugin.config.get("landscape_background_images", []), [])
        self.assertFalse(session.payload_path.exists())
        # 失败状态可查询，重复 cancel 不删除正式素材也不报错。
        status = self._run(manager.get_status(USERNAME, session.upload_id))
        self.assertEqual(status["state"], "failed")
        response = self._run(manager.cancel(USERNAME, session.upload_id))
        self.assertEqual(response["state"], "failed")

    def test_config_save_failure_cleans_candidate(self):
        plugin = self._make_plugin({})
        manager = self._make_manager(plugin, chunk_size=64)
        with mock.patch.object(
            plugin, "_save_config", side_effect=ValueError("保存失败")
        ):
            _, session = self._chunked_flow(manager, bundle(image_bytes()))
        self.assertEqual(session.state, "failed")
        self.assertEqual(list(plugin.paths.background_dir.iterdir()), [])
        self.assertEqual(list(plugin.paths.cover_dir.iterdir()), [])

    def test_cancel_wins_and_complete_wins_both_consistent(self):
        # cancel 先赢：会话取消后 complete 拒绝、迟到块拒绝。
        plugin = self._make_plugin({})
        data = image_bytes() * 2
        manager = self._make_manager(plugin, chunk_size=len(data) // 2)
        upload_id = self._run(
            manager.init_session(USERNAME, self._init_payload(data))
        )["upload_id"]
        self._run(manager.append_chunk(USERNAME, upload_id, "0", Upload(data[: len(data) // 2])))
        response = self._run(manager.cancel(USERNAME, upload_id))
        self.assertEqual(response["state"], "cancelled")
        with self.assertRaises(main.UploadError):
            self._run(manager.complete(USERNAME, upload_id))
        with self.assertRaises(main.UploadError):
            self._run(
                manager.append_chunk(USERNAME, upload_id, "1", Upload(data[len(data) // 2 :]))
            )
        self.assertFalse(
            any(plugin.paths.upload_dir.iterdir()), "取消后临时目录应清理"
        )

        # complete 先赢：cancel 只返回真实状态，素材正常入库。
        plugin2 = self._make_plugin({})
        _, session = self._chunked_flow(plugin2._uploads, image_bytes())
        response = self._run(plugin2._uploads.cancel(USERNAME, session.upload_id))
        self.assertEqual(response["state"], "committed")
        self.assertEqual(
            plugin2.config["landscape_background_images"],
            [session.saved_filename],
        )

    def test_chunked_commit_interleaved_with_legacy_upload_keeps_both(self):
        plugin = self._make_plugin({})
        chunked_data = image_bytes()
        colors_started = threading.Event()
        release_colors = threading.Event()
        original_colors = plugin._with_theme_colors

        def delayed_colors(config, **kwargs):
            colors_started.set()
            if not release_colors.wait(5):
                raise RuntimeError("test interleave wait timed out")
            return original_colors(config, **kwargs)

        async def flow():
            manager = plugin._uploads
            init = await manager.init_session(USERNAME, self._init_payload(chunked_data))
            upload_id = init["upload_id"]
            await manager.append_chunk(USERNAME, upload_id, "0", Upload(chunked_data))
            with (
                mock.patch.object(plugin, "_with_theme_colors", delayed_colors),
                mock.patch.object(
                    main, "request", _FormUpload(image_bytes("JPEG"))
                ),
                mock.patch.object(main, "ensure_dashboard_injection", lambda paths: {}),
            ):
                await manager.complete(USERNAME, upload_id)
                session = manager._sessions[upload_id]
                legacy = asyncio.create_task(
                    plugin._upload_background_for_orientation("landscape")
                )
                try:
                    self.assertTrue(
                        await asyncio.to_thread(colors_started.wait, 3)
                    )
                    # 分块入库持有配置锁取色时，旧上传在锁外完成素材处理后等待。
                    await asyncio.sleep(0.1)
                    self.assertFalse(legacy.done())
                finally:
                    release_colors.set()
                if session.task is not None:
                    await session.task
                legacy_response = await legacy
            return session, legacy_response

        session, legacy_response = self._run(flow())
        self.assertEqual(session.state, "committed")
        self.assertEqual(legacy_response["status_code"], 200)
        filenames = {
            session.saved_filename,
            legacy_response["body"]["background_image"],
        }
        self.assertEqual(
            set(plugin.config["landscape_background_images"]), filenames
        )
        self.assertEqual(
            {path.name for path in plugin.paths.background_dir.iterdir()}, filenames
        )


class _FormUpload:
    """旧单次上传接口的最小请求桩。"""

    query = {}
    username = USERNAME

    def __init__(self, data):
        self.upload = Upload(data)

    async def files(self):
        return {"file": self.upload}

    async def form(self):
        return {}

    async def json(self, default=None):
        return {}


class ExpiryRecoveryTest(ChunkedUploadTestCase):
    def _force_sweep(self, manager):
        manager._last_sweep = 0
        return self._run(manager._sweep_expired())

    def test_receiving_idle_expires_and_directory_removed(self):
        plugin = self._make_plugin({})
        manager = plugin._uploads
        upload_id = self._run(
            manager.init_session(USERNAME, self._init_payload(image_bytes()))
        )["upload_id"]
        session = manager._sessions[upload_id]
        directory = session.directory
        session.updated_at -= RECEIVING_IDLE_TTL + 1
        self._force_sweep(manager)
        self.assertNotIn(upload_id, manager._sessions)
        self.assertFalse(directory.exists())
        with self.assertRaises(main.UploadError):
            self._run(manager.get_status(USERNAME, upload_id))

    def test_processing_not_swept_and_failed_kept_for_idle_ttl(self):
        plugin = self._make_plugin({})
        manager = plugin._uploads
        upload_id = self._run(
            manager.init_session(USERNAME, self._init_payload(image_bytes()))
        )["upload_id"]
        session = manager._sessions[upload_id]
        session.state = "processing"
        session.updated_at -= COMMITTED_RECEIPT_TTL + 1
        self._force_sweep(manager)
        self.assertIn(upload_id, manager._sessions)

        session.state = "failed"
        session.updated_at = time.time() - 60
        self._force_sweep(manager)
        self.assertIn(upload_id, manager._sessions, "失败会话应保留一个闲置周期供查询")
        session.updated_at -= RECEIVING_IDLE_TTL + 1
        self._force_sweep(manager)
        self.assertNotIn(upload_id, manager._sessions)

    def test_committed_receipt_expires_after_retention(self):
        plugin = self._make_plugin({})
        manager, session = self._chunked_flow(plugin._uploads, image_bytes())
        directory = session.directory
        manager._sessions[session.upload_id] = session
        session.updated_at -= COMMITTED_RECEIPT_TTL + 1
        self._force_sweep(manager)
        self.assertNotIn(session.upload_id, manager._sessions)
        self.assertFalse(directory.exists())
        # 回执过期不影响正式素材。
        filename = session.saved_filename
        self.assertTrue(plugin._resolve_background(filename).is_file())

    def test_restart_invalidates_unfinished_transfer(self):
        plugin = self._make_plugin({})
        data = image_bytes() * 4
        manager = self._make_manager(plugin, chunk_size=256)
        upload_id = self._run(
            manager.init_session(USERNAME, self._init_payload(data))
        )["upload_id"]
        self._run(manager.append_chunk(USERNAME, upload_id, "0", Upload(data[:256])))
        directory = manager._sessions[upload_id].directory
        self.assertTrue(directory.exists())
        restarted = self._make_manager(plugin)
        notes = restarted.recover()
        self.assertEqual(notes, [])
        self.assertFalse(directory.exists())

    def test_restart_committing_with_config_reference_repairs_receipt(self):
        plugin = self._make_plugin({})
        manager, session = self._chunked_flow(plugin._uploads, image_bytes())
        directory = session.directory
        material_id = session.material_id
        # 模拟「配置已保存但成功回执未落盘」：回退回执为 committing 状态。
        meta = json.loads((directory / "session.json").read_text(encoding="utf-8"))
        meta["state"] = "processing"
        (directory / "session.json").write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8"
        )
        restarted = self._make_manager(plugin)
        notes = restarted.recover()
        self.assertEqual(notes, [])
        repaired = json.loads((directory / "session.json").read_text(encoding="utf-8"))
        self.assertEqual(repaired["state"], "committed")
        self.assertEqual(repaired["material_id"], material_id)
        self.assertEqual(
            repaired["saved_filename"], session.saved_filename
        )
        # 回执装入内存：重启后的重复 complete/status 返回同一历史身份，不重复入库。
        filename = session.saved_filename
        again = self._run(restarted.complete(USERNAME, session.upload_id))
        self.assertEqual(again["state"], "committed")
        self.assertEqual(again["result"]["background_image"], filename)
        status = self._run(restarted.get_status(USERNAME, session.upload_id))
        self.assertEqual(status["result"]["background_image"], filename)
        self.assertEqual(plugin.config["landscape_background_images"], [filename])
        # 正式素材保持不动。
        self.assertTrue(plugin._resolve_background(filename).is_file())

    def test_restart_loads_committed_receipt_for_identity(self):
        plugin = self._make_plugin({})
        manager, session = self._chunked_flow(plugin._uploads, image_bytes())
        filename = session.saved_filename
        restarted = self._make_manager(plugin)
        notes = restarted.recover()
        self.assertEqual(notes, [])
        status = self._run(restarted.get_status(USERNAME, session.upload_id))
        self.assertEqual(status["state"], "committed")
        self.assertEqual(status["result"]["background_image"], filename)
        self.assertEqual(plugin.config["landscape_background_images"], [filename])

    def test_restart_committing_without_reference_cleans_candidate(self):
        plugin = self._make_plugin({})
        manager = plugin._uploads
        init = self._run(
            manager.init_session(USERNAME, self._init_payload(image_bytes()))
        )
        session = manager._sessions[init["upload_id"]]
        directory = session.directory
        # 模拟入库中断：只留下未引用的候选原素材和 committing 回执。
        candidate = plugin.paths.background_dir / f"background-{session.material_id}.png"
        candidate.write_bytes(image_bytes())
        meta = json.loads((directory / "session.json").read_text(encoding="utf-8"))
        meta["state"] = "processing"
        (directory / "session.json").write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8"
        )
        restarted = self._make_manager(plugin)
        notes = restarted.recover()
        self.assertEqual(notes, [])
        self.assertFalse(candidate.exists())
        self.assertFalse(directory.exists())
        self.assertEqual(plugin.config.get("landscape_background_images", []), [])

    def test_restart_corrupt_meta_is_kept_and_reported(self):
        plugin = self._make_plugin({})
        directory = plugin.paths.upload_dir / "broken-session"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "session.json").write_text("not json", encoding="utf-8")
        restarted = self._make_manager(plugin)
        notes = restarted.recover()
        self.assertTrue(notes)
        self.assertTrue(directory.exists(), "记录损坏不能猜测清理")


class LargeBundleChunkedUploadTest(ChunkedUploadTestCase):
    def test_bundle_over_128mib_uploads_via_default_chunks(self):
        plugin = self._make_plugin({})
        padding = 128 * 1024 * 1024
        video = (
            (_FIXTURES / "sample.mp4").read_bytes()
            + (padding + 8).to_bytes(4, "big")
            + b"free"
            + b"\0" * padding
        )
        data = bundle(video)
        self.assertGreater(len(data), 128 * 1024 * 1024)
        manager, session = self._chunked_flow(plugin._uploads, data)
        self.assertEqual(session.state, "committed")
        filename = session.saved_filename
        self.assertTrue(filename.endswith(".mp4"))
        saved = plugin._resolve_background(filename)
        self.assertGreater(saved.stat().st_size, 128 * 1024 * 1024)
        # 原素材内容与上传前一致（流式校验，不整读比较）。
        expected = hashlib.sha256(video).hexdigest()
        actual = hashlib.sha256()
        with saved.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                actual.update(chunk)
        self.assertEqual(actual.hexdigest(), expected)
        self.assertEqual(plugin.config["landscape_background_images"], [filename])
        item = plugin._background_item(filename, True)
        self.assertEqual(item["media_type"], "video")
        self.assertTrue(item["cover_url"])


if __name__ == "__main__":
    unittest.main()
