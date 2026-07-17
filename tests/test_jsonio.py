"""Tests for JSON payload extraction."""

import unittest

from qaymark.jsonio import extract_json_payload


class ExtractJsonTests(unittest.TestCase):
    def test_parses_raw_object(self) -> None:
        payload = extract_json_payload('{"summary": "ok", "operations": []}')
        self.assertEqual(payload["summary"], "ok")

    def test_parses_fenced_block(self) -> None:
        text = "Here you go:\n```json\n{\"operations\": [1]}\n```\nDone."
        self.assertEqual(extract_json_payload(text)["operations"], [1])

    def test_parses_from_surrounding_prose(self) -> None:
        text = 'prose before {"summary": "x", "operations": []} prose after'
        self.assertEqual(extract_json_payload(text)["summary"], "x")

    def test_raises_when_no_json(self) -> None:
        with self.assertRaises(ValueError):
            extract_json_payload("no json here at all")


if __name__ == "__main__":
    unittest.main()
