"""Command line interface for local mock loop runs."""

import argparse
import json
import os
import sys
from dataclasses import replace
from typing import List, Optional, TextIO

from orchestrator.config import BudgetConfig, OrchestratorConfig, default_config, load_config
from orchestrator.loop import LoopResult, LoopRunner, ValidationResult
from orchestrator.memory import MemoryStore
from orchestrator.sqlite_store import SQLiteEventLog, SQLiteMemoryStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loop-orchestrator",
        description="Run a mock-first Loop Orchestrator task.",
    )
    parser.add_argument("goal", help="User goal to run through the mock loop.")
    parser.add_argument("--task-id", default="task_cli_0001", help="Stable task id for the run.")
    parser.add_argument(
        "--config",
        help="Path to a JSON or TOML config file with budget, safety, and provider settings.",
    )
    parser.add_argument(
        "--memory-path",
        default="data/memory/project_store.json",
        help="Path to JSON memory store when --sqlite-path is not used.",
    )
    parser.add_argument(
        "--sqlite-path",
        help="Use SQLite-backed memory and event persistence at this path.",
    )
    parser.add_argument("--json", action="store_true", help="Emit the full result as JSON.")
    parser.add_argument("--events-out", help="Write event log JSON to this path.")
    parser.add_argument("--max-usd", type=float, help="Override the run budget in USD.")
    parser.add_argument(
        "--max-iterations",
        type=int,
        help="Override the maximum loop iterations.",
    )
    parser.add_argument(
        "--max-repair-attempts",
        type=int,
        help="Override the repair cap for one failure fingerprint.",
    )
    parser.add_argument(
        "--fail-fingerprint",
        help="Simulate validation failure with this fingerprint.",
    )
    parser.add_argument(
        "--fail-until",
        type=int,
        help="When simulating failure, fail through this iteration then pass. Omit to always fail.",
    )
    return parser


def make_config(args: argparse.Namespace) -> OrchestratorConfig:
    base = load_config(args.config) if args.config else default_config()
    budget = base.budget
    overrides = {}
    if args.max_usd is not None:
        overrides["max_usd"] = args.max_usd
    if args.max_iterations is not None:
        overrides["max_iterations"] = args.max_iterations
    if args.max_repair_attempts is not None:
        overrides["max_repair_attempts"] = args.max_repair_attempts
    if overrides:
        budget = replace(budget, **overrides)
    return OrchestratorConfig(
        project_id=base.project_id,
        budget=budget,
        safety=base.safety,
        providers=base.providers,
    )


def make_validator(args: argparse.Namespace):
    if not args.fail_fingerprint:
        return None

    def validator(iteration: int, response_text: str) -> ValidationResult:
        if args.fail_until is None or iteration <= args.fail_until:
            return ValidationResult.failure(
                args.fail_fingerprint,
                "Simulated validation failure for %s." % args.fail_fingerprint,
            )
        return ValidationResult.success("Simulated validation recovered.")

    return validator


def write_events(path: str, result: LoopResult) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(result.events, handle, sort_keys=True, indent=2)
        handle.write("\n")


def print_summary(result: LoopResult, stdout: TextIO) -> None:
    routing = result.routing
    stdout.write("status: %s\n" % result.status)
    stdout.write("task_id: %s\n" % result.task_id)
    stdout.write("tier: %s\n" % routing.tier)
    stdout.write("intent: %s\n" % routing.intent)
    stdout.write("risk: %s\n" % routing.risk)
    stdout.write("message: %s\n" % result.message)
    stdout.write("events: %d\n" % len(result.events))
    stdout.write("artifacts: %d\n" % len(result.artifacts))
    stdout.write("changed_artifacts: %d\n" % len(result.changed_artifacts))
    stdout.write("actual_usd: %.8f\n" % result.budget["actual_usd"])
    stdout.write("prompt_hash: %s\n" % result.prompt_hash)
    stdout.write("cacheable_hash: %s\n" % result.cacheable_hash)


def main(
    argv: Optional[List[str]] = None,
    stdout: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)

    config = make_config(args)
    if args.sqlite_path:
        memory = SQLiteMemoryStore.load(config.project_id, args.sqlite_path)
        events = SQLiteEventLog(args.sqlite_path, project_id=config.project_id)
    else:
        memory = MemoryStore.load(config.project_id, args.memory_path)
        events = None
    runner = LoopRunner(config=config, memory=memory, events=events)
    result = runner.run(args.goal, task_id=args.task_id, validator=make_validator(args))

    if args.events_out:
        write_events(args.events_out, result)

    if args.json:
        json.dump(result.to_dict(), stdout, sort_keys=True, indent=2)
        stdout.write("\n")
    else:
        print_summary(result, stdout)

    if result.status == "succeeded":
        return 0
    stderr.write("loop status: %s\n" % result.status)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
