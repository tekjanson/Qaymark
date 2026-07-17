#!/usr/bin/env python3
"""Serve a signed-in overview dashboard for one or more Qaymark workspaces."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import html
import json
import os
import time
from dataclasses import dataclass
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

COOKIE_NAME = "qaymark_session"
COOKIE_TTL = 60 * 60 * 12


HTML_SHELL = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Qaymark Control Plane</title>
    <style>
      body { margin: 0; font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; }
      main { max-width: 1300px; margin: 0 auto; padding: 24px; display: grid; gap: 16px; }
      .card { background: #111827; border: 1px solid #334155; border-radius: 16px; padding: 16px; }
      pre {
        white-space: pre-wrap;
        word-break: break-word;
        background: #020617;
        padding: 12px;
        border-radius: 12px;
        overflow: auto;
      }
      a { color: #93c5fd; }
      table { width: 100%; border-collapse: collapse; }
      th, td {
        padding: 8px;
        border-bottom: 1px solid #334155;
        text-align: left;
        vertical-align: top;
      }
      .muted { color: #94a3b8; }
      .ok { color: #86efac; }
      .bad { color: #fca5a5; }
      .grid {
        display: grid;
        gap: 16px;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      }
      .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
      input, button {
        border-radius: 10px;
        border: 1px solid #334155;
        padding: 10px 12px;
        font: inherit;
      }
      button { background: #8b5cf6; color: white; cursor: pointer; }
      .login { max-width: 420px; margin: 80px auto; }
      .small { font-size: 0.9rem; }
    </style>
  </head>
  <body>
    <main>
      <section class="card">
        <div class="row">
          <h1 style="margin:0">Qaymark Control Plane</h1>
          <a href="/logout" class="small">Sign out</a>
        </div>
        <div id="meta" class="muted">Loading...</div>
      </section>
      <section class="card">
        <h2>Global view</h2>
        <div id="summary" class="muted">Loading...</div>
      </section>
      <section class="card">
        <h2>Workspaces</h2>
        <div id="workspaces" class="muted">Loading...</div>
      </section>
      <section class="card">
        <h2>Feedback</h2>
        <p class="muted">Leave a note here and the next harness attempt will read it.</p>
        <div class="row">
          <select id="feedback-workspace"></select>
          <button id="feedback-send" type="button">Send feedback</button>
        </div>
        <textarea id="feedback-text" rows="6" style="width:100%;margin-top:10px"></textarea>
        <div id="feedback-status" class="muted"></div>
      </section>
      <section class="card">
        <h2>Raw status</h2>
        <pre id="status">Waiting for data...</pre>
      </section>
    </main>
    <script>
      async function refresh() {
        const res = await fetch('/api/overview.json', { cache: 'no-store' });
        const data = await res.json();
        const meta = [
          `Root: ${data.root || 'unknown'}`,
          `Signed in as: ${data.user || 'unknown'}`,
          `Workspaces: ${data.counts.total}`,
          `Running: ${data.counts.running}`,
          `Passed: ${data.counts.passed}`,
          `Failed: ${data.counts.failed}`,
        ].join(' | ');
        document.getElementById('meta').textContent = meta;
        const card = (value, label, cls) =>
          `<div class="card"><strong class="${cls}">${value}</strong>`
          + `<div class="muted">${label}</div></div>`;
        document.getElementById('summary').innerHTML = [
          '<div class="grid">',
          card(data.counts.total, 'workspaces', ''),
          card(data.counts.passed, 'passed', 'ok'),
          card(data.counts.failed, 'failed', 'bad'),
          card(data.counts.running, 'running', ''),
          '</div>',
        ].join('');
        document.getElementById('status').textContent = JSON.stringify(data, null, 2);
        const selector = document.getElementById('feedback-workspace');
        if (!selector.dataset.loaded) {
          const options = data.workspaces.map(
            (item) => `<option value="${item.name}">${item.name}</option>`
          );
          selector.innerHTML = ['<option value="">Global feedback</option>']
            .concat(options)
            .join('');
          selector.dataset.loaded = '1';
        }
        if (!data.workspaces.length) {
          document.getElementById('workspaces').innerHTML =
            '<span class="muted">No workspaces with harness status found yet.</span>';
          return;
        }
        const rows = data.workspaces.map((item) => {
          const validation = item.validation_ok
            ? '<span class="ok">passed</span>'
            : '<span class="bad">failed</span>';
          const hygiene = item.hygiene_passed
            ? '<span class="ok">passed</span>'
            : '<span class="bad">failed</span>';
          return [
            '<tr>',
            `<td><a href="${item.link}">${item.name}</a></td>`,
            `<td>${item.phase}</td>`,
            `<td>${item.attempt}</td>`,
            `<td>${validation}</td>`,
            `<td>${hygiene}</td>`,
            `<td>${item.summary || ''}</td>`,
            '</tr>',
          ].join('');
        }).join('');
        document.getElementById('workspaces').innerHTML = [
          '<table>',
          '<thead><tr><th>Workspace</th><th>Phase</th><th>Attempt</th>'
          + '<th>Validation</th><th>Hygiene</th><th>Summary</th></tr></thead>',
          '<tbody>',
          rows,
          '</tbody></table>',
        ].join('');
      }
      async function sendFeedback() {
        const workspace = document.getElementById('feedback-workspace').value;
        const message = document.getElementById('feedback-text').value.trim();
        const status = document.getElementById('feedback-status');
        if (!message) {
          status.textContent = 'Write feedback first.';
          return;
        }
        const body = new URLSearchParams({ workspace, message });
        const res = await fetch('/api/feedback', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body,
        });
        const saved = 'Saved. The next harness attempt will read it.';
        status.textContent = res.ok ? saved : 'Failed to save feedback.';
        if (res.ok) {
          document.getElementById('feedback-text').value = '';
        }
      }
      document.getElementById('feedback-send').addEventListener('click', sendFeedback);
      refresh();
      setInterval(refresh, 2000);
    </script>
  </body>
</html>
"""


