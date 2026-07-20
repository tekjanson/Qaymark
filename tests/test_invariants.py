"""Regression guards: the invariants that keep the factory actually working.

Each test here pins down a property we had to fix the hard way. They are the
executable "rules" for the system — if any regresses, this module fails, the
pre-commit hook and CI reject the change, and we cannot silently break the
factory again. Keep them fast and dependency-light (no network, no servers).
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from qaymark import health, keeper, ollama_client, operations, workspace
from qaymark import checkin
from qaymark.hygiene import HygieneResult
from qaymark.operations import OperationOutcome
from qaymark.prompt import build_system_prompt, synthesize_feedback
from qaymark.reference_bridge import ReferenceResult
from qaymark.report import AttemptReport


def _load_dashboard():
    spec = importlib.util.spec_from_file_location(
        "dashboard", Path(__file__).resolve().parent.parent / "scripts" / "dashboard.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class GenerationQualityInvariants(unittest.TestCase):
    """Rules that stop the model looping forever on broken/partial output."""

    def test_escaped_newlines_are_repaired(self) -> None:
        op = {"kind": "write_file", "path": "a.py", "content": "def f():\\n    return 1"}
        body = operations._content_from_operation(op)
        self.assertIn("\n", body)
        self.assertNotIn("\\n", body)

    def test_system_prompt_demands_complete_files_not_stubs(self) -> None:
        prompt = build_system_prompt("long-lines")
        self.assertIn("COMPLETE", prompt)
        self.assertIn("never a partial stub", prompt)
        self.assertNotIn("smallest safe chunk", prompt)

    def test_prompt_forbids_invented_subdirectories(self) -> None:
        # Weak models copy schema example paths verbatim; a nested example made
        # them write nested/fizzbuzz.py and fail every root-file contract.
        prompt = build_system_prompt("long-lines")
        self.assertIn("EXACT path", prompt)
        self.assertIn("workspace ROOT", prompt)
        self.assertNotIn("some/dir/file.py", prompt)

    def test_feedback_includes_full_written_file_content(self) -> None:
        root = Path(tempfile.mkdtemp())
        (root / "m.py").write_text("import os\nx = 1\n", encoding="utf-8")
        report = AttemptReport(
            1, False, "boom", HygieneResult(passed=False, violations=[]),
            ReferenceResult(), OperationOutcome(written=["m.py"]),
        )
        text = synthesize_feedback(report, root)
        self.assertIn("current full content", text)
        self.assertIn("import os", text)

    def test_contract_test_files_are_shown_in_full(self) -> None:
        root = Path(tempfile.mkdtemp())
        long_test = "\n".join(f"assert n == {i}" for i in range(200))
        (root / "test_it.py").write_text(long_test + "\n", encoding="utf-8")
        snap = workspace.summarize_workspace(root)
        self.assertIn("assert n == 199", snap)

    def test_plan_drops_empty_file_stub_steps(self) -> None:
        # A weak model plans "create an empty file X" first; honouring it makes
        # the one-shot generator write a blank file that fails forever.
        from qaymark import plan

        steps = plan._normalize_steps([
            "Create an empty file `fizzbuzz.py` at the workspace root.",
            "Define fizzbuzz(n) that returns the FizzBuzz list.",
        ])
        texts = [step["text"] for step in steps]
        self.assertEqual(len(texts), 1)
        self.assertIn("Define fizzbuzz", texts[0])
        self.assertEqual(steps[0]["status"], "active")


class RuntimeResilienceInvariants(unittest.TestCase):
    """Rules that stop a slow/wedged Ollama from freezing loops for hours."""

    def test_generation_has_a_wall_clock_deadline(self) -> None:
        # A dribbling stream that never sets done must still terminate.
        class _Slow:
            def __init__(self) -> None:
                self.calls = 0

            def __iter__(self):
                return self

            def __next__(self):
                self.calls += 1
                if self.calls > 5:
                    raise AssertionError("deadline did not stop the stream")
                return b'{"message": {"content": "x"}}'

        with mock.patch.object(ollama_client, "_deadline", return_value=-1):
            text = ollama_client._read_stream(_Slow(), None)
        self.assertEqual(text, "")

    def test_active_progress_is_healthy_without_probing_ollama(self) -> None:
        root = Path(tempfile.mkdtemp())
        art = root / "loop" / ".harness"
        art.mkdir(parents=True)
        (art / "generation.txt").write_text("streaming", encoding="utf-8")
        with mock.patch.object(health, "ollama_healthy",
                               side_effect=AssertionError("must not probe while working")):
            report = health.check(root, "http://x", "m", window=360)
        self.assertTrue(report.healthy)

    def test_recovery_only_when_stalled_and_ollama_down(self) -> None:
        root = Path(tempfile.mkdtemp())
        art = root / "loop" / ".harness"
        art.mkdir(parents=True)
        old = time.time() - 100000
        gen = art / "generation.txt"
        gen.write_text("frozen", encoding="utf-8")
        import os

        os.utime(gen, (old, old))
        with mock.patch.object(health, "ollama_healthy", return_value=False):
            self.assertFalse(health.check(root, "http://x", "m", window=360).healthy)
        with mock.patch.object(health, "ollama_healthy", return_value=True):
            # ollama up but stalled -> still unhealthy (stuck loop), never a false OK.
            self.assertFalse(health.check(root, "http://x", "m", window=360).progressing)


class KeeperInvariants(unittest.TestCase):
    """Rules that keep the keeper safe and non-thrashing."""

    def test_default_concurrency_cap_is_one(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("QAYMARK_MAX_ACTIVE_LOOPS", None)
            self.assertEqual(keeper._max_active(), 1)

    def test_keeper_launches_at_most_the_cap(self) -> None:
        root = Path(tempfile.mkdtemp())
        jobs = []
        for i in range(3):
            job = mock.Mock()
            job.name = f"job{i}"
            jobs.append(job)
        launched: list[str] = []
        with mock.patch.dict("os.environ", {"QAYMARK_MAX_ACTIVE_LOOPS": "1"}), \
                mock.patch.object(keeper.orchestrator, "list_jobs", return_value=jobs), \
                mock.patch.object(keeper, "_loops_by_name", return_value={}), \
                mock.patch.object(keeper.orchestrator, "launch_loop",
                                  side_effect=lambda name, **k: launched.append(name)), \
                mock.patch.object(keeper.chat, "post"):
            keeper.keep_once(root)
        self.assertEqual(len(launched), 1)

    def test_healthy_report_resets_unhealthy_streak(self) -> None:
        root = Path(tempfile.mkdtemp())
        ok = health.HealthReport(ollama_ok=True, progressing=True, detail="ok")
        with mock.patch.object(keeper.health, "check", return_value=ok):
            self.assertEqual(keeper.health_cycle(root, 9), 0)


class DashboardInvariants(unittest.TestCase):
    """Rules that keep `make up` and the live view honest and crash-free."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.dashboard = _load_dashboard()

    def test_make_up_survives_a_busy_port(self) -> None:
        import socket

        taken = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        busy = taken.getsockname()[1]
        from functools import partial

        handler = partial(self.dashboard.DashboardHandler, root=Path(tempfile.mkdtemp()))
        try:
            server = self.dashboard._bind_server(handler, busy)
        finally:
            taken.close()
        try:
            self.assertNotEqual(server.server_address[1], busy)
        finally:
            server.server_close()

    def test_stale_generation_marker_is_not_reported_active(self) -> None:
        art = Path(tempfile.mkdtemp())
        gen = art / "generation.txt"
        gen.write_text("half", encoding="utf-8")
        (art / "generation.state").write_text("active", encoding="utf-8")
        import os

        old = time.time() - 6000
        os.utime(gen, (old, old))
        status = self.dashboard._generation_status(art)
        self.assertFalse(status["active"])
        self.assertTrue(status["stale"])


