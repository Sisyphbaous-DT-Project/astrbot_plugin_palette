"""素材真实解码、原子上传、封面/缩略图/取色和混合图库回归。"""

from __future__ import annotations

import asyncio
import json
import subprocess
import threading
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PIL import Image

from test_config import PalettePluginTestCase, _FakeRequest, main

media = main.save_background_upload.__globals__
_FIXTURES = Path(__file__).with_name("fixtures")

def settings_payload(snapshot, **inputs):
    """执行设置页真实表单函数，避免用简化请求遗漏旧图库快照。"""

    script = r"""
const fs = require("node:fs");
const vm = require("node:vm");
const request = JSON.parse(fs.readFileSync(0, "utf8"));
const app = fs.readFileSync(process.argv[1], "utf8");
const form = app.slice(app.indexOf("function configFromForm("),
  app.indexOf("\nfunction getOrientationConfigKeys("));
const context = {
  currentConfig: request.snapshot,
  numberFromInput: (input, fallback) => Number(input.value) || fallback,
  rotationIntervalFromInput: () => 30,
};
const inputNames = [
  ...form.matchAll(/\b(\w+Input)\./g),
  ...form.matchAll(/numberFromInput\((\w+Input),/g),
].map(match => match[1]);
for (const name of new Set(inputNames)) {
  context[name] = {value: "0", checked: true, ...request.inputs[name]};
}
context.fitInput.value = "cover";
context.positionInput.value = "center center";
context.textModeInput.value = "soft_shadow";
context.advancedCssInput.value = "";
vm.createContext(context);
vm.runInContext(form, context);
process.stdout.write(JSON.stringify(context.configForSave()));
"""
    result = subprocess.run(
        ["node", "-e", script, str(_FIXTURES.parent.parent / "pages/settings/app.js")],
        input=json.dumps({"snapshot": snapshot, "inputs": inputs}),
        text=True,
        capture_output=True,
        timeout=10,
        check=True,
    )
    return json.loads(result.stdout)


def image_bytes(format="PNG", *, animated=False):
    buffer = BytesIO()
    image = Image.new("RGB", (24, 16), (32, 180, 85))
    options = {}
    if animated:
        options = {
            "save_all": True,
            "append_images": [Image.new("RGB", image.size, (230, 45, 70))],
            "duration": 100,
            "loop": 0,
        }
    image.save(buffer, format, **options)
    return buffer.getvalue()


def bundle(content, cover=None):
    cover = image_bytes() if cover is None else cover
    return b"PALETTE-MEDIA-1\n" + len(cover).to_bytes(4, "big") + cover + content


class Upload:
    def __init__(self, data, *, filename="unknown.bin", content_length=None):
        self.content = BytesIO(data)
        self.filename = filename
        self.content_length = content_length

    async def seek(self, offset):
        self.content.seek(offset)

    async def read(self, size=-1):
        return self.content.read(size)


class FormRequest(_FakeRequest):
    query = {}

    def __init__(self, upload):
        super().__init__({})
        self.upload = upload

    async def files(self):
        return {"file": self.upload}

    async def form(self):
        return {}


class ConcurrentRequest:
    """按任务分发上传文件与 JSON，模拟同一插件的并发请求。"""

    query = {}

    def __init__(self, uploads=None, payloads=None):
        self.uploads = uploads or {}
        self.payloads = payloads or {}

    async def files(self):
        return {"file": self.uploads[asyncio.current_task().get_name()]}

    async def form(self):
        return {}

    async def json(self, default=None):
        return self.payloads[asyncio.current_task().get_name()]


