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
NOVELTY_REFERENCE = Path(__file__).resolve().parents[1] / "references" / "novelty-audit.md"
REASONING_EFFORTS = ("low", "medium", "high", "xhigh", "max", "ultra")


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


def ensure_skill_revision(root: Path) -> bool:
    with campaign.locked_state(root) as state:
        try:
            campaign.require_current_skill(state)
            campaign.pin_missing_skill_reference(state)
        except (campaign.CampaignError, OSError) as exc:
            state["status"] = "paused"
            state["control"].update({"state": "paused", "reason": f"skill revision check failed: {exc}"})
            campaign.add_history(state, "controller_skill_revision_failed", reason=str(exc))
            return False
    return True


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

Before planning or method experiments, read {NOVELTY_REFERENCE} and satisfy the machine-enforced novelty gate. Describe each candidate as mechanism primitives without its coined name, search exact/synonym/task/adjacent/combination/code/citation-neighbor routes, compare at least three checked primary sources, and write the bound IDEA_REPORT and NOVELTY_AUDIT.json artifacts. If the campaign predates this gate, stop implementation and move backward to novelty_review. Never write or register NOVELTY_REVIEW.json from the author thread: enter novelty_review and hand off with state needs_novelty_review so the controller launches a fresh adversarial reviewer. A rejected or application-only idea may continue only on its recorded diagnostic track; revise the idea before claiming a new method.

Work until one of these is true: PBS work must be awaited, explicit human input is required, a scheduled wake is appropriate, a safety/budget condition requires pause, or every completion artifact is verified and the campaign can be completed. Before this Codex turn exits, call campaign.py handoff with the correct state and concrete reason. A missing handoff pauses the controller rather than spinning another agent turn."""


def novelty_reviewer_prompt(root: Path, audit: dict[str, Any]) -> str:
    blind_packet = json.dumps(
        {
            "candidate_id": audit["candidate_id"],
            "mechanism_without_brand": audit["mechanism_without_brand"],
            "primitives": audit["primitives"],
        },
        indent=2,
        sort_keys=True,
    )
    return f"""Use $gadi-autoresearch as the cold, adversarial novelty reviewer for {root}.
This is intentionally a fresh Codex thread. You are not the author and must not continue implementation, edit the idea report or novelty audit, change phases/storage/approval, or register/submit/run experiments. Read {NOVELTY_REFERENCE} and campaign.json. Start from only this blind mechanism packet; do not open IDEA_REPORT.md, NOVELTY_AUDIT.json, LITERATURE.md, or the author's cited sources until you have independently chosen and inspected your own candidate sources:

{blind_packet}

Browse primary sources and inspect full papers plus official code when available. Independently cover exact mechanism, synonyms, task-local work, adjacent fields, primitive combinations, code search, and backward/forward citations. Seek the earliest prior, closest prior, newest relevant prior, and an exact-combination prior. Apply the brand-substitution and A+B decomposition tests. Default to derivative or unresolved unless the remaining delta is a technically non-obvious mechanism or interaction, not a renamed application, engineering integration, metric choice, or scale-up.

After fixing your independent source set and preliminary judgment, read the author artifacts, test the author's strongest rebuttal, and inspect additional cited sources where needed. Write the exact schema from {NOVELTY_REFERENCE} to {root}/NOVELTY_REVIEW.json. Bind it to the recorded audit hash, include at least three independently checked primary sources and a comparison for every primitive, then register it with assurance provisional using campaign.py. Hand off to needs_agent with a concrete verdict. If a reliable review cannot be completed, hand off to waiting_human instead of guessing. The controller will reject the review if this thread matches the author thread, the audit changed, the source workspace changes, the schema is incomplete, an old review is reused, or the required handoff is absent. A fresh same-family review is process-independent but remains scientifically provisional."""


def codex_prefix(
    codex_bin: str,
    model: str | None,
    reasoning_effort: str | None,
) -> list[str]:
    command = [codex_bin]
    if model:
        command.extend(["--model", model])
    if reasoning_effort:
        command.extend(["--config", f'model_reasoning_effort="{reasoning_effort}"'])
    return command


