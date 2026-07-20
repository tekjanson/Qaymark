"""Tests for the streaming Ollama client and the live-generation file."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qaymark import loop, ollama_client
from qaymark.config import HarnessConfig


def _ndjson(chunks: list[str]) -> io.BytesIO:
    lines = [json.dumps({"message": {"content": c}}) for c in chunks]
    lines.append(json.dumps({"done": True}))
    return io.BytesIO("\n".join(lines).encode("utf-8"))


class StreamingClientTests(unittest.TestCase):
    def test_stream_accumulates_and_emits_deltas(self) -> None:
        seen: list[str] = []
        response = _ndjson(["Hel", "lo ", "world"])
        response.__enter__ = lambda: response  # type: ignore[attr-defined]
        response.__exit__ = lambda *a: False  # type: ignore[attr-defined]
        with mock.patch.object(ollama_client.urllib.request, "urlopen", return_value=response):
            text = ollama_client.chat("sys", "user", "m", "http://x", on_delta=seen.append)
        self.assertEqual(text, "Hello world")
        self.assertEqual(seen, ["Hel", "lo ", "world"])


class LiveGenerationFileTests(unittest.TestCase):
    def test_generate_writes_live_file_and_marks_done(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        config = HarnessConfig(task="add numbers", workspace=tmp, use_reference=False)
        payload = json.dumps({"summary": "x", "operations": [
            {"kind": "write_file", "path": "a.py", "lines": ["x = 1"]}]})

        def fake_chat(system, user, model, base_url, on_delta=None):
            if on_delta:
                on_delta(payload)
            return payload

        with mock.patch.object(loop, "ollama_chat", side_effect=fake_chat):
            result = loop._generate(config, "system", "user")
        self.assertTrue(result["operations"])
        live = tmp / ".harness" / "generation.txt"
        state = tmp / ".harness" / "generation.state"
        self.assertEqual(live.read_text(encoding="utf-8"), payload)
        self.assertEqual(state.read_text(encoding="utf-8"), "done")


if __name__ == "__main__":
    unittest.main()