class MediaUploadTest(PalettePluginTestCase):
    def upload(self, plugin, data, orientation="landscape"):
        with (
            mock.patch.object(main, "request", FormRequest(Upload(data))),
            mock.patch.object(main, "ensure_dashboard_injection", lambda paths: {}),
        ):
            return asyncio.run(plugin._upload_background_for_orientation(orientation))

    def test_legacy_defaults_and_direction_media_match_fallback(self):
        plugin = self._make_plugin({}, ("only.mp4",))
        plugin.config.update(
            landscape_background_image="only.mp4",
            landscape_background_images=["only.mp4"],
        )
        config = plugin._public_config()
        self.assertTrue(config["dynamic_background_enabled"])
        self.assertEqual(
            config["portrait_background_url"], config["landscape_background_url"]
        )
        self.assertEqual(config["portrait_background_media"]["media_type"], "video")
        self.assertFalse(
            plugin._normalize_config({"dynamic_background_enabled": "off"})[
                "dynamic_background_enabled"
            ]
        )

    def test_image_real_content_and_existing_current_preserved(self):
        plugin = self._make_plugin({})
        first = self.upload(plugin, image_bytes())
        self.assertEqual(first["status_code"], 200)
        filename = first["body"]["background_image"]
        self.assertTrue(filename.endswith(".png"))
        self.assertTrue(media["find_cover"](plugin.paths.cover_dir, filename).is_file())
        self.assertTrue(first["body"]["config"]["theme_primary"])
        second = self.upload(plugin, image_bytes("JPEG"))
        self.assertEqual(
            second["body"]["config"]["landscape_background_image"], filename
        )
        self.assertEqual(
            len(second["body"]["config"]["landscape_background_images"]), 2
        )

    def test_valid_webp_with_multibyte_riff_size_uploads(self):
        data = (_FIXTURES / "valid-webp-multibyte-length.webp").read_bytes()
        self.assertEqual(data[4:6], b"\xde\x87")
        plugin = self._make_plugin({})
        response = self.upload(plugin, data)
        self.assertEqual(response["status_code"], 200, response)
        self.assertTrue(response["body"]["background_image"].endswith(".webp"))

    def test_dynamic_image_cover_is_static_and_thumbnail_and_color_are_real(self):
        plugin = self._make_plugin({})
        for format in ("GIF", "WEBP"):
            with self.subTest(format=format):
                response = self.upload(plugin, image_bytes(format, animated=True))
                filename = response["body"]["background_image"]
                item = plugin._background_item(filename, False)
                self.assertEqual(item["media_type"], "animated_image")
                cover = media["find_cover"](plugin.paths.cover_dir, filename)
                with Image.open(cover) as image:
                    self.assertFalse(getattr(image, "is_animated", False))
                self.assertEqual(plugin._theme_color_source(filename), cover)
                request = SimpleNamespace(query={"filename": filename})
                with mock.patch.object(main, "request", request):
                    result = asyncio.run(plugin.get_background_thumbnail())
                self.assertTrue(result["body"]["data_url"].startswith("data:image/"))

    def test_real_video_containers_and_svg_persist_covers(self):
        plugin = self._make_plugin({})
        samples = [
            ("mp4", (_FIXTURES / "sample.mp4").read_bytes()),
            ("webm", (_FIXTURES / "sample.webm").read_bytes()),
            (
                "svg",
                b'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="16"><rect width="24" height="16" fill="green"><animate attributeName="opacity" values="0.5;1;0.5" dur="2s" repeatCount="indefinite"/></rect></svg>',
            ),
        ]
        for suffix, content in samples:
            with self.subTest(suffix=suffix):
                response = self.upload(plugin, bundle(content), "portrait")
                self.assertEqual(response["status_code"], 200, response)
                filename = response["body"]["background_image"]
                self.assertTrue(filename.endswith("." + suffix))
                cover = media["find_cover"](plugin.paths.cover_dir, filename)
                self.assertTrue(cover.is_file())
                self.assertEqual(plugin._theme_color_source(filename), cover)
                with mock.patch.object(
                    main, "request", SimpleNamespace(query={"filename": filename})
                ):
                    preview = asyncio.run(plugin.get_background_preview())["body"][
                        "data_url"
                    ]
                self.assertTrue(preview.startswith("data:image/"))
                self.assertLess(len(preview), 10000)

    def test_errors_leave_no_files_or_config(self):
        plugin = self._make_plugin({})
        before = dict(plugin.config)
        cases = [
            b"",
            b"fake ftyp",
            b"\x00\x00\x00\x10ftypisom\x00\x00\x00\x00",
            (_FIXTURES / "sample.mp4").read_bytes(),
            bundle((_FIXTURES / "sample.mp4").read_bytes(), b"fake cover"),
            bundle(b"<svg><script>alert(1)</script></svg>"),
            b"PALETTE-MEDIA-1\n\x00\x00\x00\xffshort",
            b"\x89PNG\r\n\x1a\nbroken",
        ]
        for data in cases:
            with self.subTest(prefix=data[:30]):
                response = self.upload(plugin, data)
                self.assertEqual(response["status_code"], 400)
                self.assertEqual(plugin.config, before)
                self.assertEqual(list(plugin.paths.background_dir.iterdir()), [])
                self.assertEqual(list(plugin.paths.cover_dir.iterdir()), [])

    def test_limits_and_invalid_cover_cleanup(self):
        plugin = self._make_plugin({})
        with mock.patch.dict(media, MAX_BACKGROUND_BYTES=32):
            self.assertEqual(self.upload(plugin, image_bytes())["status_code"], 400)
        with mock.patch.dict(media, MAX_VIDEO_BYTES=32):
            self.assertEqual(
                self.upload(plugin, bundle((_FIXTURES / "sample.mp4").read_bytes()))[
                    "status_code"
                ],
                400,
            )
        huge_cover = BytesIO()
        Image.new("RGB", (4097, 1), "blue").save(huge_cover, "PNG")
        self.assertEqual(
            self.upload(
                plugin,
                bundle((_FIXTURES / "sample.mp4").read_bytes(), huge_cover.getvalue()),
            )["status_code"],
            400,
        )
        self.assertEqual(list(plugin.paths.background_dir.iterdir()), [])
        self.assertEqual(list(plugin.paths.cover_dir.iterdir()), [])

    def test_config_save_failure_cleans_files(self):
        plugin = self._make_plugin({})
        with mock.patch.object(
            plugin, "_save_config", side_effect=ValueError("保存失败")
        ):
            self.assertEqual(self.upload(plugin, image_bytes())["status_code"], 400)
        self.assertEqual(list(plugin.paths.background_dir.iterdir()), [])
        self.assertEqual(list(plugin.paths.cover_dir.iterdir()), [])

    def test_first_concurrent_uploads_keep_both_records_and_current(self):
        plugin = self._make_plugin({})
        first_color_started = threading.Event()
        release_first = threading.Event()
        original_colors = plugin._with_theme_colors
        original_save_upload = plugin._save_background_upload

        def delayed_colors(*args, **kwargs):
            first_color_started.set()
            if not release_first.wait(5):
                raise RuntimeError("test color wait timed out")
            return original_colors(*args, **kwargs)

        async def scenario():
            second_prepared = asyncio.Event()

            async def save_upload(upload):
                filename = await original_save_upload(upload)
                if asyncio.current_task().get_name() == "second":
                    second_prepared.set()
                return filename

            request = ConcurrentRequest(
                {
                    "first": Upload(image_bytes()),
                    "second": Upload(image_bytes("JPEG")),
                }
            )
            with (
                mock.patch.object(main, "request", request),
                mock.patch.object(main, "ensure_dashboard_injection", lambda paths: {}),
                mock.patch.object(plugin, "_with_theme_colors", delayed_colors),
                mock.patch.object(plugin, "_save_background_upload", save_upload),
            ):
                first = asyncio.create_task(
                    plugin._upload_background_for_orientation("landscape"), name="first"
                )
                try:
                    self.assertTrue(
                        await asyncio.to_thread(first_color_started.wait, 3)
                    )
                    second = asyncio.create_task(
                        plugin._upload_background_for_orientation("landscape"),
                        name="second",
                    )
                    await asyncio.wait_for(second_prepared.wait(), timeout=3)
                    self.assertFalse(second.done(), "素材处理可并发，配置合并必须等待")
                finally:
                    release_first.set()
                responses = await asyncio.gather(first, second)
            self.assertEqual(
                [response["status_code"] for response in responses], [200, 200]
            )
            filenames = [response["body"]["background_image"] for response in responses]
            self.assertEqual(plugin.config["landscape_background_images"], filenames)
            self.assertEqual(plugin.config["landscape_background_image"], filenames[0])
            self.assertEqual(
                set(path.name for path in plugin.paths.background_dir.iterdir()),
                set(filenames),
            )

        asyncio.run(scenario())

    def test_deletion_overlapping_upload_preserves_new_record(self):
        plugin = self._make_plugin({})
        current = self.upload(plugin, image_bytes())["body"]["background_image"]
        next_file = self.upload(plugin, image_bytes("JPEG"))["body"]["background_image"]
        colors_started = threading.Event()
        release_colors = threading.Event()
        original_colors = plugin._with_theme_colors
        original_save_upload = plugin._save_background_upload

        def delayed_colors(config, **kwargs):
            colors_started.set()
            if not release_colors.wait(5):
                raise RuntimeError("test deletion wait timed out")
            return original_colors(config, **kwargs)

        async def scenario():
            upload_prepared = asyncio.Event()

            async def save_upload(upload):
                filename = await original_save_upload(upload)
                upload_prepared.set()
                return filename

            request = ConcurrentRequest(
                uploads={"uploading": Upload(image_bytes())},
                payloads={
                    "deleting": {
                        "background_image": current,
                        "orientation": "landscape",
                    }
                },
            )
            with (
                mock.patch.object(main, "request", request),
                mock.patch.object(main, "ensure_dashboard_injection", lambda paths: {}),
                mock.patch.object(plugin, "_with_theme_colors", delayed_colors),
                mock.patch.object(plugin, "_save_background_upload", save_upload),
            ):
                deleting = asyncio.create_task(
                    plugin.delete_background(), name="deleting"
                )
                try:
                    self.assertTrue(await asyncio.to_thread(colors_started.wait, 3))
                    uploading = asyncio.create_task(
                        plugin._upload_background_for_orientation("landscape"),
                        name="uploading",
                    )
                    await asyncio.wait_for(upload_prepared.wait(), timeout=3)
                    self.assertFalse(uploading.done())
                finally:
                    release_colors.set()
                deleted, uploaded = await asyncio.gather(deleting, uploading)
            self.assertEqual(deleted["status_code"], 200)
            self.assertEqual(uploaded["status_code"], 200)
            filename = uploaded["body"]["background_image"]
            self.assertEqual(
                plugin.config["landscape_background_images"], [next_file, filename]
            )
            self.assertEqual(plugin.config["landscape_background_image"], next_file)
            self.assertFalse(plugin._resolve_background(current).exists())
            self.assertTrue(plugin._resolve_background(filename).exists())

        asyncio.run(scenario())

    def test_settings_save_waits_for_current_library_update(self):
        plugin = self._make_plugin({})
        entered = threading.Event()
        release = threading.Event()
        original = plugin._with_theme_colors

        def delayed_colors(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("test save wait timed out")
            return original(*args, **kwargs)

        async def scenario():
            request = ConcurrentRequest(
                uploads={"uploading": Upload(image_bytes())},
                payloads={
                    "saving": settings_payload(
                        plugin._public_config(), enabledInput={"checked": False}
                    )
                },
            )
            with (
                mock.patch.object(main, "request", request),
                mock.patch.object(main, "ensure_dashboard_injection", lambda paths: {}),
                mock.patch.object(plugin, "_with_theme_colors", delayed_colors),
            ):
                uploading = asyncio.create_task(
                    plugin._upload_background_for_orientation("landscape"),
                    name="uploading",
                )
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait, 3))
                    saving = asyncio.create_task(plugin.save_config(), name="saving")
                    await asyncio.sleep(0)
                    self.assertFalse(saving.done())
                finally:
                    release.set()
                uploaded, saved = await asyncio.gather(uploading, saving)
            self.assertEqual(saved["status_code"], 200)
            self.assertFalse(plugin.config["enabled"])
            self.assertEqual(
                plugin.config["landscape_background_images"],
                [uploaded["body"]["background_image"]],
            )

        asyncio.run(scenario())

    def test_old_settings_page_save_keeps_new_upload_and_theme(self):
        plugin = self._make_plugin({})
        snapshot = plugin._public_config()
        uploaded = self.upload(plugin, image_bytes())["body"]["background_image"]
        theme = (plugin.config["theme_primary"], plugin.config["theme_secondary"])
        payload = settings_payload(snapshot, dimInput={"value": "0.6"})
        self.assertNotIn("landscape_background_images", payload)
        self.assertNotIn("theme_primary", payload)
        with mock.patch.object(main, "request", _FakeRequest(payload)):
            response = asyncio.run(plugin.save_config())
        self.assertEqual(response["status_code"], 200)
        self.assertEqual(plugin.config["background_dim"], 0.6)
        self.assertEqual(plugin.config["landscape_background_images"], [uploaded])
        self.assertEqual(plugin.config["landscape_background_image"], uploaded)
        self.assertEqual(
            (plugin.config["theme_primary"], plugin.config["theme_secondary"]), theme
        )

    def test_old_settings_page_save_does_not_restore_deleted_or_previous_current(self):
        for delete in (False, True):
            with self.subTest(delete=delete):
                plugin = self._make_plugin({})
                first = self.upload(plugin, image_bytes())["body"]["background_image"]
                snapshot = plugin._public_config()
                next_file = self.upload(plugin, image_bytes("JPEG"))["body"]["background_image"]
                with mock.patch.object(
                    main,
                    "request",
                    _FakeRequest({
                        "orientation": "landscape",
                        "background_image": first if delete else next_file,
                    }),
                ):
                    handler = plugin.delete_background if delete else plugin.select_background
                    self.assertEqual(asyncio.run(handler())["status_code"], 200)
                payload = settings_payload(snapshot, dimInput={"value": "0.7"})
                with mock.patch.object(main, "request", _FakeRequest(payload)):
                    response = asyncio.run(plugin.save_config())
                self.assertEqual(response["status_code"], 200)
                self.assertEqual(plugin.config["landscape_background_image"], next_file)
                self.assertEqual(
                    plugin.config["landscape_background_images"],
                    [next_file] if delete else [first, next_file],
                )
                self.assertEqual(plugin.config["background_dim"], 0.7)

    def test_svg_read_response_is_sandboxed_and_nosniff(self):
        plugin = self._make_plugin({})
        filename = self.upload(
            plugin,
            bundle(
                b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>'
            ),
        )["body"]["background_image"]
        with mock.patch.object(main, "file_response", lambda path, **kw: kw):
            response = asyncio.run(plugin.get_background(filename))
        self.assertEqual(response["headers"]["X-Content-Type-Options"], "nosniff")
        self.assertIn("sandbox;", response["headers"]["Content-Security-Policy"])
        self.assertIn(
            "default-src 'none'", response["headers"]["Content-Security-Policy"]
        )

    def test_select_random_delete_mixed_pool_and_all_references(self):
        plugin = self._make_plugin({})
        image = self.upload(plugin, image_bytes())["body"]["background_image"]
        video = self.upload(plugin, bundle((_FIXTURES / "sample.mp4").read_bytes()))[
            "body"
        ]["background_image"]
        with mock.patch.object(
            main,
            "request",
            _FakeRequest({"orientation": "landscape", "background_image": video}),
        ):
            self.assertEqual(
                asyncio.run(plugin.select_background())["status_code"], 200
            )
        plugin.config["background_rotation_enabled"] = True
        self.assertEqual(
            self._run_random_select(
                plugin, {"scheduled": True, "orientation": "landscape"}
            )["body"]["config"]["landscape_background_image"],
            image,
        )
        plugin.config.update(
            background_image=video,
            background_images=[video],
            portrait_background_image=video,
            portrait_background_images=[video],
        )
        with mock.patch.object(
            main,
            "request",
            _FakeRequest({"orientation": "landscape", "background_image": video}),
        ):
            self.assertEqual(
                asyncio.run(plugin.delete_background())["status_code"], 200
            )
        self.assertFalse(plugin._resolve_background(video).exists())
        self.assertIsNone(media["find_cover"](plugin.paths.cover_dir, video))
        self.assertNotIn(video, str(plugin._public_config()))
        self.assertNotIn(
            "orientation",
            self._run_random_select(
                plugin, {"scheduled": True, "orientation": "landscape"}
            )["body"],
        )

    def test_deleting_current_keeps_cleanup_when_next_cover_is_missing(self):
        plugin = self._make_plugin({})
        current = self.upload(plugin, image_bytes())["body"]["background_image"]
        video = self.upload(plugin, bundle((_FIXTURES / "sample.mp4").read_bytes()))[
            "body"
        ]["background_image"]
        media["delete_background_cover"](plugin.paths.cover_dir, video)
        with mock.patch.object(
            main,
            "request",
            _FakeRequest(
                {
                    "orientation": "landscape",
                    "background_image": current,
                }
            ),
        ):
            response = asyncio.run(plugin.delete_background())
        self.assertEqual(response["status_code"], 200)
        self.assertIn("主题色未更新", response["body"]["message"])
        self.assertEqual(plugin.config["landscape_background_image"], video)
        self.assertNotIn(current, str(plugin._public_config()))

    def test_svg_safe_animations_preserved_and_actual_unsafe_samples_rejected(self):
        sanitize = media["sanitize_svg"]
        safe = b'<svg xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="g"/></defs><rect fill="url(#g)"><animate attributeName="opacity" values="0;1" dur="2s"/></rect><style>@keyframes pulse {to {opacity:.5}}</style></svg>'
        self.assertIn(b"animate", sanitize(safe))
        unsafe = [
            b'<svg onload="alert(1)"/>',
            b"<svg><foreignObject><div/></foreignObject></svg>",
            b'<svg><image href="https://example.com/img.png"/></svg>',
            b'<svg xml:base="https://example.com/"><use href="#external"/></svg>',
            b'<svg><rect fill="url(relative.png)"/></svg>',
            b'<svg><style>@import "remote.css";</style></svg>',
            b"<svg><style>rect{fill:u\\72l(https://example.com)}</style></svg>",
            b'<svg><animate attributeName="href" values="https://example.com"/></svg>',
            b'<!DOCTYPE svg [<!ENTITY x "boom">]><svg>&x;</svg>',
            b'<?xml-stylesheet href="https://example.com"?><svg/>',
        ]
        for data in unsafe:
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    sanitize(data)

    def test_old_animated_cover_lazy_and_cover_failure_is_explicit(self):
        plugin = self._make_plugin({})
        path = plugin.paths.background_dir / "old.gif"
        path.write_bytes(image_bytes("GIF", animated=True))
        with (
            mock.patch.object(
                main, "request", SimpleNamespace(query={"filename": path.name})
            ),
            mock.patch.object(
                main, "file_response", lambda path, **kw: {"path": path, **kw}
            ),
        ):
            result = asyncio.run(plugin.get_background_cover())
        self.assertTrue(result["path"].is_file())
        video = plugin.paths.background_dir / "old.mp4"
        video.write_bytes((_FIXTURES / "sample.mp4").read_bytes())
        with self.assertRaisesRegex(ValueError, "暂无封面"):
            plugin._with_theme_colors(
                {**plugin._public_config(), "landscape_background_image": video.name},
                force=True,
            )
        cover = media["save_cover_image"](
            Image.new("RGB", (8, 8), "green"), plugin.paths.cover_dir, video.name
        )
        cover.write_bytes(b"broken")
        with self.assertRaisesRegex(ValueError, "封面无法读取"):
            plugin._with_theme_colors(
                {**plugin._public_config(), "landscape_background_image": video.name},
                force=True,
            )
