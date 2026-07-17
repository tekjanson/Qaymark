"""Tests for safe operation application."""

import tempfile
import unittest
from pathlib import Path

from qaymark.operations import apply_operations, safe_target


class SafeTargetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def test_rejects_absolute_path(self) -> None:
        self.assertIsNone(safe_target(self.root, "/etc/passwd"))

    def test_rejects_parent_traversal(self) -> None:
        self.assertIsNone(safe_target(self.root, "../../etc/passwd"))

    def test_rejects_empty_path(self) -> None:
        self.assertIsNone(safe_target(self.root, ""))

    def test_allows_nested_path(self) -> None:
        target = safe_target(self.root, "a/b/c.py")
        self.assertIsNotNone(target)
        self.assertTrue(str(target).startswith(str(self.root.resolve())))


class ApplyOperationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def test_write_file_from_lines(self) -> None:
        payload = {"operations": [{"kind": "write_file", "path": "m.py", "lines": ["x = 1"]}]}
        outcome = apply_operations(self.root, payload)
        self.assertEqual(outcome.written, ["m.py"])
        self.assertEqual((self.root / "m.py").read_text(encoding="utf-8"), "x = 1\n")

    def test_traversal_write_is_skipped(self) -> None:
        payload = {"operations": [{"kind": "write_file", "path": "../evil.py", "lines": ["x"]}]}
        outcome = apply_operations(self.root, payload)
        self.assertEqual(outcome.written, [])
        self.assertEqual(len(outcome.skipped), 1)

    def test_run_command_disabled_by_default(self) -> None:
        payload = {"operations": [{"kind": "run_command", "command": "touch hacked"}]}
        outcome = apply_operations(self.root, payload, allow_commands=False)
        self.assertFalse((self.root / "hacked").exists())
        self.assertTrue(any("disabled" in note for note in outcome.skipped))

    def test_unknown_kind_is_skipped(self) -> None:
        outcome = apply_operations(self.root, {"operations": [{"kind": "delete", "path": "m"}]})
        self.assertTrue(any("unknown" in note for note in outcome.skipped))

    def test_protected_file_is_not_overwritten(self) -> None:
        spec = self.root / "tests" / "spec.py"
        spec.parent.mkdir()
        spec.write_text("original\n", encoding="utf-8")
        op = {"kind": "write_file", "path": "tests/spec.py", "lines": ["hacked"]}
        guard = frozenset({"tests/spec.py"})
        outcome = apply_operations(self.root, {"operations": [op]}, protected=guard)
        self.assertEqual(spec.read_text(encoding="utf-8"), "original\n")
        self.assertTrue(any("protected" in note for note in outcome.skipped))


if __name__ == "__main__":
    unittest.main()
