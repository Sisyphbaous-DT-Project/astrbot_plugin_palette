"""设置页分块上传器的 Node 行为验证入口。"""

from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent.parent


class UploadJavaScriptTest(unittest.TestCase):
    def test_chunked_upload_behavior(self):
        command = [
            "node",
            str(ROOT / "tests/upload_behavior.cjs"),
            str(ROOT / "pages/settings/upload.js"),
        ]
        # 本地参考仓库存在时额外执行真实 bridge；仓库独立运行仍覆盖受控 bridge。
        bridge = ROOT.parent / "tmp/AstrBot/astrbot/dashboard/plugin_page_bridge.js"
        if bridge.is_file():
            command.append(str(bridge))
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("行为验证通过", result.stdout)


if __name__ == "__main__":
    unittest.main()
