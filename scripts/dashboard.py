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
import signal
import sys
import time
from dataclasses import dataclass
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qaymark import chat  # noqa: E402  (path set up above)
from qaymark import control  # noqa: E402  (path set up above)
from qaymark import frameworks as fw  # noqa: E402  (path set up above)
from qaymark import orchestrator  # noqa: E402  (path set up above)
from qaymark import plan as plan_mod  # noqa: E402  (path set up above)

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
      .factory-wrap {
        position: relative;
        min-height: 300px;
        overflow-x: auto;
        overflow-y: hidden;
        padding: 8px 0 4px;
      }
      .factory-scene {
        position: relative;
        min-height: 280px;
        min-width: 900px;
      }
      .factory-grid {
        position: absolute;
        inset: 0;
        background-image:
          linear-gradient(rgba(148,163,184,.06) 1px, transparent 1px),
          linear-gradient(90deg, rgba(148,163,184,.06) 1px, transparent 1px);
        background-size: 160px 84px;
        border-radius: 18px;
        opacity: .6;
      }
      .factory-station {
        position: absolute;
        top: 0;
        bottom: 0;
        width: 160px;
        left: calc(var(--col) * 160px);
        border-left: 1px dashed rgba(148,163,184,.14);
      }
      .factory-station .label {
        position: absolute;
        top: 4px;
        left: 8px;
        font-size: .68rem;
        letter-spacing: .06em;
        text-transform: uppercase;
        color: #7c8aa5;
        white-space: nowrap;
      }
      .factory-lane {
        position: absolute;
        left: 0;
        right: 0;
        height: 68px;
        top: calc(var(--row) * 84px + 30px);
        border-radius: 12px;
        background:
          repeating-linear-gradient(90deg,
            rgba(148,163,184,.05) 0 14px, transparent 14px 28px);
        background-size: 28px 100%;
        animation: flow 1.6s linear infinite;
      }
      @keyframes flow { to { background-position: 28px 0; } }
      .factory-node {
        position: absolute;
        width: 148px;
        left: calc(var(--col) * 160px + 6px);
        top: calc(var(--row) * 84px + 34px);
        border-radius: 14px;
        border: 1px solid rgba(148,163,184,.2);
        background: linear-gradient(180deg, rgba(30,41,59,.98), rgba(15,23,42,.98));
        box-shadow:
          0 1px 0 rgba(255,255,255,.05) inset,
          0 6px 0 rgba(2,6,23,.6),
          0 14px 26px rgba(2,6,23,.55);
        padding: 10px 12px;
        transition: transform .2s ease, box-shadow .2s ease;
      }
      .factory-node:hover { transform: translateY(-3px); }
      .factory-node strong { display: block; font-size: .92rem; margin-bottom: 2px; }
      .factory-node strong a { color: #e2e8f0; text-decoration: none; }
      .factory-node .phase { color: #94a3b8; font-size: .78rem; }
      .factory-node .meter {
        margin-top: 8px;
        height: 8px;
        border-radius: 999px;
        background: rgba(2,6,23,.95);
        overflow: hidden;
        border: 1px solid rgba(148,163,184,.18);
      }
      .factory-node .meter span {
        display: block;
        height: 100%;
        border-radius: inherit;
        background: linear-gradient(90deg, #22d3ee, #8b5cf6);
        width: calc(var(--p) * 100%);
      }
      .factory-node.running {
        border-color: rgba(34,211,238,.6);
        box-shadow:
          0 0 0 1px rgba(34,211,238,.3),
          0 6px 0 rgba(2,6,23,.6),
          0 14px 30px rgba(34,211,238,.22);
        animation: pulse 1.8s ease-in-out infinite;
      }
      @keyframes pulse {
        50% { box-shadow:
          0 0 0 1px rgba(34,211,238,.55),
          0 6px 0 rgba(2,6,23,.6),
          0 16px 38px rgba(34,211,238,.4); }
      }
      .factory-node.paused { border-color: rgba(250,204,21,.55); }
      .factory-node.stopped { border-color: rgba(148,163,184,.35); opacity: .75; }
      .factory-node .dot {
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        margin-right: 5px;
        background: #64748b;
      }
      .factory-node.running .dot { background: #22d3ee; }
      .factory-node.paused .dot { background: #facc15; }
      .loop-bar {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
        gap: 10px;
      }
      .loop-chip {
        border: 1px solid rgba(148,163,184,.14);
        border-radius: 14px;
        background: rgba(2,6,23,.6);
        padding: 10px 12px;
      }
      .loop-card {
        border: 1px solid rgba(148,163,184,.16);
        border-radius: 14px;
        background: rgba(2,6,23,.55);
        padding: 12px 14px;
        margin-bottom: 10px;
      }
      .loop-card .head {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
      }
      .loop-card .badge {
        font-size: .78rem;
        padding: 2px 10px;
        border-radius: 999px;
        border: 1px solid rgba(148,163,184,.25);
      }
      .loop-card .badge.running { color: #22d3ee; border-color: rgba(34,211,238,.5); }
      .loop-card .badge.paused { color: #facc15; border-color: rgba(250,204,21,.5); }
      .loop-card .badge.idle { color: #94a3b8; }
      .loop-card .controls { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
      .loop-card .controls button { padding: 6px 12px; }
      .loop-card .redirect { display: flex; gap: 6px; margin-top: 8px; flex-wrap: wrap; }
      .loop-card .redirect input { flex: 1; min-width: 220px; }
      .loop-card .note { font-size: .8rem; margin-top: 6px; }
      .factory-node.green { border-color: rgba(134,239,172,.6); }
      .factory-node.green .dot { background: #86efac; }
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
          <h2 style="margin:0">Factory floor</h2>
          <span class="muted">The loop as a reactive 3D map</span>
        </div>
        <div id="factory-floor" class="factory-wrap muted">Loading...</div>
      </section>
      <section class="card">
        <div class="row" style="justify-content:space-between">
          <h2 style="margin:0">Loop control</h2>
          <span class="muted">Pick which loops run; pause, redirect, or stop them</span>
        </div>
        <div class="row" style="margin:6px 0 12px">
          <label class="small" for="launch-job">Start a loop:</label>
          <select id="launch-job"></select>
          <input id="launch-model" placeholder="model (optional)" style="max-width:200px">
          <label class="small"><input id="launch-forever" type="checkbox"> forever</label>
          <button id="launch-go" type="button" data-action="launch">Launch</button>
          <button id="run-all" type="button" data-action="run-all"
            style="background:#0e7490">Run all pending</button>
        </div>
        <div id="launch-note" class="small muted"></div>
        <div id="loops" class="muted">Loading...</div>
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
        renderFloor(data);
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
      function floorNodeClass(node) {
        if (node.stopping || node.phase === 'stopped') return ' stopped';
        if (node.paused || node.phase === 'paused') return ' paused';
        if (node.alive) return ' running';
        if (node.green) return ' green';
        return '';
      }
      function renderFloor(data) {
        const floor = data.floor || { phases: [], nodes: [] };
        const stations = floor.phases.map(
          (phase, index) =>
            '<div class="factory-station" style="--col:' + index + '">'
            + '<span class="label">' + phase + '</span></div>'
        ).join('');
        const lanes = floor.nodes.map(
          (node) => '<div class="factory-lane" style="--row:' + node.row + '"></div>'
        ).join('');
        const nodes = floor.nodes.map((node) => {
          const attempt = node.attempt == null ? '–' : node.attempt;
          const cap = node.max_attempts ? '/' + node.max_attempts : '';
          return [
            '<article class="factory-node' + floorNodeClass(node) + '"',
            ' style="--col:' + node.col + ';--row:' + node.row + ';--p:' + node.progress + '">',
            '<strong><span class="dot"></span>',
            '<a href="' + node.console + '">' + node.name + '</a></strong>',
            '<div class="phase">' + node.phase + ' · ' + attempt + cap + '</div>',
            '<div class="meter"><span></span></div>',
            '</article>',
          ].join('');
        }).join('');
        const empty = floor.nodes.length ? ''
          : '<div class="muted" style="padding:12px">No loops on the floor yet.</div>';
        document.getElementById('factory-floor').innerHTML = empty + [
          '<div class="factory-scene">',
          '<div class="factory-grid"></div>',
          lanes,
          stations,
          nodes,
          '</div>',
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
      function loopBadge(loop) {
        if (loop.alive && loop.paused) return '<span class="badge paused">paused</span>';
        if (loop.alive) return '<span class="badge running">running</span>';
        return '<span class="badge idle">idle</span>';
      }
      function loopCard(loop) {
        const attempt = loop.attempt == null ? '–' : loop.attempt;
        const cap = loop.max_attempts ? '/' + loop.max_attempts : '';
        const pauseBtn = loop.paused
          ? '<button data-loop-act="resume">Resume</button>'
          : '<button data-loop-act="pause">Pause</button>';
        return [
          '<div class="loop-card" data-loop="' + loop.name + '">',
          '<div class="head"><strong>' + loop.name + '</strong>' + loopBadge(loop),
          '<span class="muted small">phase ' + loop.phase + ' · attempt '
          + attempt + cap + ' · build ' + (loop.build || 0) + '</span></div>',
          '<div class="controls">', pauseBtn,
          '<button data-loop-act="stop">Stop</button>',
          '<a class="badge" href="/console?ws=' + loop.name + '">Open console</a></div>',
          '<div class="redirect"><input placeholder="Redirect to a new task...">',
          '<button data-loop-act="redirect">Redirect</button></div>',
          '<div class="note muted">' + (loop.note || '') + '</div>',
          '</div>',
        ].join('');
      }
      async function loadLoops() {
        const res = await fetch('/api/loops.json', { cache: 'no-store' });
        const data = await res.json();
        const select = document.getElementById('launch-job');
        if (!select.dataset.loaded) {
          select.innerHTML = data.jobs.map(
            (j) => '<option value="' + j.name + '">' + j.name + '</option>'
          ).join('');
          select.dataset.loaded = '1';
        }
        const loops = data.loops || [];
        document.getElementById('loops').innerHTML = loops.length
          ? loops.map(loopCard).join('')
          : '<span class="muted">No loops yet. Launch one above.</span>';
      }
      async function postLoop(url, body, note) {
        const res = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: new URLSearchParams(body),
        });
        const data = await res.json().catch(() => ({ ok: false }));
        if (note) {
          document.getElementById(note).textContent = data.ok
            ? 'Done.' : ('Error: ' + (data.error || 'failed'));
        }
        loadLoops();
        return data.ok;
      }
      document.getElementById('launch-go').addEventListener('click', () => {
        postLoop('/api/loop-launch', {
          job: document.getElementById('launch-job').value,
          model: document.getElementById('launch-model').value,
          forever: document.getElementById('launch-forever').checked ? '1' : '',
        }, 'launch-note');
      });
      document.getElementById('run-all').addEventListener('click', () => {
        postLoop('/api/loops-run-all', {
          model: document.getElementById('launch-model').value,
        }, 'launch-note');
      });
      document.getElementById('loops').addEventListener('click', (event) => {
        const act = event.target.dataset.loopAct;
        if (!act) return;
        const card = event.target.closest('.loop-card');
        const name = card.dataset.loop;
        const body = { name, action: act };
        if (act === 'redirect') {
          body.task = card.querySelector('.redirect input').value;
        }
        postLoop('/api/loop-control', body, null);
      });
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
      loadLoops();
      refresh();
      setInterval(refresh, 2000);
      setInterval(loadLoops, 2500);
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
      .factory-wrap {
        min-height: 150px;
        overflow-x: auto;
        overflow-y: hidden;
        position: relative;
      }
      .factory-scene {
        position: relative;
        height: 130px;
        min-width: 820px;
      }
      .factory-grid {
        position: absolute;
        inset: 0;
        background-image:
          linear-gradient(rgba(148,163,184,.06) 1px, transparent 1px),
          linear-gradient(90deg, rgba(148,163,184,.06) 1px, transparent 1px);
        background-size: 116px 84px;
        border-radius: 18px;
        opacity: .6;
      }
      .factory-station {
        position: absolute;
        top: 0;
        bottom: 0;
        width: 116px;
        left: calc(var(--col) * 116px);
        border-left: 1px dashed rgba(148,163,184,.14);
      }
      .factory-station .label {
        position: absolute;
        top: 4px;
        left: 8px;
        font-size: .64rem;
        text-transform: uppercase;
        letter-spacing: .05em;
        color: #7c8aa5;
        white-space: nowrap;
      }
      .factory-lane {
        position: absolute;
        left: 0;
        right: 0;
        height: 60px;
        top: 34px;
        border-radius: 12px;
        background:
          repeating-linear-gradient(90deg,
            rgba(148,163,184,.05) 0 14px, transparent 14px 28px);
        background-size: 28px 100%;
        animation: flow 1.6s linear infinite;
      }
      @keyframes flow { to { background-position: 28px 0; } }
      .factory-node {
        position: absolute;
        width: 150px;
        left: calc(var(--col) * 116px + 6px);
        top: 38px;
        border-radius: 14px;
        border: 1px solid rgba(148,163,184,.2);
        background: linear-gradient(180deg, rgba(30,41,59,.98), rgba(15,23,42,.98));
        box-shadow:
          0 6px 0 rgba(2,6,23,.6),
          0 14px 26px rgba(2,6,23,.55);
        padding: 10px 12px;
      }
      .factory-node.running {
        border-color: rgba(34,211,238,.6);
        animation: pulse 1.8s ease-in-out infinite;
      }
      @keyframes pulse {
        50% { box-shadow:
          0 0 0 1px rgba(34,211,238,.5),
          0 6px 0 rgba(2,6,23,.6),
          0 16px 36px rgba(34,211,238,.38); }
      }
      .factory-node.paused { border-color: rgba(250,204,21,.55); }
      .factory-node strong { display: block; font-size: .9rem; }
      .factory-node .dot {
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        margin-right: 5px;
        background: #22d3ee;
      }
      .factory-node.paused .dot { background: #facc15; }
      .meter {
        height: 8px;
        border-radius: 999px;
        background: rgba(2,6,23,.95);
        overflow: hidden;
        margin-top: 8px;
      }
      .meter span {
        display: block;
        height: 100%;
        width: calc(var(--p) * 100%);
        border-radius: inherit;
        background: linear-gradient(90deg, #22d3ee, #8b5cf6);
      }
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
      .status-line {
        display: flex;
        gap: 6px;
        flex-wrap: wrap;
        margin-top: 8px;
      }
      .status-line .pill { margin-right: 0; }
      .chat-log {
        list-style: none;
        margin: 0;
        padding: 0;
        max-height: 320px;
        overflow-y: auto;
        display: flex;
        flex-direction: column;
        gap: 8px;
      }
      .chat-msg {
        border-radius: 12px;
        padding: 8px 12px;
        max-width: 90%;
        font-size: .9rem;
        line-height: 1.35;
      }
      .chat-msg .who { font-size: .7rem; text-transform: uppercase; letter-spacing: .05em; }
      .chat-msg.operator { align-self: flex-end; background: rgba(139,92,246,.22);
        border: 1px solid rgba(139,92,246,.4); }
      .chat-msg.loop { align-self: flex-start; background: rgba(34,211,238,.12);
        border: 1px solid rgba(34,211,238,.3); }
      .chat-msg.system { align-self: center; background: rgba(148,163,184,.12);
        border: 1px solid rgba(148,163,184,.25); color: #cbd5e1; }
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
      <div class="card">
        <h2>Loop map</h2>
        <div class="muted">Where the model is in the loop, now, in a 3D factory floor view.</div>
        <div id="loop-map" class="factory-wrap">Loading...</div>
      </div>
      <div class="card">
        <h2>Loop control</h2>
        <p class="muted">Steer this loop directly — no terminal, no Copilot.</p>
        <div id="loop-state" class="status-line"></div>
        <div class="row">
          <button id="loop-pause" type="button" data-action="pause">Pause</button>
          <button id="loop-resume" type="button" data-action="resume">Resume</button>
          <button id="loop-stop" type="button" data-action="stop">Stop</button>
        </div>
        <div class="row" style="margin-top:8px">
          <input id="loop-redirect" placeholder="Redirect to a new task..." style="flex:1">
          <button id="loop-redirect-go" type="button" data-action="redirect">Redirect</button>
        </div>
        <div id="loop-note" class="note muted"></div>
      </div>
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <h2 style="margin:0">Plan</h2>
          <span id="plan-focus" class="muted"></span>
        </div>
        <p class="muted">What this workspace is working on. Edit it to steer the
          loop — the plan is folded into the model's next prompt.</p>
        <div id="plan-meta" class="status-line"></div>
        <div class="row" style="gap:6px">
          <input id="plan-goal" placeholder="Goal" style="flex:1">
          <button id="plan-goal-save" type="button" data-action="plan-goal">Save goal</button>
        </div>
        <ul id="plan-steps" style="list-style:none;padding:0;margin:10px 0"></ul>
        <div class="row" style="gap:6px">
          <input id="plan-add" placeholder="Add a step..." style="flex:1">
          <button id="plan-add-go" type="button" data-action="plan-add">Add step</button>
        </div>
        <div id="plan-note" class="note muted"></div>
      </div>
      <div class="card">
        <h2>Chat with this loop</h2>
        <p class="muted">The loop narrates what it is doing. Reply to steer it —
          plain text becomes feedback; start with <code>/redirect</code> to hand
          it a new task.</p>
        <ul id="chat-log" class="chat-log" aria-live="polite"></ul>
        <form id="chat-form" style="margin-top:10px">
          <label class="muted" for="chat-input">Message</label>
          <textarea id="chat-input" rows="2"
            placeholder="e.g. focus on the failing test, or /redirect build X"></textarea>
          <button id="chat-send" type="submit" data-action="chat">Send</button>
          <span id="chat-note" class="note muted"></span>
        </form>
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

      function renderLoop(item) {
        const phases = [
          'starting',
          'attempting',
          'retrying',
          'watching',
          'passed',
          'failed',
          'reverted',
        ];
        const phaseIndex = Math.max(phases.indexOf(item.phase), 0);
        const progress = item.max_attempts ? Math.min(item.attempt / item.max_attempts, 1) : 0;
        const stations = phases.map((phase, index) =>
          '<div class="factory-station" style="--col:' + index + '">'
          + '<span class="label">' + phase + '</span></div>'
        ).join('');
        const cls = item.phase === 'paused' ? ' paused' : ' running';
        const node = [
          '<article class="factory-node' + cls + '" style="--col:' + phaseIndex,
          ';--p:' + progress + '">',
          '<strong><span class="dot"></span>' + ws + '</strong>',
          '<div class="meter"><span></span></div>',
          '</article>',
        ].join('');
        document.getElementById('loop-map').innerHTML = [
          '<div class="factory-scene">',
          '<div class="factory-grid"></div>',
          '<div class="factory-lane"></div>',
          stations,
          node,
          '</div>',
        ].join('');
      }

      function renderRules(item) {
        const list = document.getElementById('rules');
        const lines = (item.rules || '').split('\\n')
          .filter((line) => line.trim().startsWith('- '));
        list.innerHTML = lines.map((line) => '<li>' + line.replace(/^- /, '') + '</li>').join('');
      }

      function renderControl(loop) {
        const wrap = document.getElementById('loop-state');
        if (!loop) {
          wrap.innerHTML = '<span class="pill">control: unknown</span>';
          return;
        }
        const bits = [
          '<span class="pill">control: ' + (loop.paused ? 'paused' : 'running') + '</span>',
          loop.stopping ? '<span class="pill">stopping</span>' : '',
          loop.redirect_task
            ? '<span class="pill">redirect: ' + escapeHtml(loop.redirect_task) + '</span>'
            : '',
          loop.note ? '<span class="pill">note: ' + escapeHtml(loop.note) + '</span>' : '',
        ].filter(Boolean);
        wrap.innerHTML = bits.join('');
      }

      function renderPlanMeta(planData) {
        const wrap = document.getElementById('plan-meta');
        const steps = planData.steps || [];
        const active = steps.find((step) => step.status === 'active');
        const bits = [
          planData.generated_by
            ? '<span class="pill">source: ' + escapeHtml(planData.generated_by) + '</span>'
            : '',
          planData.generated_at
            ? '<span class="pill">generated: ' + escapeHtml(planData.generated_at) + '</span>'
            : '',
          '<span class="pill">steps: ' + steps.length + '</span>',
          active ? '<span class="pill">focus: ' + escapeHtml(active.text || '') + '</span>' : '',
        ].filter(Boolean);
        wrap.innerHTML = bits.join('');
      }

      async function refresh() {
        const [overviewRes, loopsRes] = await Promise.all([
          fetch('/api/overview.json', { cache: 'no-store' }),
          fetch('/api/loops.json', { cache: 'no-store' }),
        ]);
        const data = await overviewRes.json();
        const loopData = await loopsRes.json().catch(() => ({ loops: [] }));
        const item = data.workspaces.find((w) => w.name === ws);
        if (!item) {
          document.getElementById('status').textContent = 'Workspace not found: ' + ws;
          return;
        }
        const loop = (loopData.loops || []).find((entry) => entry.name === ws);
        renderStatus(item);
        renderLoop(item);
        renderPreview(item);
        renderRules(item);
        renderControl(loop);
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
      async function loopControl(action, task) {
        const note = document.getElementById('loop-note');
        const body = { name: ws, action };
        if (task) body.task = task;
        const res = await fetch('/api/loop-control', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: new URLSearchParams(body),
        });
        const data = await res.json().catch(() => ({ ok: false }));
        note.textContent = data.ok
          ? (action + ' applied.') : ('Error: ' + (data.error || 'failed'));
      }
      document.getElementById('loop-pause').addEventListener('click', () => loopControl('pause'));
      document.getElementById('loop-resume').addEventListener('click', () => loopControl('resume'));
      document.getElementById('loop-stop').addEventListener('click', () => loopControl('stop'));
      document.getElementById('loop-redirect-go').addEventListener('click', () => {
        const box = document.getElementById('loop-redirect');
        if (box.value.trim()) loopControl('redirect', box.value.trim());
        box.value = '';
      });

      function escapeHtml(text) {
        return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      }
      async function loadChat() {
        const res = await fetch('/api/chat.json?ws=' + encodeURIComponent(ws), {
          cache: 'no-store',
        });
        const data = await res.json().catch(() => ({ messages: [] }));
        const log = document.getElementById('chat-log');
        const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
        log.innerHTML = (data.messages || []).map((m) =>
          '<li class="chat-msg ' + m.role + '"><div class="who">' + m.role
          + '</div>' + escapeHtml(m.text) + '</li>'
        ).join('');
        if (atBottom) log.scrollTop = log.scrollHeight;
      }
      document.getElementById('chat-form').addEventListener('submit', async (event) => {
        event.preventDefault();
        const box = document.getElementById('chat-input');
        const text = box.value.trim();
        if (!text) return;
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: new URLSearchParams({ workspace: ws, message: text }),
        });
        document.getElementById('chat-note').textContent = res.ok ? 'Sent.' : 'Failed to send.';
        if (res.ok) box.value = '';
        loadChat();
      });

      async function planOp(fields) {
        const body = new URLSearchParams(Object.assign({ workspace: ws }, fields));
        const res = await fetch('/api/plan', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body,
        });
        const data = await res.json().catch(() => ({ ok: false }));
        document.getElementById('plan-note').textContent = data.ok
          ? 'Plan updated.' : ('Error: ' + (data.error || 'failed'));
        loadPlan();
      }
      const STEP_STATES = ['pending', 'active', 'done', 'blocked'];
      function stepRow(step) {
        const options = STEP_STATES.map((s) =>
          '<option value="' + s + '"' + (s === step.status ? ' selected' : '') + '>'
          + s + '</option>').join('');
        return '<li data-step="' + step.id + '" style="display:flex;gap:6px;'
          + 'align-items:center;margin-bottom:6px">'
          + '<span class="pill">' + (step.status || 'pending') + '</span>'
          + '<span style="flex:1">' + escapeHtml(step.text || '') + '</span>'
          + '<select data-role="status">' + options + '</select>'
          + '<button data-role="focus" type="button">Focus</button>'
          + '<button data-role="remove" type="button">✕</button></li>';
      }
      async function loadPlan() {
        const res = await fetch('/api/plan.json?ws=' + encodeURIComponent(ws), {
          cache: 'no-store',
        });
        const data = await res.json().catch(() => ({ plan: {} }));
        const p = data.plan || {};
        const goalEl = document.getElementById('plan-goal');
        if (document.activeElement !== goalEl) goalEl.value = p.goal || '';
        document.getElementById('plan-focus').textContent =
          p.focus_note ? ('focus: ' + p.focus_note) : '';
        renderPlanMeta(p);
        document.getElementById('plan-steps').innerHTML =
          (p.steps || []).map(stepRow).join('');
      }
      document.getElementById('plan-goal-save').addEventListener('click', () => {
        planOp({ op: 'set-goal', goal: document.getElementById('plan-goal').value });
      });
      document.getElementById('plan-add-go').addEventListener('click', () => {
        const box = document.getElementById('plan-add');
        if (box.value.trim()) planOp({ op: 'add-step', text: box.value.trim() });
        box.value = '';
      });
      document.getElementById('plan-steps').addEventListener('click', (event) => {
        const li = event.target.closest('li[data-step]');
        if (!li) return;
        const step = li.dataset.step;
        if (event.target.dataset.role === 'focus') planOp({ op: 'set-active', step });
        if (event.target.dataset.role === 'remove') planOp({ op: 'remove-step', step });
      });
      document.getElementById('plan-steps').addEventListener('change', (event) => {
        if (event.target.dataset.role !== 'status') return;
        const li = event.target.closest('li[data-step]');
        planOp({ op: 'update-step', step: li.dataset.step, status: event.target.value });
      });

      refresh();
      loadChat();
      loadPlan();
      setInterval(refresh, 1500);
      setInterval(loadChat, 2000);
      setInterval(loadPlan, 3000);
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
          + '<button data-act="delete" style="background:#7f1d1d">Delete</button>'
          + '<span class="note muted"></span></div></div>';
      }

      function frameworkEditor(f) {
        return '<div class="fw-edit" style="margin-top:12px;border-top:1px solid #1f2a3d;'
          + 'padding-top:10px">'
          + '<textarea data-role="new-rule" rows="3" style="width:100%;box-sizing:border-box;'
          + 'background:#0b1220;color:inherit;border:1px solid #334155;border-radius:8px;'
          + 'padding:8px" placeholder=\'Add a rule as JSON, e.g. '
          + '{"id":"my-rule","type":"long-lines","enabled":true,"severity":"error"}\'></textarea>'
          + '<div class="controls" style="margin-top:6px">'
          + '<button data-act="add-rule">Add rule</button>'
          + '<button data-act="edit-manifest">Edit raw manifest</button>'
          + '<span class="note muted"></span></div>'
          + '<textarea data-role="manifest" rows="12" style="display:none;width:100%;'
          + 'box-sizing:border-box;margin-top:8px;background:#020617;color:inherit;'
          + 'border:1px solid #334155;border-radius:8px;padding:8px;'
          + 'font-family:monospace"></textarea>'
          + '<div class="controls" data-role="manifest-actions" '
          + 'style="display:none;margin-top:6px">'
          + '<button data-act="save-manifest">Save manifest</button></div></div>';
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
          + '<div class="fw-body">' + rules + frameworkEditor(f) + '</div></div>';
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

      async function postJson(url, fields, note) {
        const res = await fetch(url, { method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: new URLSearchParams(fields) });
        const data = await res.json().catch(() => ({ ok: false }));
        if (note) note.textContent = data.ok ? 'Saved.' : ('Error: ' + (data.error || 'failed'));
        return data;
      }

      async function handleRuleAction(row, act, target) {
        const fid = row.dataset.fw;
        const ruleId = row.dataset.rule;
        const note = row.querySelector('.note');
        if (act === 'toggle') {
          const enabling = target.textContent === 'Enable';
          if (await post(fid, ruleId, 'enabled', enabling ? 'true' : 'false', note)) load();
        } else if (act === 'save') {
          const sev = row.querySelector('[data-kind="severity"]');
          let ok = await post(fid, ruleId, 'severity', sev.value, note);
          for (const input of row.querySelectorAll('input[type="number"]')) {
            ok = await post(fid, ruleId, input.dataset.kind, input.value, note) && ok;
          }
          if (ok) load();
        } else if (act === 'delete') {
          if (!confirm('Delete rule ' + ruleId + '?')) return;
          const data = await postJson('/api/framework-delete-rule',
            { framework: fid, rule: ruleId }, note);
          if (data.ok) load();
        } else if (act === 'delete') {
          if (!confirm('Delete rule ' + ruleId + '?')) return;
          const data = await postJson('/api/framework-delete-rule',
            { framework: fid, rule: ruleId }, note);
          if (data.ok) load();
        }
      }

      async function handleEditorAction(card, act, target) {
        const fid = card.dataset.fw;
        const note = card.querySelector('.fw-edit .note');
        if (act === 'add-rule') {
          const box = card.querySelector('[data-role="new-rule"]');
          const data = await postJson('/api/framework-add-rule',
            { framework: fid, rule: box.value }, note);
          if (data.ok) { box.value = ''; load(); }
        } else if (act === 'edit-manifest') {
          const res = await fetch('/api/framework-manifest.json?framework=' + fid);
          const data = await res.json();
          card.querySelector('[data-role="manifest"]').value = data.manifest || '';
          card.querySelector('[data-role="manifest"]').style.display = 'block';
          card.querySelector('[data-role="manifest-actions"]').style.display = 'flex';
        } else if (act === 'save-manifest') {
          const box = card.querySelector('[data-role="manifest"]');
          await postJson('/api/framework-manifest', { framework: fid, manifest: box.value }, note);
          load();
        }
      }

      document.addEventListener('click', async (event) => {
        const head = event.target.closest('.fw-head');
        if (head) { head.parentElement.classList.toggle('open'); return; }
        const act = event.target.dataset.act;
        if (!act) return;
        const row = event.target.closest('.rule');
        if (row) { await handleRuleAction(row, act, event.target); return; }
        const card = event.target.closest('.fw');
        if (card) await handleEditorAction(card, act, event.target);
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


PHASE_ORDER = ("starting", "attempting", "retrying", "watching", "passed", "failed")
_PHASE_TO_STATION = {
    "starting": "starting",
    "idle": "starting",
    "attempting": "attempting",
    "waiting": "attempting",
    "retrying": "retrying",
    "reverted": "retrying",
    "watching": "watching",
    "paused": "watching",
    "passed": "passed",
    "failed": "failed",
    "stopped": "failed",
}

# What "human-readable" means for the factory floor, encoded so a test can
# enforce it. A readable floor is: (1) a fixed, ordered, small set of lifecycle
# stations so left-to-right always means the same thing; (2) every loop mapped
# to exactly one station (position == meaning); (3) one row per loop so nothing
# overlaps; (4) a bounded progress meter in [0, 1]; and (5) a flat scene with no
# tilt and no sideways skew — depth comes from the cards, never a slanted plane.
FLOOR_READABILITY = {
    "stations": PHASE_ORDER,
    "scene_tilt": 0,
    "scene_tilt_max": 6,
    "scene_skew": 0,
}


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


def _post_chat(workspace: Path, username: str, message: str) -> None:
    """Record an operator chat message and let it steer the loop.

    A plain message becomes feedback for the next rebuild; a message that starts
    with ``/redirect`` hands the loop a brand-new task.
    """

    text = message.strip()
    if not text:
        return
    chat.post(workspace, "operator", text)
    if text.lower().startswith("/redirect"):
        task = text[len("/redirect"):].strip(" :")
        if task:
            control.redirect(workspace, task, note=f"redirect via chat by {username}")
            chat.post(workspace, "system", "Got it — redirecting to your new task.")
        return
    _append_feedback(workspace, username, text)
    chat.post(workspace, "system", "Noted — I'll fold that into the next build.")


def _apply_plan_op(workspace: Path, form: dict[str, str]) -> dict:
    """Edit the workspace plan; each op adjusts the loop's direction."""

    op = form.get("op", "")
    if op == "set-goal":
        return plan_mod.set_goal(workspace, form.get("goal", ""))
    if op == "add-step":
        return plan_mod.add_step(workspace, form.get("text", ""))
    if op == "remove-step":
        return plan_mod.remove_step(workspace, form.get("step", ""))
    if op == "set-active":
        return plan_mod.set_active(workspace, form.get("step", ""))
    if op == "update-step":
        return plan_mod.update_step(
            workspace, form.get("step", ""), form.get("text") or None, form.get("status") or None
        )
    raise ValueError(f"unknown plan op: {op}")


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
    active = {"starting", "attempting", "retrying", "watching", "reverted", "waiting"}
    counts = {
        "total": len(workspaces),
        "running": sum(item.phase in active for item in workspaces),
        "passed": sum(item.validation_ok and item.hygiene_passed for item in workspaces),
        "failed": sum(item.phase == "failed" for item in workspaces),
    }
    floor = _factory_floor(workspaces)
    return {
        "root": str(root),
        "user": username,
        "counts": counts,
        "floor": floor,
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


def _floor_node(row: int, item: WorkspaceStatus) -> dict[str, object]:
    station = _PHASE_TO_STATION.get(item.phase, "starting")
    col = PHASE_ORDER.index(station)
    progress = min(item.attempt / item.max_attempts, 1.0) if item.max_attempts else 0.0
    command = control.read_control(item.path)
    return {
        "name": item.name,
        "phase": item.phase,
        "station": station,
        "col": col,
        "row": row,
        "attempt": item.attempt,
        "max_attempts": item.max_attempts,
        "progress": progress,
        "alive": control.loop_is_alive(item.path),
        "green": orchestrator.is_green(item.path),
        "paused": command.paused,
        "stopping": command.stop,
        "console": f"/console?ws={item.name}",
    }


def _factory_floor(workspaces: list[WorkspaceStatus]) -> dict[str, object]:
    nodes = [_floor_node(row, item) for row, item in enumerate(workspaces)]
    return {
        "phases": list(PHASE_ORDER),
        "nodes": nodes,
        "tilt": FLOOR_READABILITY["scene_tilt"],
        "skew": FLOOR_READABILITY["scene_skew"],
    }


def floor_is_readable(floor: dict[str, object]) -> bool:
    """Enforce the readability contract documented on ``FLOOR_READABILITY``."""

    phases = floor.get("phases", [])
    nodes = floor.get("nodes", [])
    stations = list(FLOOR_READABILITY["stations"])
    if phases != stations or not isinstance(nodes, list):
        return False
    if int(floor.get("skew", 1)) != 0:
        return False
    if int(floor.get("tilt", 999)) > int(FLOOR_READABILITY["scene_tilt_max"]):
        return False
    rows = [node.get("row") for node in nodes]
    if len(rows) != len(set(rows)):  # one row per loop: no overlap
        return False
    return all(_node_is_readable(node, len(stations)) for node in nodes)


def _node_is_readable(node: object, station_count: int) -> bool:
    if not isinstance(node, dict):
        return False
    col = int(node.get("col", -1))
    progress = float(node.get("progress", -1))
    return 0 <= col < station_count and 0.0 <= progress <= 1.0


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


def _framework_add_rule(form: dict[str, str]) -> dict:
    fid = form.get("framework", "")
    if not fid:
        raise ValueError("framework is required")
    try:
        rule = json.loads(form.get("rule", ""))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid rule JSON: {exc.msg}") from exc
    return fw.add_rule(fid, rule)


def _framework_delete_rule(form: dict[str, str]) -> dict:
    fid = form.get("framework", "")
    rule_id = form.get("rule", "")
    if not fid or not rule_id:
        raise ValueError("framework and rule are required")
    return fw.delete_rule(fid, rule_id)


def _framework_replace_manifest(form: dict[str, str]) -> dict:
    fid = form.get("framework", "")
    if not fid:
        raise ValueError("framework is required")
    try:
        manifest = json.loads(form.get("manifest", ""))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid manifest JSON: {exc.msg}") from exc
    return fw.replace_manifest(fid, manifest)


def _loops_payload(root: Path) -> dict:
    """Everything the orchestrator UI needs: live loops and launchable jobs."""

    jobs = [
        {"name": job.name, "description": job.description, "model": job.model}
        for job in orchestrator.list_jobs()
    ]
    return {"loops": orchestrator.list_loops(root), "jobs": jobs}


def _apply_loop_control(root: Path, form: dict[str, str]) -> dict:
    """Pause, resume, stop, or redirect one loop from the control panel."""

    name = form.get("name", "").strip()
    action = form.get("action", "").strip()
    note = form.get("note", "")
    if not name or not action:
        raise ValueError("name and action are required")
    if action == "pause":
        return orchestrator.pause_loop(name, note, root=root)
    if action == "resume":
        return orchestrator.resume_loop(name, note, root=root)
    if action == "stop":
        return orchestrator.stop_loop(name, note, root=root)
    if action == "redirect":
        task = form.get("task", "").strip()
        if not task:
            raise ValueError("redirect requires a task")
        return orchestrator.redirect_loop(name, task, note, root=root)
    raise ValueError(f"unknown action: {action}")


def _launch_loop_request(root: Path, form: dict[str, str]) -> dict:
    """Start a new supervised loop for a job into a persistent workspace."""

    job = form.get("job", "").strip()
    if not job:
        raise ValueError("job is required")
    model = form.get("model", "").strip() or None
    forever = str(form.get("forever", "")).lower() in {"1", "true", "yes", "on"}
    pid = orchestrator.launch_loop(job, model=model, forever=forever, root=root)
    return {"pid": pid, "job": job}


def _run_all_request(root: Path, form: dict[str, str]) -> dict:
    """Launch every non-green, not-running loop so they all keep trying."""

    model = form.get("model", "").strip() or None
    started = orchestrator.launch_pending(model=model, forever=True, root=root)
    return {"started": started}


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
        elif path == "/api/loops.json":
            body = json.dumps(_loops_payload(self.root), indent=2).encode("utf-8")
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
        if path == "/api/chat.json":
            self._serve_chat()
            return
        if path == "/api/plan.json":
            self._serve_plan()
            return
        if path == "/api/framework-manifest.json":
            self._serve_framework_manifest()
            return
        if path.startswith("/workspace/"):
            self._serve_workspace(path)
            return
        return super().do_GET()

    def _serve_framework_manifest(self) -> None:
        fid = parse_qs(urlparse(self.path).query).get("framework", [""])[0]
        try:
            raw = fw.raw_manifest(fid)
        except KeyError as exc:
            self._send(HTTPStatus.BAD_REQUEST, "text/plain; charset=utf-8", str(exc).encode())
            return
        body = json.dumps({"framework": fid, "manifest": raw}).encode("utf-8")
        self._send(HTTPStatus.OK, "application/json; charset=utf-8", body)

    def _serve_ws_query(self) -> Path | None:
        ws = parse_qs(urlparse(self.path).query).get("ws", [""])[0]
        return self._resolve_workspace(ws)

    def _serve_chat(self) -> None:
        target = self._serve_ws_query()
        if target is None:
            self._send(HTTPStatus.BAD_REQUEST, "text/plain; charset=utf-8", b"invalid workspace")
            return
        body = json.dumps({"messages": chat.read(target)}, indent=2).encode("utf-8")
        self._send(HTTPStatus.OK, "application/json; charset=utf-8", body)

    def _serve_plan(self) -> None:
        target = self._serve_ws_query()
        if target is None:
            self._send(HTTPStatus.BAD_REQUEST, "text/plain; charset=utf-8", b"invalid workspace")
            return
        body = json.dumps({"plan": plan_mod.read_plan(target)}, indent=2).encode("utf-8")
        self._send(HTTPStatus.OK, "application/json; charset=utf-8", body)

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

    def _handle_global_json(self, apply) -> None:
        """POST helper for global (non-workspace) edits that return JSON."""

        username = self._require_auth()
        if username is None:
            self._send(HTTPStatus.UNAUTHORIZED, "text/plain; charset=utf-8", b"login required")
            return
        size = int(self.headers.get("Content-Length", "0"))
        form = _parse_form(self.rfile.read(size))
        try:
            result = apply(form)
        except (KeyError, ValueError) as exc:
            body = json.dumps({"ok": False, "error": str(exc)}).encode("utf-8")
            self._send(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
            return
        body = json.dumps({"ok": True, "result": result}).encode("utf-8")
        self._send(HTTPStatus.OK, "application/json; charset=utf-8", body)

    def _handle_loop_json(self, apply) -> None:
        username = self._require_auth()
        if username is None:
            self._send(HTTPStatus.UNAUTHORIZED, "text/plain; charset=utf-8", b"login required")
            return
        size = int(self.headers.get("Content-Length", "0"))
        form = _parse_form(self.rfile.read(size))
        try:
            result = apply(self.root, form)
        except (KeyError, ValueError, RuntimeError, OSError) as exc:
            body = json.dumps({"ok": False, "error": str(exc)}).encode("utf-8")
            self._send(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
            return
        body = json.dumps({"ok": True, "result": result}).encode("utf-8")
        self._send(HTTPStatus.OK, "application/json; charset=utf-8", body)

    def _handle_ws_json(self, apply) -> None:
        """POST helper for endpoints that edit a workspace and return JSON."""

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
        try:
            result = apply(target, form)
        except (KeyError, ValueError, OSError) as exc:
            body = json.dumps({"ok": False, "error": str(exc)}).encode("utf-8")
            self._send(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
            return
        body = json.dumps({"ok": True, "result": result}).encode("utf-8")
        self._send(HTTPStatus.OK, "application/json; charset=utf-8", body)

    def _post_routes(self) -> dict:
        return {
            "/api/feedback": lambda: self._handle_workspace_post(_append_feedback, "message"),
            "/api/rules": lambda: self._handle_workspace_post(_append_rule, "rule"),
            "/api/chat": lambda: self._handle_workspace_post(_post_chat, "message"),
            "/api/plan": lambda: self._handle_ws_json(_apply_plan_op),
            "/api/framework-rule": self._handle_framework_rule,
            "/api/framework-add-rule": lambda: self._handle_global_json(_framework_add_rule),
            "/api/framework-delete-rule": lambda: self._handle_global_json(_framework_delete_rule),
            "/api/framework-manifest": (
                lambda: self._handle_global_json(_framework_replace_manifest)
            ),
            "/api/loop-control": lambda: self._handle_loop_json(_apply_loop_control),
            "/api/loop-launch": lambda: self._handle_loop_json(_launch_loop_request),
            "/api/loops-run-all": lambda: self._handle_loop_json(_run_all_request),
        }

    def do_POST(self):  # noqa: N802
        path = urlparse(self.path).path
        route = self._post_routes().get(path)
        if route is not None:
            route()
            return
        if path != "/login":
            self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"not found")
            return
        self._handle_login()

    def _handle_login(self) -> None:
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
    # Auto-reap launched loop supervisors so stopped loops don't linger as
    # zombies (which would otherwise read as "alive" on the floor).
    if hasattr(signal, "SIGCHLD"):
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)
    root = Path(args.root).expanduser().resolve()
    handler = partial(DashboardHandler, root=root)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    port = server.server_address[1]
    print(f"dashboard: http://127.0.0.1:{port}", flush=True)
    print(f"root: {root}", flush=True)
    print(f"user: {_user()}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
