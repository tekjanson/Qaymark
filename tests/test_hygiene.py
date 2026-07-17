"""Tests for the degraded fallback hygiene scanner."""

import tempfile
import unittest
from pathlib import Path

from qaymark.hygiene import fallback_scan, format_hygiene_feedback
from qaymark.workspace import iter_files


class FallbackScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def _scan(self) -> list:
        return fallback_scan(self.root, iter_files(self.root)).violations

    def test_clean_file_passes(self) -> None:
        (self.root / "ok.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        result = fallback_scan(self.root, iter_files(self.root))
        self.assertTrue(result.passed)
        self.assertTrue(result.degraded)

    def test_detects_trailing_whitespace(self) -> None:
        (self.root / "bad.py").write_text("x = 1 \n", encoding="utf-8")
        rules = {v["rule_id"] for v in self._scan()}
        self.assertIn("trailing-whitespace", rules)

    def test_detects_missing_final_newline(self) -> None:
        (self.root / "bad.py").write_text("x = 1", encoding="utf-8")
        rules = {v["rule_id"] for v in self._scan()}
        self.assertIn("final-newline", rules)

    def test_detects_python_syntax_error(self) -> None:
        (self.root / "broken.py").write_text("def f(:\n    pass\n", encoding="utf-8")
        rules = {v["rule_id"] for v in self._scan()}
        self.assertIn("python-syntax", rules)


class FeedbackFormatTests(unittest.TestCase):
    def test_no_violations_message(self) -> None:
        from qaymark.hygiene import HygieneResult

        text = format_hygiene_feedback(HygieneResult(passed=True))
        self.assertIn("no violations", text.lower())


if __name__ == "__main__":
    unittest.main()
