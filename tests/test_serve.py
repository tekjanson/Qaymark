"""Tests for the playable-workspace server."""

from __future__ import annotations

import socket
import tempfile
import unittest
from pathlib import Path

from qaymark import serve


class ServeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def test_find_free_port_prefers_available(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            free = probe.getsockname()[1]
        # the probe is closed after the block, so the port is free again
        self.assertEqual(serve.find_free_port(free), free)

    def test_find_free_port_falls_back_when_taken(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
            taken.bind(("127.0.0.1", 0))
            taken.listen()
            busy = taken.getsockname()[1]
            chosen = serve.find_free_port(busy)
        self.assertNotEqual(chosen, busy)
        self.assertGreater(chosen, 0)

    def test_has_entrypoint(self) -> None:
        self.assertFalse(serve.has_entrypoint(self.tmp))
        (self.tmp / "index.html").write_text("<h1>hi</h1>", encoding="utf-8")
        self.assertTrue(serve.has_entrypoint(self.tmp))

    def test_validate_reports_exit_code(self) -> None:
        ok = serve.validate(self.tmp, "true")
        self.assertEqual(ok.returncode, 0)
        bad = serve.validate(self.tmp, "false")
        self.assertNotEqual(bad.returncode, 0)

    def test_build_server_binds_and_serves(self) -> None:
        (self.tmp / "index.html").write_text("<h1>play</h1>", encoding="utf-8")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        server = serve.build_server(self.tmp, port)
        try:
            self.assertEqual(server.server_address[1], port)
        finally:
            server.server_close()


if __name__ == "__main__":
    unittest.main()
