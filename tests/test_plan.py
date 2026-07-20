"""Tests for the workspace plan module."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qaymark import plan


class PlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ws = Path(tempfile.mkdtemp())
        (self.ws / ".harness").mkdir(parents=True, exist_ok=True)

    def test_ensure_creates_default_plan_with_active_step(self) -> None:
        created = plan.ensure_plan(self.ws, "Build a widget")
        self.assertEqual(created["goal"], "Build a widget")
        self.assertTrue(created["steps"])
        self.assertEqual(created["steps"][0]["status"], "active")

    def test_ensure_keeps_existing_plan(self) -> None:
        plan.ensure_plan(self.ws, "first goal")
        again = plan.ensure_plan(self.ws, "second goal")
        self.assertEqual(again["goal"], "first goal")

    def test_bootstrap_plan_prefers_model_generated_plan(self) -> None:
        generated = {
            "goal": "Ship the harness",
            "focus_note": "Keep the loop moving",
            "steps": [{"text": "inspect", "status": "active"}, "build", "verify"],
            "generated_by": "ollama",
            "generated_at": "now",
        }
        with mock.patch.object(plan, "generate_plan", return_value=generated):
            bootstrapped = plan.bootstrap_plan(
                self.ws,
                "fallback goal",
                plan.PlanSeed(
                    task="Build the harness",
                    snapshot="workspace snapshot",
                    rule_digest="ui-flow-completeness",
                    model="qwen2.5-coder:3b",
                    base_url="http://localhost:11434",
                ),
            )
        self.assertEqual(bootstrapped["generated_by"], "ollama")
        self.assertEqual(bootstrapped["goal"], "Ship the harness")
        self.assertEqual(bootstrapped["steps"][0]["status"], "active")
        self.assertEqual(plan.read_plan(self.ws)["generated_by"], "ollama")

    def test_add_update_remove_step(self) -> None:
        plan.ensure_plan(self.ws, "goal")
        updated = plan.add_step(self.ws, "extra step")
        step_id = updated["steps"][-1]["id"]
        plan.update_step(self.ws, step_id, "renamed step", "done")
        step = next(s for s in plan.read_plan(self.ws)["steps"] if s["id"] == step_id)
        self.assertEqual(step["text"], "renamed step")
        self.assertEqual(step["status"], "done")
        plan.remove_step(self.ws, step_id)
        ids = [s["id"] for s in plan.read_plan(self.ws)["steps"]]
        self.assertNotIn(step_id, ids)

    def test_set_active_is_exclusive(self) -> None:
        plan.ensure_plan(self.ws, "goal")
        steps = plan.read_plan(self.ws)["steps"]
        target = steps[2]["id"]
        plan.set_active(self.ws, target)
        result = plan.read_plan(self.ws)
        active = [s for s in result["steps"] if s["status"] == "active"]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["id"], target)

    def test_focus_note_and_prompt_text(self) -> None:
        plan.ensure_plan(self.ws, "Build Tetris")
        plan.set_focus_note(self.ws, "fixing hygiene")
        text = plan.plan_prompt_text(plan.read_plan(self.ws))
        self.assertIn("Build Tetris", text)
        self.assertIn("Focus now", text)

    def test_prompt_text_empty_plan(self) -> None:
        self.assertEqual(plan.plan_prompt_text({}), "")


if __name__ == "__main__":
    unittest.main()
