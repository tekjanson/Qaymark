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

    def test_contract_test_files_are_shown_in_full(self) -> None:
        long_test = "\n".join(f"assert x == {i}" for i in range(120))
        (self.root / "test_thing.py").write_text(long_test + "\n", encoding="utf-8")
        (self.root / "thing.py").write_text("\n".join(f"a{i} = {i}" for i in range(120)) + "\n",
                                            encoding="utf-8")
        snap = summarize_workspace(self.root)
        # The acceptance test is the contract → shown in full (all 120 lines).
        self.assertIn("contract — full", snap)
        self.assertIn("assert x == 119", snap)
        # A regular source file is still previewed/truncated.
        self.assertIn("more lines)", snap)
        self.assertNotIn("a119 = 119", snap)

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
