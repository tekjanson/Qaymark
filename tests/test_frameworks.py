"""Tests for the be-gone frameworks governance layer."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qaymark import frameworks as fw


class FrameworksTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        manifest = {
            "version": 1,
            "rules": [
                {
                    "id": "demo-rule",
                    "type": "demo-rule",
                    "enabled": True,
                    "severity": "error",
                    "description": "d",
                    "what": "w",
                    "why": "y",
                    "max_lines": 45,
                }
            ],
        }
        self.path = self.tmp / "demo.json"
        self.path.write_text(json.dumps(manifest), encoding="utf-8")
        self.framework = fw.Framework("demo", "demo", "d", self.path, "https://example/demo")
        self._patch = mock.patch.object(fw, "_BY_ID", {"demo": self.framework})
        self._patch.start()

    def tearDown(self) -> None:
        self._patch.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_read_manifest(self) -> None:
        manifest = fw.read_manifest("demo")
        self.assertEqual(manifest["rules"][0]["id"], "demo-rule")

    def test_unknown_framework_raises(self) -> None:
        with self.assertRaises(KeyError):
            fw.read_manifest("nope")

    def test_update_severity_persists(self) -> None:
        view = fw.update_rule("demo", "demo-rule", {"severity": "warning"})
        self.assertEqual(view["severity"], "warning")
        reloaded = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(reloaded["rules"][0]["severity"], "warning")

    def test_update_numeric_coerces_int(self) -> None:
        view = fw.update_rule("demo", "demo-rule", {"max_lines": "30"})
        self.assertEqual(view["config"]["max_lines"], 30)
        self.assertIsInstance(view["config"]["max_lines"], int)

    def test_update_toggle_enabled(self) -> None:
        view = fw.update_rule("demo", "demo-rule", {"enabled": False})
        self.assertFalse(view["enabled"])

    def test_invalid_severity_rejected(self) -> None:
        with self.assertRaises(ValueError):
            fw.update_rule("demo", "demo-rule", {"severity": "loud"})

    def test_uneditable_field_rejected(self) -> None:
        with self.assertRaises(ValueError):
            fw.update_rule("demo", "demo-rule", {"type": "other"})

    def test_unknown_rule_rejected(self) -> None:
        with self.assertRaises(KeyError):
            fw.update_rule("demo", "ghost", {"enabled": False})


class RealManifestTests(unittest.TestCase):
    def test_all_frameworks_load(self) -> None:
        data = fw.list_frameworks()
        ids = {f["id"] for f in data}
        self.assertEqual(ids, {"slop-be-gone", "design-be-gone", "chaos-be-gone"})
        for framework in data:
            self.assertGreater(framework["rule_count"], 0)


if __name__ == "__main__":
    unittest.main()