class CheckinInvariants(unittest.TestCase):
    """Rules that guarantee passing work is *saved* (checked in), not lost."""

    def test_green_work_is_committed_and_idempotent(self) -> None:
        ws = Path(tempfile.mkdtemp())
        (ws / "app.py").write_text("x = 1\n", encoding="utf-8")
        first = checkin.checkin_green(ws, "job", 1)
        self.assertTrue(first["committed"], first)
        self.assertTrue((ws / ".git").exists())
        second = checkin.checkin_green(ws, "job", 1)
        self.assertFalse(second["committed"], "unchanged work must not re-commit")

    def test_harness_artifacts_are_not_committed(self) -> None:
        ws = Path(tempfile.mkdtemp())
        (ws / "app.py").write_text("x = 1\n", encoding="utf-8")
        art = ws / ".harness"
        art.mkdir()
        (art / "status.json").write_text("{}", encoding="utf-8")
        checkin.checkin_green(ws, "job", 1)
        tracked = checkin._git(ws, "ls-files").stdout
        self.assertIn("app.py", tracked)
        self.assertNotIn(".harness", tracked)

    def test_keeper_checks_in_only_green_loops(self) -> None:
        root = Path(tempfile.mkdtemp())
        green_ws = str(root / "g")
        loops = {
            "g": {"green": True, "build": 2, "workspace": green_ws},
            "r": {"green": False, "build": 0, "workspace": str(root / "r")},
        }
        seen: list[str] = []
        with mock.patch.object(keeper.checkin, "checkin_green",
                               side_effect=lambda ws, name, build: seen.append(name)
                               or {"committed": False}), \
                mock.patch.object(keeper.chat, "post"):
            keeper.checkin_green(root, loops, ["g", "r"])
        self.assertEqual(seen, ["g"])


