#!/usr/bin/env python3
"""Event-driven Codex controller for an approved Gadi autoresearch campaign."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterator

sys.dont_write_bytecode = True
import campaign


MAX_LOG_BYTES = 5 * 1024 * 1024


def rotate_log(path: Path) -> None:
    if not path.exists() or path.stat().st_size < MAX_LOG_BYTES:
        return
    previous = path.with_suffix(".previous.log")
    previous.unlink(missing_ok=True)
    path.replace(previous)


@contextlib.contextmanager
def controller_lock(root: Path) -> Iterator[None]:
    path = root / "controller.lock"
    with path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise campaign.CampaignError("another controller already owns this campaign") from exc
        yield
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def nested_thread_id(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("thread_id", "threadId", "session_id", "sessionId"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
        for child in value.values():
            candidate = nested_thread_id(child)
            if candidate:
                return candidate
    elif isinstance(value, list):
        for child in value:
            candidate = nested_thread_id(child)
            if candidate:
                return candidate
    return None


def set_control(root: Path, **updates: Any) -> None:
    with campaign.locked_state(root) as state:
        state["control"].update(updates)
        campaign.add_history(state, "controller_transition", control_updates=updates)


def pause_campaign(root: Path, reason: str) -> None:
    with campaign.locked_state(root) as state:
        state["status"] = "paused"
        state["control"].update({"state": "paused", "reason": reason})
        campaign.add_history(state, "controller_paused", reason=reason)


def wake_due(root: Path, state: dict[str, Any]) -> bool:
    if state["control"]["state"] != "waiting_time":
        return False
    wake_at = state["control"].get("wake_at")
    if not wake_at:
        pause_campaign(root, "waiting_time has no wake_at")
        return False
    if campaign.parse_time(wake_at) <= dt.datetime.now(dt.timezone.utc):
        set_control(root, state="needs_agent", reason=f"scheduled wake reached: {wake_at}", wake_at=None)
        return True
    return False


def refresh_pbs(root: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(campaign.worker_cli_path()), "refresh", str(root)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return
    if "once per 600 seconds" in result.stderr:
        return
    pause_campaign(root, f"PBS refresh failed: {result.stderr.strip()}")


def agent_prompt(root: Path) -> str:
    return f"""Use $gadi-autoresearch and resume the approved campaign at {root}.
Read campaign.json and the research workspace directly. Continue the full idea-to-paper workflow within the recorded project, SU, GPU, walltime, deadline, and persistent-file envelope. Use campaign.py for all experiment registration, previews, submissions, refreshes, artifacts, phases, and handoffs. Never call raw qsub/qdel, never compute on the login or persistent-session host, and never write workload data under .codex.

