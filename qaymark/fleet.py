"""Parallel fleet runner: race several harness workers on one job.

Each worker gets its own workspace (seeded with the same spec + fixed tests),
runs the guardrailed loop independently, and the first to pass both the tests
and the strict hygiene gate wins. Remaining workers are terminated.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import shutil
from dataclasses import dataclass, replace
from pathlib import Path

from .config import HarnessConfig
from .loop import run_harness
from .references import ensure_idud_binary, ensure_slop_src


@dataclass
class FleetResult:
    winner: int | None
    result_dir: Path | None
    outcomes: dict[int, int]


def _worker(idx: int, config: HarnessConfig, queue: "mp.Queue[tuple[int, int]]") -> None:
    code = run_harness(config)
    queue.put((idx, code))


def _worker_config(base: HarnessConfig, idx: int) -> HarnessConfig:
    return replace(base, workspace=base.workspace / f"worker-{idx}")


def _pre_provision(config: HarnessConfig) -> None:
    """Provision tools once in the parent so workers never race on git."""

    ensure_slop_src(config.cache_dir)
    if config.use_idud:
        ensure_idud_binary(config.cache_dir)
    os.environ["QAYMARK_NO_REFRESH"] = "1"


def _collect(queue: "mp.Queue[tuple[int, int]]", workers: int) -> tuple[int | None, dict[int, int]]:
    outcomes: dict[int, int] = {}
    winner: int | None = None
    while len(outcomes) < workers:
        idx, code = queue.get()
        outcomes[idx] = code
        if code == 0:
            winner = idx
            break
    return winner, outcomes


def _promote_winner(config: HarnessConfig, winner: int | None) -> Path | None:
    if winner is None:
        return None
    result_dir = config.workspace / "result"
    if result_dir.exists():
        shutil.rmtree(result_dir)
    shutil.copytree(config.workspace / f"worker-{winner}", result_dir)
    return result_dir


def run_fleet(config: HarnessConfig, workers: int) -> FleetResult:
    """Run *workers* harness workers in parallel; first to pass wins."""

    config.workspace.mkdir(parents=True, exist_ok=True)
    _pre_provision(config)

    ctx = mp.get_context("fork")
    queue: "mp.Queue[tuple[int, int]]" = ctx.Queue()
    procs: dict[int, "mp.process.BaseProcess"] = {}
    for idx in range(workers):
        args = (idx, _worker_config(config, idx), queue)
        proc = ctx.Process(target=_worker, args=args, daemon=True)
        proc.start()
        procs[idx] = proc

    winner, outcomes = _collect(queue, workers)

    for idx, proc in procs.items():
        if idx != winner and proc.is_alive():
            proc.terminate()
    for proc in procs.values():
        proc.join(timeout=15)

    return FleetResult(winner=winner, result_dir=_promote_winner(config, winner), outcomes=outcomes)
