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
        self.framework = fw.Framework(
            "demo", "demo", "d", self.path, "https://example/demo", "demo-domain", "demo-scope"
        )
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

    def test_add_rule_appends_and_persists(self) -> None:
        view = fw.add_rule("demo", {"id": "new-rule", "type": "long-lines", "enabled": True})
        self.assertEqual(view["id"], "new-rule")
        reloaded = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(len(reloaded["rules"]), 2)

    def test_add_rule_rejects_duplicate_id(self) -> None:
        with self.assertRaises(ValueError):
            fw.add_rule("demo", {"id": "demo-rule", "type": "long-lines"})

    def test_add_rule_requires_type(self) -> None:
        with self.assertRaises(ValueError):
            fw.add_rule("demo", {"id": "no-type"})

    def test_delete_rule(self) -> None:
        fw.add_rule("demo", {"id": "temp", "type": "long-lines"})
        result = fw.delete_rule("demo", "temp")
        self.assertEqual(result["deleted"], "temp")
        ids = [r["id"] for r in json.loads(self.path.read_text(encoding="utf-8"))["rules"]]
        self.assertNotIn("temp", ids)

    def test_delete_unknown_rule_raises(self) -> None:
        with self.assertRaises(KeyError):
            fw.delete_rule("demo", "ghost")

    def test_replace_manifest_with_valid_payload(self) -> None:
        new = {"version": 2, "rules": [{"id": "only", "type": "empty-files"}]}
        fw.replace_manifest("demo", new)
        reloaded = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(reloaded["version"], 2)
        self.assertEqual(reloaded["rules"][0]["id"], "only")

    def test_replace_manifest_rejects_invalid(self) -> None:
        with self.assertRaises(ValueError):
            fw.replace_manifest("demo", {"rules": [{"type": "no-id"}]})

    def test_raw_manifest_is_pretty_json(self) -> None:
        raw = fw.raw_manifest("demo")
        self.assertIn("demo-rule", raw)
        self.assertEqual(json.loads(raw)["rules"][0]["id"], "demo-rule")


class ValidateManifestTests(unittest.TestCase):
    def test_valid_manifest(self) -> None:
        manifest = {"rules": [{"id": "a", "type": "long-lines"}]}
        self.assertEqual(fw.validate_manifest(manifest), [])

    def test_missing_rules_array(self) -> None:
        self.assertTrue(fw.validate_manifest({"nope": 1}))

    def test_duplicate_ids_flagged(self) -> None:
        manifest = {"rules": [{"id": "a", "type": "x"}, {"id": "a", "type": "y"}]}
        problems = fw.validate_manifest(manifest)
        self.assertTrue(any("duplicate" in p for p in problems))


class RealManifestTests(unittest.TestCase):
    def test_all_frameworks_load(self) -> None:
        data = fw.list_frameworks()
        ids = {f["id"] for f in data}
        self.assertEqual(ids, {"slop-be-gone", "design-be-gone", "chaos-be-gone", "drift-be-gone"})
        for framework in data:
            self.assertGreater(framework["rule_count"], 0)
            self.assertTrue(framework["domain"])
            self.assertTrue(framework["scope"])

    def test_ui_flow_completeness_rule_is_present(self) -> None:
        manifest = fw.read_manifest("design-be-gone")
        ids = {rule["id"] for rule in manifest["rules"]}
        self.assertIn("ui-flow-completeness-design", ids)

    def test_cluster_has_no_overlap(self) -> None:
        # Vibing governance: slop owns single-file hygiene, drift owns
        # cross-module architecture; no framework may blur into another.
        self.assertEqual(fw.check_overlap(), [])

    def test_overlap_detected_when_domains_collide(self) -> None:
        clone = fw.Framework("dup", "dup", "d", fw.FRAMEWORKS[0].manifest, "u", "hygiene", "other")
        with mock.patch.object(fw, "FRAMEWORKS", fw.FRAMEWORKS + (clone,)):
            problems = fw.check_overlap()
        self.assertTrue(any("domain 'hygiene'" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
