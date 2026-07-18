"""Serve a built workspace as a playable static site.

Only launches once the workspace's validation command passes, so a human is
never handed a broken build. Used to deliver a browser-playable artifact (e.g.
the web Tetris game) on a free local port.
"""

from __future__ import annotations

import socket
import subprocess
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def find_free_port(preferred: int = 8800) -> int:
    """Return *preferred* if free, otherwise an OS-assigned free port."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def validate(workspace: Path, command: str) -> subprocess.CompletedProcess[str]:
    """Run the workspace's validation command and capture the result."""

    return subprocess.run(
        command,
        cwd=workspace,
        shell=True,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def has_entrypoint(workspace: Path, entrypoint: str = "index.html") -> bool:
    return (workspace / entrypoint).is_file()


def build_server(workspace: Path, port: int) -> ThreadingHTTPServer:
    handler = partial(SimpleHTTPRequestHandler, directory=str(workspace))
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def serve(workspace: Path, port: int, entrypoint: str = "index.html") -> str:
    """Start a blocking static server for *workspace*; return the play URL."""

    server = build_server(workspace, port)
    url = f"http://127.0.0.1:{port}/{entrypoint}"
    print(f"▶ play at: {url}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return url