class RoundRobinInvariants(unittest.TestCase):
    """Rules that stop one impossible job hogging the only worker forever."""

    def test_pending_rotate_least_recently_launched_first(self) -> None:
        root = Path(tempfile.mkdtemp())
        keeper._record_launch(root, "hard")
        order = keeper.rotate_pending(["easy", "hard"], root)
        self.assertEqual(order[0], "easy", "never-launched job must go first")

    def test_keeper_launches_bounded_turns_not_forever(self) -> None:
        root = Path(tempfile.mkdtemp())
        job = mock.Mock()
        job.name = "job0"
        calls: list[dict] = []
        with mock.patch.dict("os.environ", {"QAYMARK_MAX_ACTIVE_LOOPS": "1"}), \
                mock.patch.object(keeper.orchestrator, "list_jobs", return_value=[job]), \
                mock.patch.object(keeper, "_loops_by_name", return_value={}), \
                mock.patch.object(keeper.orchestrator, "launch_loop",
                                  side_effect=lambda name, **k: calls.append(k) or 1), \
                mock.patch.object(keeper.chat, "post"):
            keeper.keep_once(root)
        self.assertTrue(calls)
        self.assertFalse(calls[0].get("forever"), "keeper must launch bounded turns")


class StabilityInvariants(unittest.TestCase):
    """Rules that keep a green build green (no regenerating passing work)."""

    def test_green_marker_survives_reverted_status(self) -> None:
        from qaymark import orchestrator
        from qaymark.config import ARTIFACT_DIR_NAME

        ws = Path(tempfile.mkdtemp())
        art = ws / ARTIFACT_DIR_NAME
        art.mkdir()
        (art / "status.json").write_text('{"phase": "watching"}', encoding="utf-8")
        (art / "run-attempt-2.json").write_text(
            '{"validation_ok": false, "hygiene_passed": false}', encoding="utf-8"
        )
        self.assertFalse(orchestrator.is_green(ws))
        (art / "green.json").write_text('{"build": 1}', encoding="utf-8")
        self.assertTrue(orchestrator.is_green(ws), "durable green must not flip to red")

    def test_supervise_is_bounded_when_not_forever(self) -> None:
        from qaymark import cli
        from qaymark.config import HarnessConfig

        cfg = HarnessConfig(task="t", workspace=Path(tempfile.mkdtemp()))
        cfg.loop_forever = False
        seen: dict = {}

        def _fake(config, poll_interval, max_cycles):
            seen["max_cycles"] = max_cycles
            return mock.Mock(passed=True)

        with mock.patch("qaymark.factory.supervise", side_effect=_fake):
            cli._run_supervisor(cfg, 0.1)
        self.assertEqual(seen["max_cycles"], 1, "bounded turn must yield the worker")


if __name__ == "__main__":
    unittest.main()
