"""Tests that the shipped hygiene manifest is well-formed."""

import importlib.util
import json
import unittest

from qaymark.config import DEFAULT_MANIFEST


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))

    def test_is_valid_json_with_rules(self) -> None:
        self.assertIn("rules", self.manifest)
        self.assertGreaterEqual(len(self.manifest["rules"]), 25)

    def test_every_rule_has_id_and_type(self) -> None:
        for rule in self.manifest["rules"]:
            self.assertTrue(rule.get("id"))
            self.assertTrue(rule.get("type"))

    def test_rule_ids_are_unique(self) -> None:
        ids = [rule["id"] for rule in self.manifest["rules"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_complexity_rules_are_errors(self) -> None:
        by_id = {rule["id"]: rule for rule in self.manifest["rules"]}
        for rule_id in ("python-function-length", "python-function-args", "python-nesting-depth"):
            self.assertEqual(by_id[rule_id].get("severity"), "error")

    @unittest.skipUnless(importlib.util.find_spec("sbg"), "sbg not installed")
    def test_validates_against_real_engine(self) -> None:
        from sbg.engine import validate_manifest

        self.assertEqual(validate_manifest(self.manifest), [])


if __name__ == "__main__":
    unittest.main()
