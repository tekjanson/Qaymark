"""Tests for workspace inspection helpers."""

import tempfile
import unittest
from pathlib import Path

from qaymark.workspace import ensure_sbgignore, iter_files, seed_workspace, summarize_workspace


class WorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def test_iter_files_skips_ignored_dirs(self) -> None:
        (self.root / "keep.py").write_text("x = 1\n", encoding="utf-8")
        junk = self.root / "node_modules"
        junk.mkdir()
        (junk / "dep.js").write_text("y\n", encoding="utf-8")
        names = {p.name for p in iter_files(self.root)}
        self.assertIn("keep.py", names)
        self.assertNotIn("dep.js", names)

    def test_summarize_reports_empty(self) -> None:
        self.assertEqual(summarize_workspace(self.root), "<empty workspace>")

    def test_ensure_sbgignore_is_idempotent(self) -> None:
        ensure_sbgignore(self.root)
        first = (self.root / ".sbgignore").read_text(encoding="utf-8")
        ensure_sbgignore(self.root)
        second = (self.root / ".sbgignore").read_text(encoding="utf-8")
        self.assertEqual(first, second)
        self.assertIn("context/", first)

    def test_seed_workspace_copies_and_reports_paths(self) -> None:
        seed = Path(tempfile.mkdtemp())
        (seed / "tests").mkdir()
        (seed / "tests" / "t.py").write_text("x\n", encoding="utf-8")
        (seed / "TASK.md").write_text("do\n", encoding="utf-8")
        seeded = seed_workspace(self.root, seed)
        self.assertTrue((self.root / "tests" / "t.py").exists())
        self.assertEqual(set(seeded), {"tests/t.py", "TASK.md"})

    def test_seed_workspace_none_is_noop(self) -> None:
        self.assertEqual(seed_workspace(self.root, None), [])


if __name__ == "__main__":
    unittest.main()
