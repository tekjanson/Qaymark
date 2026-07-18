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
import sys
import time
from dataclasses import dataclass
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qaymark import frameworks as fw  # noqa: E402  (path set up above)

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
          <span class="small"><a href="/governance">Governance</a> &middot;
            <a href="/logout">Sign out</a></span>
        </div>
        <div id="meta" class="muted">Loading...</div>
      </section>
      <section class="card">
        <h2>Global view</h2>
        <div id="summary" class="muted">Loading...</div>
      </section>
      <section class="card">
        <div class="row" style="justify-content:space-between">
          <h2 style="margin:0">Governance</h2>
          <a href="/governance">Open drill-down &rarr;</a>
        </div>
        <p class="muted">The be-gone frameworks that gate every build.</p>
        <div id="governance" class="muted">Loading...</div>
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
            `<td><a href="${item.console}">${item.name}</a></td>`,
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
      async function loadGovernance() {
        const res = await fetch('/api/frameworks.json', { cache: 'no-store' });
        const data = await res.json();
        const cards = data.frameworks.map((f) =>
          `<a class="card" href="/governance" style="text-decoration:none;color:inherit">`
          + `<strong>${f.name}</strong>`
          + `<div class="muted">${f.enabled_count}/${f.rule_count} rules enabled</div>`
          + `<div class="muted" style="font-size:0.85rem">${f.description}</div></a>`
        ).join('');
        document.getElementById('governance').innerHTML = '<div class="grid">' + cards + '</div>';
      }
      loadGovernance();
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