def codex_command(
    codex_bin: str,
    workspace: Path,
    state: dict[str, Any],
    root: Path,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> list[str]:
    thread_id = state["control"].get("thread_id")
    prompt = agent_prompt(root)
    common = [
        *codex_prefix(codex_bin, model, reasoning_effort),
        "exec",
        "--approve-for-me",
        "--add-dir",
        str(root),
    ]
    if thread_id:
        return [*common, "resume", "--json", thread_id, prompt]
    return [*common, "--json", "-C", str(workspace), prompt]


def novelty_codex_command(
    codex_bin: str,
    workspace: Path,
    root: Path,
    audit: dict[str, Any],
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> list[str]:
    common = [
        *codex_prefix(codex_bin, model, reasoning_effort),
        "exec",
        "--approve-for-me",
        "--add-dir",
        str(root),
    ]
    return [*common, "--json", "-C", str(workspace), novelty_reviewer_prompt(root, audit)]


def run_agent(
    root: Path,
    codex_bin: str,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> None:
    state = campaign.load_state(root)
    campaign.require_approved(state, "allow_auto_agent")
    campaign.require_current_skill(state)
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
        campaign.require_current_skill(current)
        current["control"].update({"state": "agent_running", "reason": "controller launched Codex"})
        campaign.add_history(current, "controller_transition", control_updates={"state": "agent_running"})
    command = codex_command(codex_bin, workspace, current, root, model, reasoning_effort)
    log_path = root / "controller.log"
    rotate_log(log_path)
    discovered_thread = None
    log = log_path.open("a", encoding="utf-8")
    returncode = 1
    try:
        log.write(
            f"\n[{campaign.utc_now()}] launch author: "
            f"model={model or 'config default'} "
            f"reasoning_effort={reasoning_effort or 'config default'}\n"
        )
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
            if event.get("type") == "thread.started":
                candidate = nested_thread_id(event)
                if candidate:
                    discovered_thread = candidate
        process.stdout.close()
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


def run_novelty_reviewer(
    root: Path,
    codex_bin: str,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> None:
    state = campaign.load_state(root)
    campaign.require_approved(state, "allow_auto_agent")
    campaign.require_current_skill(state)
    control = state["control"]
    if int(control["agent_turns"]) >= int(state["approval"]["max_agent_turns"]):
        pause_campaign(root, "approved Codex turn budget exhausted before novelty review")
        return
    try:
        audit_path = campaign.artifact_file(state, "novelty_audit")
        audit = campaign.validate_novelty_audit(state, audit_path)
        audit_sha256 = campaign.sha256_file(audit_path)
    except (campaign.CampaignError, OSError) as exc:
        pause_campaign(root, f"novelty reviewer input validation failed: {exc}")
        return
    author_thread_id = control.get("thread_id")
    review_requested_at = control.get("novelty_review_requested_at")
    try:
        campaign.live_preflight(state)
    except (campaign.CampaignError, OSError) as exc:
        pause_campaign(root, f"novelty reviewer preflight failed: {exc}")
        return
    workspace = campaign.canonical(state["workspace"], strict=True)
    campaign.validate_workspace(workspace)
    try:
        reviewer_workspace_commit = campaign.git_workspace_info(
            workspace,
            require_clean=True,
        )["commit"]
    except (campaign.CampaignError, OSError) as exc:
        pause_campaign(root, f"novelty reviewer requires a clean source workspace: {exc}")
        return
    if not shutil.which(codex_bin):
        pause_campaign(root, f"Codex executable is unavailable: {codex_bin}")
        return

    with campaign.locked_state(root) as current:
        if current["status"] != "active" or current["control"]["state"] != "needs_novelty_review":
            return
        campaign.require_approved(current, "allow_auto_agent")
        campaign.require_current_skill(current)
        try:
            current_audit = campaign.artifact_file(current, "novelty_audit")
            audit_unchanged = campaign.sha256_file(current_audit) == audit_sha256
        except (campaign.CampaignError, OSError) as exc:
            current["status"] = "paused"
            current["control"].update({
                "state": "paused",
                "reason": f"novelty audit became invalid before reviewer launch: {exc}",
            })
            campaign.add_history(current, "controller_novelty_review_input_changed", reason=str(exc))
            return
        if not audit_unchanged:
            current["status"] = "paused"
            current["control"].update({
                "state": "paused",
                "reason": "novelty audit changed before the cold reviewer launch",
            })
            campaign.add_history(current, "controller_novelty_review_input_changed", reason="hash changed")
            return
        previous_review = current["artifacts"].pop("novelty_review", None)
        current["control"].update({
            "state": "novelty_reviewer_running",
            "reason": "controller launched fresh adversarial novelty reviewer",
        })
        campaign.add_history(
            current,
            "controller_novelty_review_started",
            audit_sha256=audit_sha256,
            author_thread_id=author_thread_id,
            invalidated_review_sha256=(previous_review or {}).get("sha256"),
        )

    command = novelty_codex_command(
        codex_bin,
        workspace,
        root,
        audit,
        model,
        reasoning_effort,
    )
    log_path = root / "controller.log"
    rotate_log(log_path)
    discovered_thread = None
    log = log_path.open("a", encoding="utf-8")
    returncode = 1
    try:
        log.write(
            f"\n[{campaign.utc_now()}] launch novelty reviewer: "
            f"model={model or 'config default'} "
            f"reasoning_effort={reasoning_effort or 'config default'}\n"
        )
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
            pause_campaign(root, f"failed to launch novelty reviewer: {exc}")
            raise campaign.CampaignError(f"failed to launch novelty reviewer: {exc}") from exc
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
            if event.get("type") == "thread.started":
                candidate = nested_thread_id(event)
                if candidate:
                    discovered_thread = candidate
        process.stdout.close()
        returncode = process.wait()
        log.write(f"[{campaign.utc_now()}] novelty-review exit: {returncode}\n")
    finally:
        log.close()

    with campaign.locked_state(root) as updated:
        updated["control"]["agent_turns"] += 1
        updated["control"]["last_agent_at"] = campaign.utc_now()
        failure: str | None = None
        if returncode != 0:
            failure = f"novelty reviewer exited with status {returncode}; inspect controller.log"
        elif not discovered_thread:
            failure = "novelty reviewer returned no thread ID"
        elif discovered_thread == author_thread_id:
            failure = "novelty reviewer reused the author thread instead of a fresh context"
        else:
            try:
                current_audit = campaign.artifact_file(updated, "novelty_audit")
                if campaign.sha256_file(current_audit) != audit_sha256:
                    raise campaign.CampaignError("novelty audit changed during cold review")
                review_path = campaign.artifact_file(updated, "novelty_review")
                campaign.validate_novelty_review(updated, review_path)
                review_record = updated["artifacts"]["novelty_review"]
                if review_record.get("assurance") != "provisional":
                    raise campaign.CampaignError("same-family novelty review was not registered as provisional")
                if review_requested_at and campaign.parse_time(
                    review_record["recorded_at"]
                ) < campaign.parse_time(review_requested_at):
                    raise campaign.CampaignError("novelty reviewer reused an artifact from before this request")
                current_workspace = campaign.git_workspace_info(workspace, require_clean=True)
                if current_workspace["commit"] != reviewer_workspace_commit:
                    raise campaign.CampaignError("novelty reviewer changed the source workspace commit")
            except (campaign.CampaignError, OSError) as exc:
                failure = f"cold novelty review validation failed: {exc}"
        if not failure and updated["control"]["state"] == "novelty_reviewer_running":
            failure = "novelty reviewer exited without the required campaign handoff"
        if not failure and updated["control"]["state"] not in {"needs_agent", "waiting_human", "paused"}:
            failure = f"novelty reviewer used an invalid handoff: {updated['control']['state']}"

        if failure:
            updated["status"] = "paused"
            updated["control"].update({"state": "paused", "reason": failure})
        else:
            review_record = updated["artifacts"]["novelty_review"]
            review_record.update({
                "cold_review": True,
                "review_thread_id": discovered_thread,
                "author_thread_id": author_thread_id,
                "reviewed_audit_sha256": audit_sha256,
            })
            updated["control"]["novelty_review_thread_id"] = discovered_thread
        campaign.add_history(
            updated,
            "novelty_review_turn_finished",
            returncode=returncode,
            review_thread_id=discovered_thread,
            author_thread_id=author_thread_id,
            validated=not failure,
            failure=failure,
        )


def describe_action(state: dict[str, Any]) -> str:
    control = state["control"]["state"]
    if state["status"] != "active":
        return f"stop: campaign status is {state['status']}"
    if control == "needs_agent":
        return "invoke or resume one Codex turn"
    if control == "needs_novelty_review":
        return "launch one fresh adversarial novelty-review thread"
    if control == "waiting_pbs":
        return "refresh PBS no more than once every 600 seconds"
    if control == "waiting_time":
        return f"wait until {state['control'].get('wake_at')}"
    return f"stop and wait: {control}"


def tick(
    root: Path,
    codex_bin: str,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> bool:
    state = campaign.load_state(root)
    if state["status"] != "active":
        return False
    if not ensure_skill_revision(root):
        return False
    state = campaign.load_state(root)
    if campaign.parse_time(state["approval"]["deadline"]) <= dt.datetime.now(dt.timezone.utc):
        pause_campaign(root, "campaign approval deadline expired")
        return False
    control = state["control"]["state"]
    if control in {"agent_running", "novelty_reviewer_running"}:
        duplicate_reason = (
            "stale agent_running state; inspect the control host before resuming to avoid duplicate agents"
            if control == "agent_running"
            else "stale novelty_reviewer_running state; inspect the control host before resuming to avoid duplicate reviewers"
        )
        with campaign.locked_state(root) as current:
            current["status"] = "paused"
            current["control"].update({
                "state": "paused",
                "reason": duplicate_reason,
            })
            campaign.add_history(current, "controller_paused_stale_process", stale_state=control)
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
        run_agent(root, codex_bin, model, reasoning_effort)
    elif control == "needs_novelty_review":
        run_novelty_reviewer(root, codex_bin, model, reasoning_effort)
    return campaign.load_state(root)["status"] == "active"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--model", help="explicit Codex model for every author and reviewer turn")
    parser.add_argument(
        "--reasoning-effort",
        choices=REASONING_EFFORTS,
        help="explicit Codex reasoning effort for every author and reviewer turn",
    )
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
            print(json.dumps({
                "campaign": state["campaign_id"],
                "action": describe_action(state),
                "agent": {
                    "model": args.model or "config default",
                    "reasoning_effort": args.reasoning_effort or "config default",
                },
                "control": state["control"],
            }, indent=2))
            return 0
        campaign.require_approved(state)
        campaign.require_approved(state, "allow_auto_agent")
        with controller_lock(root):
            while True:
                active = tick(root, args.codex_bin, args.model, args.reasoning_effort)
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
