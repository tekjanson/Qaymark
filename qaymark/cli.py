"""Command-line entry point for the guardrailed harness."""

from __future__ import annotations

import argparse
from pathlib import Path

from .config import DEFAULT_MANIFEST, HarnessConfig, default_cache_dir
from .loop import run_harness


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qaymark",
        description="Guardrailed one-shot local code generation with Ollama, "
        "gated by slop-be-gone hygiene rules and the drift-be-gone map.",
    )
    parser.add_argument("--task", required=True, help="Natural-language task to implement")
    parser.add_argument("--workspace", required=True, help="Directory to work in")
    parser.add_argument(
        "--validation-command",
        default="python3 -m compileall -q .",
        help="Shell command that must exit 0 for success",
    )
    parser.add_argument("--max-attempts", type=int, default=None, help="Guardrailed attempt count")
    parser.add_argument("--model", default=None, help="Ollama model name")
    parser.add_argument("--base-url", default=None, help="Ollama base URL")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Path to sbg manifest")
    parser.add_argument("--cache-dir", default=None, help="Cache dir for the sbg/drift tools")
    parser.add_argument("--allow-commands", action="store_true", help="Permit run_command ops")
    parser.add_argument(
        "--forever", action="store_true", help="Retry forever until the gate passes"
    )
    parser.add_argument(
        "--no-reference", action="store_true", help="Skip the drift understanding map"
    )
    parser.add_argument("--no-strict", action="store_true", help="Do not fail on hygiene warnings")
    parser.add_argument("--seed", default=None, help="Dir of spec/test files to plant (protected)")
    parser.add_argument("--starter", default=None, help="Dir of starter files to plant (editable)")
    parser.add_argument("--workers", type=int, default=1, help="Parallel fleet workers (>1 races)")
    parser.add_argument(
        "--supervise",
        action="store_true",
        help="Stay alive after the build and rebuild whenever new feedback arrives",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Seconds between feedback checks in --supervise mode",
    )
    return parser


def config_from_args(args: argparse.Namespace) -> HarnessConfig:
    config = HarnessConfig(task=args.task, workspace=Path(args.workspace).expanduser())
    config.validation_command = args.validation_command
    config.manifest_path = Path(args.manifest).expanduser()
    config.cache_dir = Path(args.cache_dir).expanduser() if args.cache_dir else default_cache_dir()
    if args.max_attempts is not None:
        config.max_attempts = args.max_attempts
    if args.model is not None:
        config.model = args.model
    if args.base_url is not None:
        config.base_url = args.base_url
    if args.allow_commands:
        config.allow_commands = True
    if args.forever:
        config.loop_forever = True
    if args.no_reference:
        config.use_reference = False
    if args.no_strict:
        config.strict = False
    if args.seed:
        config.seed_dir = Path(args.seed).expanduser()
    if args.starter:
        config.starter_dir = Path(args.starter).expanduser()
    return config


def _run_fleet(config: HarnessConfig, workers: int) -> int:
    from .fleet import run_fleet

    result = run_fleet(config, workers)
    print(f"fleet outcomes (worker -> exit): {result.outcomes}", flush=True)
    if result.winner is None:
        print("fleet: no worker passed the gate", flush=True)
        return 1
    print(f"✅ fleet winner: worker-{result.winner} -> {result.result_dir}", flush=True)
    return 0


def _run_supervisor(config: HarnessConfig, poll_interval: float) -> int:
    from .factory import supervise

    # A forever loop supervises around the clock; a bounded turn builds to green
    # (up to max_attempts) then exits so it yields the shared worker slot and
    # never regenerates already-green work into red.
    max_cycles = None if config.loop_forever else 1
    result = supervise(config, poll_interval=poll_interval, max_cycles=max_cycles)
    return 0 if result.passed else 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = config_from_args(args)
    if args.workers and args.workers > 1:
        return _run_fleet(config, args.workers)
    if args.supervise:
        return _run_supervisor(config, args.poll_interval)
    return run_harness(config)


if __name__ == "__main__":
    raise SystemExit(main())