CONSOLE_SHELL = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Qaymark Console</title>
    <style>
      body { margin: 0; font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; }
      main { max-width: 1300px; margin: 0 auto; padding: 20px; display: grid; gap: 16px; }
      .card { background: #111827; border: 1px solid #334155; border-radius: 16px; padding: 16px; }
      .cols { display: grid; gap: 16px; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
      a { color: #93c5fd; }
      h1, h2 { margin: 0 0 8px; }
      iframe { width: 100%; height: 680px; border: 0; border-radius: 12px; background: #020617; }
      textarea { width: 100%; box-sizing: border-box; border-radius: 10px; border: 1px solid
        #334155; padding: 10px; font: inherit; background: #0b1220; color: inherit; }
      button { border: 0; border-radius: 10px; padding: 10px 12px; font: inherit;
        background: #8b5cf6; color: white; cursor: pointer; margin-top: 8px; }
      .muted { color: #94a3b8; }
      .ok { color: #86efac; }
      .bad { color: #fca5a5; }
      .pill { display: inline-block; padding: 2px 10px; border-radius: 999px;
        border: 1px solid #334155; margin-right: 6px; }
      ul { margin: 8px 0 0; padding-left: 18px; }
      .note { min-height: 1.1rem; }
    </style>
  </head>
  <body>
    <main>
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <h1 id="title">Qaymark Console</h1>
          <a href="/">Back to overview</a>
        </div>
        <div id="status" class="muted">Loading...</div>
      </div>
      <div class="cols">
        <div class="card">
          <h2>Live preview</h2>
          <div id="preview-wrap" class="muted">No preview for this workspace.</div>
        </div>
        <div>
          <div class="card">
            <h2>Say what you don't like</h2>
            <p class="muted">Feedback triggers a rebuild. The preview refreshes itself.</p>
            <textarea id="feedback" rows="4" placeholder="e.g. make the board bigger"></textarea>
            <button id="send-feedback" data-action="feedback">Send feedback</button>
            <div id="feedback-note" class="note muted"></div>
          </div>
          <div class="card" style="margin-top:16px">
            <h2>Define a rule</h2>
            <p class="muted">Rules are durable and enforced on every future build.</p>
            <textarea id="rule" rows="2" placeholder="e.g. always add a header comment"></textarea>
            <button id="add-rule" data-action="rule">Add rule</button>
            <div id="rule-note" class="note muted"></div>
            <ul id="rules"></ul>
          </div>
        </div>
      </div>
    </main>
    <script>
      const ws = new URLSearchParams(location.search).get('ws') || '';
      let lastBuild = -1;
      document.getElementById('title').textContent = 'Console: ' + ws;

      function renderPreview(item) {
        const wrap = document.getElementById('preview-wrap');
        if (!item.has_preview) {
          wrap.innerHTML = '<span class="muted">No index.html in this workspace yet.</span>';
          return;
        }
        if (item.build !== lastBuild) {
          lastBuild = item.build;
          const src = '/' + ws + '/index.html?v=' + item.build;
          wrap.innerHTML = '<iframe id="preview" src="' + src + '"></iframe>';
        }
      }

      function renderStatus(item) {
        const val = item.validation_ok ? '<span class="ok">tests pass</span>'
          : '<span class="bad">tests failing</span>';
        const hyg = item.hygiene_passed ? '<span class="ok">hygiene pass</span>'
          : '<span class="bad">hygiene failing</span>';
        document.getElementById('status').innerHTML =
          '<span class="pill">phase: ' + item.phase + '</span>'
          + '<span class="pill">attempt: ' + item.attempt + '</span>'
          + '<span class="pill">build: ' + item.build + '</span>'
          + '<span class="pill">' + val + '</span>'
          + '<span class="pill">' + hyg + '</span>';
      }

      function renderRules(item) {
        const list = document.getElementById('rules');
        const lines = (item.rules || '').split('\\n')
          .filter((line) => line.trim().startsWith('- '));
        list.innerHTML = lines.map((line) => '<li>' + line.replace(/^- /, '') + '</li>').join('');
      }

      async function refresh() {
        const res = await fetch('/api/overview.json', { cache: 'no-store' });
        const data = await res.json();
        const item = data.workspaces.find((w) => w.name === ws);
        if (!item) {
          document.getElementById('status').textContent = 'Workspace not found: ' + ws;
          return;
        }
        renderStatus(item);
        renderPreview(item);
        renderRules(item);
      }

      async function post(url, field, value, note) {
        const text = value.trim();
        const el = document.getElementById(note);
        if (!text) { el.textContent = 'Write something first.'; return; }
        const body = new URLSearchParams({ workspace: ws, [field]: text });
        const res = await fetch(url, { method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body });
        el.textContent = res.ok ? 'Saved. Rebuilding on the next cycle...' : 'Failed to save.';
        return res.ok;
      }

      document.getElementById('send-feedback').addEventListener('click', async () => {
        const box = document.getElementById('feedback');
        if (await post('/api/feedback', 'message', box.value, 'feedback-note')) box.value = '';
      });
      document.getElementById('add-rule').addEventListener('click', async () => {
        const box = document.getElementById('rule');
        if (await post('/api/rules', 'rule', box.value, 'rule-note')) box.value = '';
      });

      refresh();
      setInterval(refresh, 1500);
    </script>
  </body>
</html>
"""


GOVERNANCE_SHELL = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Qaymark Governance</title>
    <style>
      body { margin: 0; font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; }
      main { max-width: 1200px; margin: 0 auto; padding: 20px; display: grid; gap: 16px; }
      .card { background: #111827; border: 1px solid #334155; border-radius: 16px; padding: 16px; }
      a { color: #93c5fd; }
      h1, h2, h3 { margin: 0 0 8px; }
      .fw { border: 1px solid #334155; border-radius: 14px; margin-bottom: 12px; overflow: hidden; }
      .fw-head { padding: 14px 16px; cursor: pointer; display: flex; justify-content: space-between;
        align-items: center; background: #0b1220; }
      .fw-head:hover { background: #131c2e; }
      .fw-body { display: none; padding: 8px 16px 16px; }
      .fw.open .fw-body { display: block; }
      .rule { border-top: 1px solid #1f2a3d; padding: 12px 0; }
      .rule:first-child { border-top: 0; }
      .rule-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
      .muted { color: #94a3b8; }
      .ok { color: #86efac; }
      .off { color: #fca5a5; }
      .pill { display: inline-block; padding: 2px 10px; border-radius: 999px;
        border: 1px solid #334155; margin-left: 6px; font-size: 0.85rem; }
      .controls { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-top: 8px; }
      select, input { border-radius: 8px; border: 1px solid #334155; padding: 6px 8px;
        font: inherit; background: #0b1220; color: inherit; }
      button { border: 0; border-radius: 8px; padding: 6px 12px; font: inherit;
        background: #8b5cf6; color: white; cursor: pointer; }
      .why { font-size: 0.9rem; }
      .count { font-variant-numeric: tabular-nums; }
      .note { min-height: 1rem; font-size: 0.85rem; }
    </style>
  </head>
  <body>
    <main>
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <h1>Governance</h1>
          <a href="/">Back to overview</a>
        </div>
        <p class="muted">Every be-gone framework and rule that governs the factory. Drill in,
          toggle, tune severity and thresholds. Changes take effect on the next build.</p>
        <div id="summary" class="muted">Loading...</div>
      </div>
      <div id="frameworks"></div>
    </main>
    <script>
      const EDITABLE_NUMERIC = ['max_lines', 'max_args', 'max_depth', 'max_length',
        'max_bytes', 'threshold', 'max_exports'];

      function severitySelect(rule) {
        const other = rule.severity === 'error' ? 'warning' : 'error';
        return '<select data-kind="severity">'
          + '<option value="' + rule.severity + '">' + rule.severity + '</option>'
          + '<option value="' + other + '">' + other + '</option></select>';
      }

      function numericInputs(rule) {
        return EDITABLE_NUMERIC.filter((k) => k in rule.config).map((k) =>
          '<label class="muted">' + k + ' '
          + '<input type="number" data-kind="' + k + '" value="' + rule.config[k] + '"></label>'
        ).join('');
      }

      function ruleRow(fid, rule) {
        const state = rule.enabled ? '<span class="ok">enabled</span>'
          : '<span class="off">disabled</span>';
        return '<div class="rule" data-fw="' + fid + '" data-rule="' + rule.id + '">'
          + '<div class="rule-head"><div><strong>' + rule.id + '</strong>'
          + '<span class="pill">' + rule.type + '</span>'
          + '<span class="pill">' + rule.severity + '</span>' + state + '</div></div>'
          + '<div class="muted why">' + (rule.what || rule.description || '') + '</div>'
          + '<div class="muted why"><em>' + (rule.why || '') + '</em></div>'
          + '<div class="controls">'
          + '<button data-act="toggle">' + (rule.enabled ? 'Disable' : 'Enable') + '</button>'
          + severitySelect(rule) + numericInputs(rule)
          + '<button data-act="save">Save</button>'
          + '<span class="note muted"></span></div></div>';
      }

      function frameworkCard(f) {
        const rules = f.rules.map((r) => ruleRow(f.id, r)).join('');
        return '<div class="fw" data-fw="' + f.id + '">'
          + '<div class="fw-head"><div><strong>' + f.name + '</strong>'
          + '<span class="pill">' + f.domain + '</span>'
          + '<span class="pill">scope: ' + f.scope + '</span>'
          + '<span class="muted"> — ' + f.description + '</span></div>'
          + '<div class="count muted">' + f.enabled_count + '/' + f.rule_count
          + ' enabled &middot; <a href="' + f.repo + '" target="_blank">repo</a></div></div>'
          + '<div class="fw-body">' + rules + '</div></div>';
      }

      async function load() {
        const res = await fetch('/api/frameworks.json', { cache: 'no-store' });
        const data = await res.json();
        const total = data.frameworks.reduce((a, f) => a + f.rule_count, 0);
        const on = data.frameworks.reduce((a, f) => a + f.enabled_count, 0);
        const overlap = data.overlap || [];
        const governance = overlap.length
          ? '<span class="bad">overlap: ' + overlap.join('; ') + '</span>'
          : '<span class="ok">no overlap &mdash; every framework owns its lane</span>';
        document.getElementById('summary').innerHTML = data.frameworks.length
          + ' frameworks &middot; ' + on + '/' + total + ' rules enabled &middot; ' + governance;
        document.getElementById('frameworks').innerHTML =
          data.frameworks.map(frameworkCard).join('');
      }

      async function post(fid, ruleId, field, value, note) {
        const body = new URLSearchParams({ framework: fid, rule: ruleId, field, value });
        const res = await fetch('/api/framework-rule', { method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body });
        const data = await res.json();
        note.textContent = data.ok ? 'Saved.' : ('Error: ' + (data.error || 'failed'));
        return data.ok;
      }

      document.addEventListener('click', async (event) => {
        const head = event.target.closest('.fw-head');
        if (head) { head.parentElement.classList.toggle('open'); return; }
        const row = event.target.closest('.rule');
        if (!row) return;
        const fid = row.dataset.fw;
        const ruleId = row.dataset.rule;
        const note = row.querySelector('.note');
        if (event.target.dataset.act === 'toggle') {
          const enabling = event.target.textContent === 'Enable';
          if (await post(fid, ruleId, 'enabled', enabling ? 'true' : 'false', note)) load();
        } else if (event.target.dataset.act === 'save') {
          const sev = row.querySelector('[data-kind="severity"]');
          let ok = await post(fid, ruleId, 'severity', sev.value, note);
          for (const input of row.querySelectorAll('input[type="number"]')) {
            ok = await post(fid, ruleId, input.dataset.kind, input.value, note) && ok;
          }
          if (ok) load();
        }
      });

      load();
    </script>
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


def _rules_file(workspace: Path) -> Path:
    return workspace / ".harness" / "rules.md"


def _read_rules(workspace: Path) -> str:
    path = _rules_file(workspace)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _append_rule(workspace: Path, username: str, rule: str) -> None:
    text = rule.strip()
    if not text:
        return
    path = _rules_file(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if not existing:
        existing = "# Project rules (always enforced)\n\n"
    line = f"- {text}  _(added by {username})_\n"
    path.write_text(existing + line, encoding="utf-8")


def _build_count(workspace: Path) -> int:
    path = workspace / ".harness" / "build_count"
    if not path.exists():
        return 0
    try:
        return int(path.read_text(encoding="utf-8").strip() or "0")
    except (ValueError, OSError):
        return 0


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
                "rules": _read_rules(item.path),
                "build": _build_count(item.path),
                "has_preview": (item.path / "index.html").exists(),
                "link": item.link,
                "console": f"/console?ws={item.name}",
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


def _update_framework_rule(form: dict[str, str]) -> dict:
    """Translate a governance form post into a validated rule update."""

    fid = form.get("framework", "")
    rule_id = form.get("rule", "")
    field = form.get("field", "")
    value: object = form.get("value", "")
    if not fid or not rule_id or not field:
        raise ValueError("framework, rule, and field are required")
    if field == "enabled":
        value = str(value).lower() in {"1", "true", "yes", "on"}
    return fw.update_rule(fid, rule_id, {field: value})


_STATIC_PAGES = {
    "/": HTML_SHELL,
    "/console": CONSOLE_SHELL,
    "/governance": GOVERNANCE_SHELL,
}


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

    def _send_logout(self) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Set-Cookie", f"{COOKIE_NAME}=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax")
        self.send_header("Location", "/")
        self.send_header("Content-Length", "0")
        self.end_headers()
        self.wfile.write(b"")

    def _serve_workspace(self, path: str) -> None:
        rel = path.removeprefix("/workspace/").strip("/")
        target = (self.root / rel).resolve()
        if self.root.resolve() not in target.parents and target != self.root.resolve():
            self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"not found")
            return
        body = _workspace_page(target).encode("utf-8")
        self._send(HTTPStatus.OK, "text/html; charset=utf-8", body)

    def _serve_api(self, path: str, username: str) -> bool:
        if path == "/api/frameworks.json":
            payload = {"frameworks": fw.list_frameworks(), "overlap": fw.check_overlap()}
            body = json.dumps(payload, indent=2).encode("utf-8")
        elif path == "/api/overview.json":
            body = json.dumps(overview(self.root, username), indent=2).encode("utf-8")
        else:
            return False
        self._send(HTTPStatus.OK, "application/json; charset=utf-8", body)
        return True

    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path
        if path == "/logout":
            self._send_logout()
            return
        username = self._require_auth()
        if username is None:
            self._send(HTTPStatus.OK, "text/html; charset=utf-8", _login_page())
            return
        page = _STATIC_PAGES.get("/" if path == "/dashboard" else path)
        if page is not None:
            self._send(HTTPStatus.OK, "text/html; charset=utf-8", page.encode("utf-8"))
            return
        if self._serve_api(path, username):
            return
        if path.startswith("/workspace/"):
            self._serve_workspace(path)
            return
        return super().do_GET()

    def _resolve_workspace(self, rel: str) -> Path | None:
        target = self.root if not rel else (self.root / rel).resolve()
        root_resolved = self.root.resolve()
        if target != root_resolved and root_resolved not in target.parents:
            return None
        return target

    def _handle_workspace_post(self, apply, ok_key: str) -> None:
        username = self._require_auth()
        if username is None:
            self._send(HTTPStatus.UNAUTHORIZED, "text/plain; charset=utf-8", b"login required")
            return
        size = int(self.headers.get("Content-Length", "0"))
        form = _parse_form(self.rfile.read(size))
        target = self._resolve_workspace(form.get("workspace", ""))
        if target is None:
            self._send(HTTPStatus.BAD_REQUEST, "text/plain; charset=utf-8", b"invalid workspace")
            return
        apply(target, username, form.get(ok_key, ""))
        self._send(HTTPStatus.OK, "application/json; charset=utf-8", b'{"ok": true}')

    def _handle_framework_rule(self) -> None:
        username = self._require_auth()
        if username is None:
            self._send(HTTPStatus.UNAUTHORIZED, "text/plain; charset=utf-8", b"login required")
            return
        size = int(self.headers.get("Content-Length", "0"))
        form = _parse_form(self.rfile.read(size))
        try:
            view = _update_framework_rule(form)
        except (KeyError, ValueError) as exc:
            body = json.dumps({"ok": False, "error": str(exc)}).encode("utf-8")
            self._send(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
            return
        body = json.dumps({"ok": True, "rule": view}).encode("utf-8")
        self._send(HTTPStatus.OK, "application/json; charset=utf-8", body)

    def do_POST(self):  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/feedback":
            self._handle_workspace_post(_append_feedback, "message")
            return
        if path == "/api/rules":
            self._handle_workspace_post(_append_rule, "rule")
            return
        if path == "/api/framework-rule":
            self._handle_framework_rule()
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
