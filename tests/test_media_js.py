"""执行最终注入输出及设置页模块的 Node 行为验证。"""

from pathlib import Path
import subprocess
import tempfile
import unittest

from test_rotation_js import _SCRIPT


class MediaJavaScriptTest(unittest.TestCase):
    def test_real_bootstrap_lifecycle_and_import(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as temp:
            script = Path(temp) / "bootstrap.js"
            script.write_text(_SCRIPT, encoding="utf-8")
            result = subprocess.run(
                [
                    "node",
                    str(root / "tests/media_runtime_behavior.cjs"),
                    str(script),
                    str(root),
                ],
                text=True,
                capture_output=True,
                timeout=30,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("行为验证通过", result.stdout)