LOGIN_SHELL = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Qaymark Sign In</title>
    <style>
      body { margin: 0; font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; }
      main { max-width: 420px; margin: 96px auto; padding: 24px; }
      .card { background: #111827; border: 1px solid #334155; border-radius: 16px; padding: 20px; }
      input, button {
        width: 100%;
        box-sizing: border-box;
        margin-top: 10px;
        border-radius: 10px;
        border: 1px solid #334155;
        padding: 10px 12px;
        font: inherit;
      }
      button { background: #8b5cf6; color: white; cursor: pointer; }
      .muted { color: #94a3b8; }
      .error { color: #fca5a5; min-height: 1.25rem; }
    </style>
  </head>
  <body>
    <main>
      <section class="card">
        <h1>Qaymark Sign In</h1>
        <p class="muted">One sign-in unlocks the full factory control plane.</p>
        <div class="error">{error}</div>
        <form method="post" action="/login">
          <input name="username" autocomplete="username" placeholder="Username"
                 value="{username}">
          <input name="password" type="password" autocomplete="current-password"
                 placeholder="Password">
          <button type="submit">Sign in</button>
        </form>
      </section>
    </main>
  </body>
</html>
"""


@dataclass
class WorkspaceStatus:
    path: Path
    name: str
    phase: str
    attempt: int
    max_attempts: int
    validation_ok: bool
    hygiene_passed: bool
    summary: str
    link: str


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _secret() -> bytes:
    value = _env("DASHBOARD_SECRET")
    if value:
        return value.encode("utf-8")
    return _env("DASHBOARD_PASSWORD", "qaymark").encode("utf-8")


def _user() -> str:
    return _env("DASHBOARD_USER", "admin")


def _password() -> str:
    return _env("DASHBOARD_PASSWORD", "qaymark")


def _token(username: str) -> str:
    ts = str(int(time.time()))
    payload = f"{username}:{ts}"
    sig = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    raw = f"{payload}:{sig}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _verify_token(value: str) -> str | None:
    try:
        raw = base64.urlsafe_b64decode(value.encode("ascii")).decode("utf-8")
        username, ts, sig = raw.split(":", 2)
        payload = f"{username}:{ts}"
        expected = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        if int(ts) + COOKIE_TTL < int(time.time()):
            return None
        if username != _user():
            return None
        return username
    except (ValueError, UnicodeError):
        return None


def _cookie_value(headers: dict[str, str]) -> str | None:
    raw = headers.get("Cookie", "")
    for part in raw.split(";"):
        name, _, value = part.strip().partition("=")
        if name == COOKIE_NAME:
            return value
    return None


def _authed(headers: dict[str, str]) -> str | None:
    token = _cookie_value(headers)
    if not token:
        return None
    return _verify_token(token)


def _discover_workspaces(root: Path) -> list[Path]:
    if (root / ".harness" / "status.json").exists():
        return [root]
    return sorted(
        path.parent.parent for path in root.rglob("status.json") if path.parent.name == ".harness"
    )


def _latest_attempt(workspace: Path) -> dict:
    files = sorted(workspace.joinpath(".harness").glob("run-attempt-*.json"))
    if not files:
        return {}
    data = _read_json(files[-1], {})
    return data if isinstance(data, dict) else {}


def _latest_attempt_summary(workspace: Path) -> str:
    return str(_latest_attempt(workspace).get("summary", ""))


def _feedback_file(workspace: Path) -> Path:
    return workspace / ".harness" / "feedback.txt"


def _latest_feedback(workspace: Path) -> str:
    path = _feedback_file(workspace)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _append_feedback(workspace: Path, username: str, message: str) -> None:
    text = message.strip()
    if not text:
        return
    path = _feedback_file(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    block = f"[{stamp}] {username}\n{text}\n\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(block)


def _load_workspace(workspace: Path, root: Path) -> WorkspaceStatus:
    data = _read_json(workspace / ".harness" / "status.json", {"phase": "idle"})
    latest = _latest_attempt(workspace)
    phase = str(data.get("phase", "idle"))
    attempt = int(data.get("attempt") or 0)
    max_attempts = int(data.get("max_attempts") or 0)
    # Status snapshots for idle phases (e.g. "watching") omit gate results, so
    # fall back to the last recorded attempt to keep the row accurate.
    validation_ok = bool(data.get("validation_ok", latest.get("validation_ok")))
    hygiene_passed = bool(data.get("hygiene_passed", latest.get("hygiene_passed")))
    summary = str(latest.get("summary", ""))
    feedback = _latest_feedback(workspace)
    rel = workspace.relative_to(root).as_posix()
    link = f"/workspace/{rel}" if rel != "." else "/workspace"
    return WorkspaceStatus(
        path=workspace,
        name=rel if rel != "." else workspace.name,
        phase=phase,
        attempt=attempt,
        max_attempts=max_attempts,
        validation_ok=validation_ok,
        hygiene_passed=hygiene_passed,
        summary=summary,
        link=link,
    )


def overview(root: Path, username: str) -> dict[str, object]:
    workspaces = [_load_workspace(workspace, root) for workspace in _discover_workspaces(root)]
    active = {"starting", "attempting", "retrying", "watching", "reverted"}
    counts = {
        "total": len(workspaces),
        "running": sum(item.phase in active for item in workspaces),
        "passed": sum(item.validation_ok and item.hygiene_passed for item in workspaces),
        "failed": sum(item.phase == "failed" for item in workspaces),
    }
    return {
        "root": str(root),
        "user": username,
        "counts": counts,
        "workspaces": [
            {
                "name": item.name,
                "phase": item.phase,
                "attempt": (
                    f"{item.attempt}/{item.max_attempts}" if item.max_attempts else item.attempt
                ),
                "validation_ok": item.validation_ok,
                "hygiene_passed": item.hygiene_passed,
                "summary": item.summary,
                "feedback": _latest_feedback(item.path),
                "link": item.link,
            }
            for item in workspaces
        ],
    }


def _login_page(error: str = "", username: str = "") -> bytes:
    return (
        LOGIN_SHELL.replace("{error}", html.escape(error))
        .replace("{username}", html.escape(username))
        .encode("utf-8")
    )


def _parse_form(body: bytes) -> dict[str, str]:
    decoded = body.decode("utf-8")
    parsed = parse_qs(decoded, keep_blank_values=True)
    return {key: values[0] for key, values in parsed.items() if values}


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, root: Path, **kwargs):
        self.root = root
        super().__init__(*args, directory=str(root), **kwargs)

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _require_auth(self) -> str | None:
        return _authed(dict(self.headers))

    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path
        if path == "/logout":
            body = b""
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header(
                "Set-Cookie", f"{COOKIE_NAME}=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax"
            )
            self.send_header("Location", "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            self.wfile.write(body)
            return

        username = self._require_auth()
        if username is None:
            body = _login_page()
            self._send(HTTPStatus.OK, "text/html; charset=utf-8", body)
            return

        if path in {"/", "/dashboard"}:
            self._send(HTTPStatus.OK, "text/html; charset=utf-8", HTML_SHELL.encode("utf-8"))
            return
        if path == "/api/overview.json":
            body = json.dumps(overview(self.root, username), indent=2).encode("utf-8")
            self._send(HTTPStatus.OK, "application/json; charset=utf-8", body)
            return
        if path.startswith("/workspace/"):
            rel = path.removeprefix("/workspace/").strip("/")
            target = (self.root / rel).resolve()
            if self.root.resolve() not in target.parents and target != self.root.resolve():
                self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"not found")
                return
            body = _workspace_page(target).encode("utf-8")
            self._send(HTTPStatus.OK, "text/html; charset=utf-8", body)
            return
        return super().do_GET()

    def do_POST(self):  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/feedback":
            username = self._require_auth()
            if username is None:
                self._send(HTTPStatus.UNAUTHORIZED, "text/plain; charset=utf-8", b"login required")
                return
            size = int(self.headers.get("Content-Length", "0"))
            form = _parse_form(self.rfile.read(size))
            rel = form.get("workspace", "")
            message = form.get("message", "")
            target = self.root if not rel else (self.root / rel).resolve()
            if self.root.resolve() not in target.parents and target != self.root.resolve():
                self._send(
                    HTTPStatus.BAD_REQUEST, "text/plain; charset=utf-8", b"invalid workspace"
                )
                return
            _append_feedback(target, username, message)
            self._send(HTTPStatus.OK, "application/json; charset=utf-8", b'{"ok": true}')
            return
        if path != "/login":
            self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"not found")
            return
        size = int(self.headers.get("Content-Length", "0"))
        form = _parse_form(self.rfile.read(size))
        username = form.get("username", "")
        password = form.get("password", "")
        if username == _user() and password == _password():
            token = _token(username)
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Set-Cookie", f"{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax")
            self.send_header("Location", "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = _login_page("Invalid username or password.", username)
        self._send(HTTPStatus.UNAUTHORIZED, "text/html; charset=utf-8", body)


def _workspace_page(workspace: Path) -> str:
    data = _read_json(workspace / ".harness" / "status.json", {"phase": "idle"})
    attempts = []
    for path in sorted(workspace.joinpath(".harness").glob("run-attempt-*.json")):
        attempts.append(_read_json(path, {}))
    return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Workspace</title>
  </head>
  <body>
    <pre>{body}</pre>
  </body>
</html>
""".format(body=html.escape(json.dumps({"status": data, "attempts": attempts}, indent=2)))


def _default_password_notice() -> None:
    if _env("DASHBOARD_PASSWORD"):
        return
    raise SystemExit("Set DASHBOARD_PASSWORD to enable the signed-in control plane.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve a signed-in Qaymark control plane")
    parser.add_argument("root", help="Workspace or parent directory to inspect")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on")
    args = parser.parse_args()

    _default_password_notice()
    root = Path(args.root).expanduser().resolve()
    handler = partial(DashboardHandler, root=root)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"dashboard: http://127.0.0.1:{args.port}", flush=True)
    print(f"root: {root}", flush=True)
    print(f"user: {_user()}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