Work until one of these is true: PBS work must be awaited, explicit human input is required, a scheduled wake is appropriate, a safety/budget condition requires pause, or every completion artifact is verified and the campaign can be completed. Before this Codex turn exits, call campaign.py handoff with the correct state and concrete reason. A missing handoff pauses the controller rather than spinning another agent turn."""


def codex_command(codex_bin: str, workspace: Path, state: dict[str, Any], root: Path) -> list[str]:
    thread_id = state["control"].get("thread_id")
    prompt = agent_prompt(root)
    common = [codex_bin, "exec", "--approve-for-me", "--add-dir", str(root)]
    if thread_id:
        return [*common, "resume", "--json", thread_id, prompt]
    return [*common, "--json", "-C", str(workspace), prompt]


def run_agent(root: Path, codex_bin: str) -> None:
    state = campaign.load_state(root)
    campaign.require_approved(state, "allow_auto_agent")
    control = state["control"]
    if int(control["agent_turns"]) >= int(state["approval"]["max_agent_turns"]):
        pause_campaign(root, "approved Codex turn budget exhausted")
        return
    try:
        campaign.live_preflight(state)
    except (campaign.CampaignError, OSError) as exc:
        with campaign.locked_state(root) as current:
            current["status"] = "paused"
            current["control"].update({"state": "paused", "reason": f"agent preflight failed: {exc}"})
            campaign.add_history(current, "controller_agent_preflight_failed", reason=str(exc))
        return
    workspace = campaign.canonical(state["workspace"], strict=True)
    campaign.validate_workspace(workspace)
    if not shutil.which(codex_bin):
        pause_campaign(root, f"Codex executable is unavailable: {codex_bin}")
        return

    with campaign.locked_state(root) as current:
        if current["status"] != "active" or current["control"]["state"] != "needs_agent":
            return
        campaign.require_approved(current, "allow_auto_agent")
        current["control"].update({"state": "agent_running", "reason": "controller launched Codex"})
        campaign.add_history(current, "controller_transition", control_updates={"state": "agent_running"})
    command = codex_command(codex_bin, workspace, current, root)
    log_path = root / "controller.log"
    rotate_log(log_path)
    discovered_thread = None
    log = log_path.open("a", encoding="utf-8")
    returncode = 1
    try:
        log.write(f"\n[{campaign.utc_now()}] launch: {' '.join(command[:4])}\n")
        log.flush()
        try:
            process = subprocess.Popen(
                command,
                cwd=workspace,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            pause_campaign(root, f"failed to launch Codex: {exc}")
            raise campaign.CampaignError(f"failed to launch Codex: {exc}") from exc
        assert process.stdout is not None
        for line in process.stdout:
            log.write(line)
            if log.tell() >= MAX_LOG_BYTES:
                log.flush()
                log.close()
                rotate_log(log_path)
                log = log_path.open("a", encoding="utf-8")
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "thread.started" or not current["control"].get("thread_id"):
                candidate = nested_thread_id(event)
                if candidate:
                    discovered_thread = candidate
        returncode = process.wait()
        log.write(f"[{campaign.utc_now()}] exit: {returncode}\n")
    finally:
        log.close()

    with campaign.locked_state(root) as updated:
        if discovered_thread:
            updated["control"]["thread_id"] = discovered_thread
        updated["control"]["agent_turns"] += 1
        updated["control"]["last_agent_at"] = campaign.utc_now()
        if returncode != 0:
            updated["status"] = "paused"
            updated["control"].update({"state": "paused", "reason": f"Codex exited with status {returncode}; inspect controller.log"})
        elif not updated["control"].get("thread_id"):
            updated["status"] = "paused"
            updated["control"].update({
                "state": "paused",
                "reason": "Codex returned no resumable thread ID; refusing to create unbounded session files",
            })
        elif updated["control"]["state"] == "agent_running":
            updated["status"] = "paused"
            updated["control"].update({"state": "paused", "reason": "Codex exited without the required campaign handoff"})
        campaign.add_history(updated, "agent_turn_finished", returncode=returncode, thread_id=discovered_thread or updated["control"].get("thread_id"))


def describe_action(state: dict[str, Any]) -> str:
    control = state["control"]["state"]
    if state["status"] != "active":
        return f"stop: campaign status is {state['status']}"
    if control == "needs_agent":
        return "invoke or resume one Codex turn"
    if control == "waiting_pbs":
        return "refresh PBS no more than once every 600 seconds"
    if control == "waiting_time":
        return f"wait until {state['control'].get('wake_at')}"
    return f"stop and wait: {control}"


def tick(root: Path, codex_bin: str) -> bool:
    state = campaign.load_state(root)
    if state["status"] != "active":
        return False
    if campaign.parse_time(state["approval"]["deadline"]) <= dt.datetime.now(dt.timezone.utc):
        pause_campaign(root, "campaign approval deadline expired")
        return False
    control = state["control"]["state"]
    if control == "agent_running":
        with campaign.locked_state(root) as current:
            current["status"] = "paused"
            current["control"].update({
                "state": "paused",
                "reason": "stale agent_running state; inspect the control host before resuming to avoid duplicate agents",
            })
            campaign.add_history(current, "controller_paused_stale_agent")
        return False
    if control == "waiting_time":
        wake_due(root, state)
        state = campaign.load_state(root)
        control = state["control"]["state"]
    if control == "waiting_pbs":
        refresh_pbs(root)
        state = campaign.load_state(root)
        control = state["control"]["state"]
    if control == "needs_agent":
        run_agent(root, codex_bin)
    return campaign.load_state(root)["status"] == "active"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--poll-seconds", type=int, default=600)
    parser.add_argument("--start", action="store_true", help="perform controller actions; preview is default")
    parser.add_argument("--loop", action="store_true", help="keep watching until the campaign pauses or completes")
    args = parser.parse_args(argv)
    try:
        root = campaign.canonical(args.root, strict=True)
        state = campaign.load_state(root)
        campaign.require_approved(state, require_active=False, allow_expired=True)
        if args.poll_seconds < 600:
            raise campaign.CampaignError("poll-seconds must be at least 600")
        expired = campaign.parse_time(state["approval"]["deadline"]) <= dt.datetime.now(dt.timezone.utc)
        if expired:
            if args.start and state["status"] == "active":
                with campaign.locked_state(root) as current:
                    current["status"] = "paused"
                    current["control"].update({
                        "state": "paused",
                        "reason": "campaign approval deadline expired; inspect active jobs and reapprove deliberately",
                    })
                    campaign.add_history(current, "controller_paused_expired_approval")
            print(json.dumps({"campaign": state["campaign_id"], "action": "stop: approval deadline expired"}, indent=2))
            return 0
        if not args.start:
            print(json.dumps({"campaign": state["campaign_id"], "action": describe_action(state), "control": state["control"]}, indent=2))
            return 0
        campaign.require_approved(state)
        campaign.require_approved(state, "allow_auto_agent")
        with controller_lock(root):
            while True:
                active = tick(root, args.codex_bin)
                if not args.loop or not active:
                    break
                state = campaign.load_state(root)
                if state["control"]["state"] in {"waiting_human", "paused", "complete"}:
                    break
                time.sleep(args.poll_seconds)
    except (campaign.CampaignError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
