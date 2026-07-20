"""Tests for prompt construction and feedback synthesis."""

import unittest
from pathlib import Path

from qaymark.config import DEFAULT_MANIFEST
from qaymark.hygiene import HygieneResult
from qaymark.reference_bridge import ReferenceResult
from qaymark.operations import OperationOutcome
from qaymark.prompt import (
    build_system_prompt,
    build_user_prompt,
    load_rule_digest,
    synthesize_feedback,
)
from qaymark.report import AttemptReport


class PromptTests(unittest.TestCase):
    def test_system_prompt_states_json_and_limits(self) -> None:
        prompt = build_system_prompt("placeholder-comments, long-lines")
        self.assertIn("JSON", prompt)
        self.assertIn("60 lines", prompt)
        self.assertIn("placeholder-comments", prompt)
        self.assertIn("COMPLETE", prompt)
        self.assertIn("never a partial stub", prompt)
        self.assertIn("fluid and human", prompt)

    def test_user_prompt_includes_task_and_feedback(self) -> None:
        prompt = build_user_prompt("build a parser", "pytest", "<snap>", "fix line 3")
        self.assertIn("build a parser", prompt)
        self.assertIn("fix line 3", prompt)

    def test_rule_digest_reads_real_manifest(self) -> None:
        digest = load_rule_digest(DEFAULT_MANIFEST)
        self.assertIn("python-function-length", digest)
        self.assertIn("ui-flow-completeness", digest)

    def test_rule_digest_handles_missing_manifest(self) -> None:
        digest = load_rule_digest(Path("/nonexistent/manifest.json"))
        self.assertIn("slop-be-gone", digest)


class FeedbackTests(unittest.TestCase):
    def _report(self, ok: bool, violations: list, written: list | None = None) -> AttemptReport:
        hygiene = HygieneResult(passed=not violations, violations=violations)
        outcome = OperationOutcome(written=written or [])
        return AttemptReport(1, ok, "boom", hygiene, ReferenceResult(), outcome)

    def test_feedback_reports_validation_failure(self) -> None:
        text = synthesize_feedback(self._report(False, []))
        self.assertIn("Validation FAILED", text)

    def test_feedback_lists_violations(self) -> None:
        violation = {"rule_id": "long-lines", "path": "a.py", "line": 3, "message": "too long"}
        text = synthesize_feedback(self._report(True, [violation]))
        self.assertIn("long-lines", text)
        self.assertIn("a.py:3", text)
        self.assertIn("COMPLETE corrected file", text)

    def test_feedback_includes_full_written_file_content(self) -> None:
        import tempfile

        root = Path(tempfile.mkdtemp())
        room = root / "control_room.py"
        room.write_text("@dataclass\nclass P:\n    id: str\n", encoding="utf-8")
        text = synthesize_feedback(self._report(False, [], written=["control_room.py"]), root)
        self.assertIn("current full content", text)
        self.assertIn("class P:", text)
        self.assertIn("COMPLETE corrected file", text)


if __name__ == "__main__":
    unittest.main()
