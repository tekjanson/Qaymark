"""User-acceptance tests: drive the real dashboard server through every journey.

These exercise the actual HTTP endpoints a person uses — sign-in, the overview
and factory floor, governance, loop control, feedback, rules, and chat — so we
can audit that each customer journey works end to end, not just in unit form.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

_SPEC = importlib.util.spec_from_file_location(
    "dashboard", Path(__file__).resolve().parent.parent / "scripts" / "dashboard.py"
)
assert _SPEC is not None and _SPEC.loader is not None
dashboard = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = dashboard
_SPEC.loader.exec_module(dashboard)

from qaymark import chat, control  # noqa: E402


class UATBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ["DASHBOARD_USER"] = "admin"
        os.environ["DASHBOARD_PASSWORD"] = "secret"
        cls.root = Path(tempfile.mkdtemp())
        cls._seed_workspace("demo", "watching")
        handler = partial(dashboard.DashboardHandler, root=cls.root)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    @classmethod
    def _seed_workspace(cls, name: str, phase: str) -> Path:
        workspace = cls.root / name
        (workspace / ".harness").mkdir(parents=True, exist_ok=True)
        status = {"phase": phase, "attempt": 1, "max_attempts": 3}
        (workspace / ".harness" / "status.json").write_text(json.dumps(status), encoding="utf-8")
        return workspace

    def _url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def _request(self, path, data=None, cookie=None, method=None):
        body = None
        headers = {}
        if data is not None:
            body = urllib.parse.urlencode(data).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if cookie:
            headers["Cookie"] = cookie
        request = urllib.request.Request(self._url(path), data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, response.read().decode("utf-8"), response.headers
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8"), exc.headers

    def _login(self) -> str:
        request = urllib.request.Request(
            self._url("/login"),
            data=urllib.parse.urlencode({"username": "admin", "password": "secret"}).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        opener = urllib.request.build_opener(_NoRedirect())
        try:
            response = opener.open(request)
            set_cookie = response.headers.get("Set-Cookie", "")
        except urllib.error.HTTPError as exc:
            set_cookie = exc.headers.get("Set-Cookie", "")
        return set_cookie.split(";", 1)[0]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: D401, ANN001, ANN002
        return None


import urllib.parse  # noqa: E402  (used above)


class AuthJourneyTests(UATBase):
    def test_anonymous_sees_login(self) -> None:
        status, body, _ = self._request("/")
        self.assertEqual(status, 200)
        self.assertIn("Sign In", body)

    def test_bad_credentials_rejected(self) -> None:
        status, body, _ = self._request(
            "/login", data={"username": "admin", "password": "wrong"}, method="POST"
        )
        self.assertEqual(status, 401)
        self.assertIn("Invalid", body)

    def test_good_credentials_grant_a_session(self) -> None:
        cookie = self._login()
        self.assertTrue(cookie.startswith(dashboard.COOKIE_NAME))
        status, body, _ = self._request("/", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertIn("Control Plane", body)

    def test_protected_api_requires_login(self) -> None:
        status, _, _ = self._request(
            "/api/loop-control", data={"name": "demo", "action": "pause"}, method="POST"
        )
        self.assertEqual(status, 401)


class OverviewJourneyTests(UATBase):
    def test_overview_reports_readable_floor(self) -> None:
        cookie = self._login()
        status, body, _ = self._request("/api/overview.json", cookie=cookie)
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("counts", data)
        self.assertTrue(dashboard.floor_is_readable(data["floor"]))

    def test_console_and_governance_pages_load(self) -> None:
        cookie = self._login()
        for path in ("/console?ws=demo", "/governance"):
            status, body, _ = self._request(path, cookie=cookie)
            self.assertEqual(status, 200)
            self.assertIn("<html", body.lower())


class GovernanceJourneyTests(UATBase):
    def test_frameworks_list_and_toggle(self) -> None:
        cookie = self._login()
        status, body, _ = self._request("/api/frameworks.json", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["frameworks"])
        toggle, tbody, _ = self._request(
            "/api/framework-rule",
            data={
                "framework": "design-be-gone",
                "rule": "single-h1",
                "field": "enabled",
                "value": "false",
            },
            cookie=cookie,
            method="POST",
        )
        self.assertEqual(toggle, 200)
        self.assertTrue(json.loads(tbody)["ok"])
        # restore
        self._request(
            "/api/framework-rule",
            data={
                "framework": "design-be-gone",
                "rule": "single-h1",
                "field": "enabled",
                "value": "true",
            },
            cookie=cookie,
            method="POST",
        )


class LoopControlJourneyTests(UATBase):
    def test_loops_list_and_control(self) -> None:
        cookie = self._login()
        status, body, _ = self._request("/api/loops.json", cookie=cookie)
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertTrue(payload["jobs"])
        for action in ("pause", "resume", "stop"):
            code, cbody, _ = self._request(
                "/api/loop-control",
                data={"name": "demo", "action": action},
                cookie=cookie,
                method="POST",
            )
            self.assertEqual(code, 200, action)
            self.assertTrue(json.loads(cbody)["ok"], action)

    def test_redirect_sets_control_channel(self) -> None:
        cookie = self._login()
        self._request(
            "/api/loop-control",
            data={"name": "demo", "action": "redirect", "task": "build a widget"},
            cookie=cookie,
            method="POST",
        )
        self.assertEqual(
            control.read_control(self.root / "demo").redirect_task, "build a widget"
        )

    def test_launch_and_run_all_are_wired(self) -> None:
        cookie = self._login()
        with mock.patch.object(dashboard.orchestrator, "launch_loop", return_value=999):
            code, body, _ = self._request(
                "/api/loop-launch", data={"job": "tetris-web"}, cookie=cookie, method="POST"
            )
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["result"]["pid"], 999)
        with mock.patch.object(
            dashboard.orchestrator, "launch_pending", return_value=["tetris"]
        ):
            code, body, _ = self._request(
                "/api/loops-run-all", data={}, cookie=cookie, method="POST"
            )
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["result"]["started"], ["tetris"])


class FeedbackAndChatJourneyTests(UATBase):
    def test_feedback_and_rules_are_recorded(self) -> None:
        cookie = self._login()
        self._request(
            "/api/feedback", data={"workspace": "demo", "message": "too slow"},
            cookie=cookie, method="POST",
        )
        self._request(
            "/api/rules", data={"workspace": "demo", "rule": "always add a header"},
            cookie=cookie, method="POST",
        )
        harness = self.root / "demo" / ".harness"
        self.assertIn("too slow", (harness / "feedback.txt").read_text(encoding="utf-8"))
        self.assertIn("header", (harness / "rules.md").read_text(encoding="utf-8"))

    def test_chat_round_trip_and_feedback_steer(self) -> None:
        cookie = self._login()
        self._request(
            "/api/chat", data={"workspace": "demo", "message": "make it bigger"},
            cookie=cookie, method="POST",
        )
        status, body, _ = self._request("/api/chat.json?ws=demo", cookie=cookie)
        self.assertEqual(status, 200)
        roles = [m["role"] for m in json.loads(body)["messages"]]
        self.assertIn("operator", roles)
        self.assertIn("system", roles)
        feedback = (self.root / "demo" / ".harness" / "feedback.txt").read_text(encoding="utf-8")
        self.assertIn("make it bigger", feedback)

    def test_chat_redirect_command_redirects_the_loop(self) -> None:
        cookie = self._login()
        self._request(
            "/api/chat",
            data={"workspace": "demo", "message": "/redirect build a scoreboard"},
            cookie=cookie, method="POST",
        )
        self.assertEqual(
            control.read_control(self.root / "demo").redirect_task, "build a scoreboard"
        )


class PlanJourneyTests(UATBase):
    def test_plan_is_editable_from_the_console(self) -> None:
        cookie = self._login()
        self._request(
            "/api/plan", data={"workspace": "demo", "op": "set-goal", "goal": "Ship it"},
            cookie=cookie, method="POST",
        )
        self._request(
            "/api/plan", data={"workspace": "demo", "op": "add-step", "text": "write tests"},
            cookie=cookie, method="POST",
        )
        status, body, _ = self._request("/api/plan.json?ws=demo", cookie=cookie)
        self.assertEqual(status, 200)
        plan = json.loads(body)["plan"]
        self.assertEqual(plan["goal"], "Ship it")
        self.assertTrue(any(s["text"] == "write tests" for s in plan["steps"]))

    def test_set_active_step_directs_focus(self) -> None:
        cookie = self._login()
        self._request(
            "/api/plan", data={"workspace": "demo", "op": "add-step", "text": "step one"},
            cookie=cookie, method="POST",
        )
        _, body, _ = self._request("/api/plan.json?ws=demo", cookie=cookie)
        step_id = json.loads(body)["plan"]["steps"][0]["id"]
        self._request(
            "/api/plan", data={"workspace": "demo", "op": "set-active", "step": step_id},
            cookie=cookie, method="POST",
        )
        _, body, _ = self._request("/api/plan.json?ws=demo", cookie=cookie)
        active = [s for s in json.loads(body)["plan"]["steps"] if s["status"] == "active"]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["id"], step_id)


class BeGoneEditingJourneyTests(UATBase):
    def test_raw_manifest_is_readable(self) -> None:
        cookie = self._login()
        status, body, _ = self._request(
            "/api/framework-manifest.json?framework=design-be-gone", cookie=cookie
        )
        self.assertEqual(status, 200)
        self.assertIn("rules", json.loads(json.loads(body)["manifest"]))

    def test_add_then_delete_rule_round_trip(self) -> None:
        cookie = self._login()
        rule = json.dumps({"id": "uat-temp-rule", "type": "long-lines", "enabled": True})
        try:
            code, body, _ = self._request(
                "/api/framework-add-rule",
                data={"framework": "design-be-gone", "rule": rule},
                cookie=cookie, method="POST",
            )
            self.assertEqual(code, 200)
            self.assertTrue(json.loads(body)["ok"])
        finally:
            code, body, _ = self._request(
                "/api/framework-delete-rule",
                data={"framework": "design-be-gone", "rule": "uat-temp-rule"},
                cookie=cookie, method="POST",
            )
            self.assertEqual(code, 200)

    def test_invalid_rule_json_is_rejected(self) -> None:
        cookie = self._login()
        code, body, _ = self._request(
            "/api/framework-add-rule",
            data={"framework": "design-be-gone", "rule": "{not json"},
            cookie=cookie, method="POST",
        )
        self.assertEqual(code, 400)
        self.assertFalse(json.loads(body)["ok"])


if __name__ == "__main__":
    unittest.main()
