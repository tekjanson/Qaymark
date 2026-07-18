"""Tests for the drift-be-gone reference bridge."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qaymark import reference_bridge as rb


class ReferenceBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def test_parse_artifact_fields(self) -> None:
        artifact = {
            "summary": "map for demo",
            "synthetic_brief": "3 modules",
            "notable_files": ["a.py", "b.py"],
            "inferred_domains": ["pkg"],
            "graph_nodes": ["a.py", "b.py", "c.py"],
            "graph_edges": [["a.py", "b.py"]],
        }
        result = rb._parse_artifact(artifact)
        self.assertTrue(result.available)
        self.assertEqual(result.node_count, 3)
        self.assertEqual(result.edge_count, 1)
        self.assertEqual(result.domains, ["pkg"])

    def test_feedback_when_available(self) -> None:
        result = rb.ReferenceResult(available=True, summary="s", node_count=2, edge_count=1)
        text = rb.format_reference_feedback(result)
        self.assertIn("drift reference", text)
        self.assertIn("2 nodes", text)

    def test_feedback_when_unavailable(self) -> None:
        text = rb.format_reference_feedback(rb.ReferenceResult(error="not cloned"))
        self.assertIn("unavailable", text)
        self.assertIn("not cloned", text)

    def test_run_map_reads_written_artifact(self) -> None:
        output = self.tmp / "map.json"
        artifact = {"summary": "ok", "graph_nodes": ["x.py"], "graph_edges": []}

        def fake_run(cmd, **kwargs):
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(artifact), encoding="utf-8")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch.object(rb.subprocess, "run", side_effect=fake_run):
            result = rb.run_map(self.tmp, self.tmp, output)
        self.assertTrue(result.available)
        self.assertEqual(result.node_count, 1)

    def test_run_map_reports_failure(self) -> None:
        with mock.patch.object(
            rb.subprocess, "run", return_value=mock.Mock(returncode=1, stdout="", stderr="boom")
        ):
            result = rb.run_map(self.tmp, self.tmp, self.tmp / "m.json")
        self.assertFalse(result.available)
        self.assertIn("boom", result.error)


if __name__ == "__main__":
    unittest.main()
