#!/usr/bin/env python3
"""Persistent-session watchdog for one Gadi autoresearch controller."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
import campaign


RESTART_DELAYS = (15, 60, 300, 900)
IDLE_POLL_SECONDS = 60
_child: subprocess.Popen[str] | None = None
_stop = False


def stop_handler(signum: int, _frame: object) -> None:
    global _stop
    _stop = True
    if _child and _child.poll() is None:
        try:
            os.killpg(_child.pid, signum)
        except ProcessLookupError:
            pass


def controller_command(args: argparse.Namespace) -> list[str]:
    command = [
        args.python,
        args.controller,
        str(args.root),
        "--codex-bin",
        args.codex_bin,
        "--start",
        "--loop",
        "--poll-seconds",
        str(args.poll_seconds),
    ]
    if args.model:
        command.extend(["--model", args.model])
    if args.reasoning_effort:
        command.extend(["--reasoning-effort", args.reasoning_effort])
    return command


def run_controller(args: argparse.Namespace) -> int:
    global _child
    command = controller_command(args)
    print(
        json.dumps(
            {
                "event": "controller_launch",
                "campaign": str(args.root),
                "command": command,
            }
        ),
        flush=True,
    )
    _child = subprocess.Popen(command, start_new_session=True, text=True)
    try:
        return _child.wait()
    finally:
        _child = None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--controller", required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--codex-bin", required=True)
    parser.add_argument("--model")
    parser.add_argument("--reasoning-effort")
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--once", action="store_true", help="run at most one controller lifecycle")
    args = parser.parse_args(argv)
    if args.poll_seconds < 60:
        parser.error("--poll-seconds must be at least 60")
    args.root = campaign.canonical(args.root, strict=True)
    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGHUP, stop_handler)
    failures = 0
    last_idle: tuple[str, str] | None = None

    while not _stop:
        try:
            state = campaign.load_state(args.root)
        except (campaign.CampaignError, OSError) as exc:
            failures += 1
            delay = RESTART_DELAYS[min(failures - 1, len(RESTART_DELAYS) - 1)]
            print(f"supervisor state read failed; retry in {delay}s: {exc}", file=sys.stderr, flush=True)
            time.sleep(delay)
            continue
        status = state["status"]
        control = state["control"]["state"]
        if status in {"complete", "stopped"}:
            print(json.dumps({"event": "supervisor_complete", "status": status, "control": control}), flush=True)
            return 0
        if status != "active":
            idle = (status, control)
            if idle != last_idle:
                print(
                    json.dumps(
                        {
                            "event": "supervisor_idle",
                            "status": status,
                            "control": control,
                            "reason": state["control"].get("reason"),
                        }
                    ),
                    flush=True,
                )
                last_idle = idle
            if args.once:
                return 0
            time.sleep(IDLE_POLL_SECONDS)
            continue

        last_idle = None
        returncode = run_controller(args)
        if _stop:
            return 0
        current = campaign.load_state(args.root)
        print(
            json.dumps(
                {
                    "event": "controller_exit",
                    "returncode": returncode,
                    "status": current["status"],
                    "control": current["control"]["state"],
                }
            ),
            flush=True,
        )
        if args.once:
            return returncode
        if current["status"] != "active":
            failures = 0
            continue
        failures += 1
        delay = RESTART_DELAYS[min(failures - 1, len(RESTART_DELAYS) - 1)]
        print(f"controller will restart in {delay}s", flush=True)
        time.sleep(delay)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
