#!/usr/bin/env python3
"""CLI for the local loop orchestrator.

Manage the code factory's loops from a terminal, with no dashboard and no
Copilot: list jobs, launch loops, and pause/resume/redirect/stop them.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qaymark import orchestrator  # noqa: E402  (path set up above)


def _print_jobs() -> int:
    for job in orchestrator.list_jobs():
        print(f"{job.name:24} {job.description}")
    return 0


def _print_loops() -> int:
    loops = orchestrator.list_loops()
    if not loops:
        print("no loops on the floor yet")
        return 0
    for loop in loops:
        state = "running" if loop["alive"] else "idle"
        if loop["paused"]:
            state = "paused"
        print(f"{loop['name']:24} {state:8} phase={loop['phase']} build={loop['build']}")
    return 0


def _launch(args: argparse.Namespace) -> int:
    pid = orchestrator.launch_loop(args.job, model=args.model, forever=args.forever)
    print(f"launched loop '{args.job}' (pid {pid})")
    return 0


def _run_all(args: argparse.Namespace) -> int:
    started = orchestrator.launch_pending(model=args.model, forever=True)
    if not started:
        print("nothing to run — every loop is green or already running")
        return 0
    print("launched:", ", ".join(started))
    return 0


def _control(action: str, args: argparse.Namespace) -> int:
    if action == "pause":
        orchestrator.pause_loop(args.name)
    elif action == "resume":
        orchestrator.resume_loop(args.name)
    elif action == "stop":
        orchestrator.stop_loop(args.name)
    elif action == "redirect":
        orchestrator.redirect_loop(args.name, args.task)
    print(f"{action} -> {args.name}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qaymark-loops", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("jobs", help="list launchable jobs")
    sub.add_parser("list", help="list loops on the floor")
    launch = sub.add_parser("launch", help="start a loop for a job")
    launch.add_argument("job")
    launch.add_argument("--model", default=None)
    launch.add_argument("--forever", action="store_true")
    run_all = sub.add_parser("run-all", help="run every non-green loop (they take turns)")
    run_all.add_argument("--model", default=None)
    for name in ("pause", "resume", "stop"):
        node = sub.add_parser(name, help=f"{name} a loop")
        node.add_argument("name")
    redirect = sub.add_parser("redirect", help="point a loop at a new task")
    redirect.add_argument("name")
    redirect.add_argument("task")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "jobs":
        return _print_jobs()
    if args.cmd == "list":
        return _print_loops()
    if args.cmd == "launch":
        return _launch(args)
    if args.cmd == "run-all":
        return _run_all(args)
    return _control(args.cmd, args)


if __name__ == "__main__":
    raise SystemExit(main())
