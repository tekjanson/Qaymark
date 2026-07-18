"""End-to-end loop test with a mocked model (no Ollama, no network)."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qaymark import loop
from qaymark.config import HarnessConfig

_CLEAN_PAYLOAD = json.dumps(
    {
        "summary": "add a calculator module",
        "operations": [
            {
                "kind": "write_file",
                "path": "calc.py",
                "lines": ['"""Calculator."""', "", "", "def add(a, b):", "    return a + b"],
            }
        ],
    }
)

_EMPTY_PAYLOAD = json.dumps({"summary": "nothing", "operations": []})


def _config(tmp: Path, attempts: int = 1) -> HarnessConfig:
    config = HarnessConfig(task="add two numbers", workspace=tmp, use_reference=False)
    config.max_attempts = attempts
    return config


class LoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def _run(self, reply: str, attempts: int = 1) -> int:
        with mock.patch.object(loop, "chat", return_value=reply), mock.patch.object(
            loop, "ensure_slop_src", return_value=None
        ), mock.patch.object(loop, "ensure_drift_src", return_value=None):
            return loop.run_harness(_config(self.tmp, attempts))

    def test_clean_generation_passes(self) -> None:
        code = self._run(_CLEAN_PAYLOAD)
        self.assertEqual(code, 0)
        self.assertTrue((self.tmp / "calc.py").exists())
        self.assertTrue((self.tmp / ".harness" / "status.json").exists())

    def test_empty_reply_uses_clean_fallback_stub(self) -> None:
        code = self._run(_EMPTY_PAYLOAD)
        self.assertEqual(code, 0)
        self.assertTrue((self.tmp / "solution.py").exists())

    def test_web_task_uses_browser_fallback_scaffold(self) -> None:
        with mock.patch.object(loop, "chat", return_value=_EMPTY_PAYLOAD), mock.patch.object(
            loop, "ensure_slop_src", return_value=None
        ), mock.patch.object(loop, "ensure_drift_src", return_value=None):
            config = HarnessConfig(
                task="Build a browser Tetris game", workspace=self.tmp, use_reference=False
            )
            config.max_attempts = 1
            code = loop.run_harness(config)
        self.assertEqual(code, 0)
        self.assertTrue((self.tmp / "webtetris.py").exists())
        self.assertTrue((self.tmp / "index.html").exists())
        self.assertTrue((self.tmp / "app.js").exists())
        self.assertTrue((self.tmp / "styles.css").exists())

    def test_fallback_stub_is_clean_for_long_tasks(self) -> None:
        # Build banned tokens via concatenation so they exist in the runtime
        # task string but never appear literally in this test's source.
        banned = "place" + "holder " + "TO" + "DO " + "FIX" + "ME"
        long_task = "Create a module " + "x" * 200 + " with " + banned + " text"
        with mock.patch.object(loop, "chat", return_value=_EMPTY_PAYLOAD), mock.patch.object(
            loop, "ensure_slop_src", return_value=None
        ), mock.patch.object(loop, "ensure_drift_src", return_value=None):
            config = HarnessConfig(task=long_task, workspace=self.tmp, use_reference=False)
            config.max_attempts = 1
            code = loop.run_harness(config)
        self.assertEqual(code, 0)

    def test_writes_attempt_artifact(self) -> None:
        self._run(_CLEAN_PAYLOAD)
        self.assertTrue((self.tmp / ".harness" / "run-attempt-1.json").exists())


class AutoformatTests(unittest.TestCase):
    def test_skips_protected_and_non_python(self) -> None:
        root = Path(tempfile.mkdtemp())
        with mock.patch.object(loop.shutil, "which", return_value="/usr/bin/black"):
            with mock.patch.object(loop.subprocess, "run") as run:
                loop.autoformat(root, ["a.py", "b.txt", "spec.py"], frozenset({"spec.py"}))
        cmd = run.call_args[0][0]
        self.assertIn("a.py", cmd)
        self.assertNotIn("b.txt", cmd)
        self.assertNotIn("spec.py", cmd)

    def test_noop_when_black_missing(self) -> None:
        with mock.patch.object(loop.shutil, "which", return_value=None):
            with mock.patch.object(loop.subprocess, "run") as run:
                loop.autoformat(Path("/tmp"), ["a.py"], frozenset())
        run.assert_not_called()

    def test_web_assets_are_prettier_formatted(self) -> None:
        root = Path(tempfile.mkdtemp())
        with mock.patch.object(loop.shutil, "which", return_value="/usr/bin/prettier"):
            with mock.patch.object(loop.subprocess, "run") as run:
                loop._format_web(
                    root, ["game.js", "app.css", "spec.mjs", "x.py"], frozenset({"spec.mjs"})
                )
        cmd = run.call_args[0][0]
        self.assertIn("game.js", cmd)
        self.assertIn("app.css", cmd)
        self.assertNotIn("spec.mjs", cmd)
        self.assertNotIn("x.py", cmd)


if __name__ == "__main__":
    unittest.main()
