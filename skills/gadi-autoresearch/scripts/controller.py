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
ADAPTER_REFERENCE = Path(__file__).resolve().parents[1] / "references" / "adapter-system.md"
WORKFLOW_REFERENCE = Path(__file__).resolve().parents[1] / "references" / "research-workflow.md"
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


def agent_prompt(root: Path, state: dict[str, Any]) -> str:
    route = state.get("route", {})
    route_references = route.get("references") or ["references/adapter-system.md"]
    absolute_references = [str(Path(__file__).resolve().parents[1] / reference.split("#", 1)[0]) for reference in route_references]
    reference_packet = json.dumps(
        {
            "mission_sha256": state.get("mission_sha256"),
            "route_status": route.get("status"),
            "route_sha256": route.get("sha256"),
            "selected_adapters": route.get("adapters", []),
            "route_references": absolute_references,
        },
        indent=2,
        sort_keys=True,
    )
    novelty_probe_packet = json.dumps(
        campaign.novelty_probe_limits(state),
        indent=2,
        sort_keys=True,
    )
    return f"""Use $gadi-autoresearch and resume the approved campaign at {root}.
Read MISSION.json, campaign.json, {ADAPTER_REFERENCE}, {WORKFLOW_REFERENCE}, and the research workspace directly. The mission is immutable and defines which final contribution classes are acceptable. Continue the evidence-led discovery-to-paper workflow within the recorded project, SU, GPU, walltime, deadline, and persistent-file envelope. Use campaign.py for route selection, experiment registration, previews, submissions, refreshes, artifacts, phases, and handoffs. Never call raw qsub/qdel, never compute on the login or persistent-session host, and never write workload data under .codex.

Current adapter packet:
{reference_packet}

During territory and discovery, map task/model/lever/evidence opportunities, run only bounded observation probes, and resolve an explicit dependency-complete route with campaign.py route-set before portfolio. Inspect every selected adapter's required evidence, discovery questions, novelty traps, and linked references. Treat human_evaluation=conditional as a claim-dependent decision: any perceived-quality or preference claim must select the required perceptual/human evidence route before leaving discovery. Write one compact DISCOVERY_REPORT.md and a machine-readable CANDIDATE_PORTFOLIO.json with the mission-required number of viable candidates. Each candidate needs an observation, causal hypothesis, mechanism, predicted signature, falsifier, cheap distinguishing test, nearest-work delta, and estimated SU/job/file cost. Do not promote a branded idea without an observed or formally defined problem.

Before planning or claim-bearing experiments, read {NOVELTY_REFERENCE} and satisfy the machine-enforced novelty gate. Bind the audit to the mission, route, candidate portfolio, and idea report. Describe the active candidate as mechanism primitives without its coined name, search exact/synonym/task/adjacent/combination/code/citation-neighbor routes, compare at least three checked primary sources, and write the bound IDEA_REPORT and NOVELTY_AUDIT.json artifacts. Never write or register NOVELTY_REVIEW.json from the author thread: enter novelty_review and hand off with state needs_novelty_review so the controller launches a fresh adversarial reviewer. A legacy derivative/rejected review is not automatically upgraded under this skill revision: either refine/replace the candidate or produce a fresh bound audit and request a fresh review.

The cold reviewer has three current outcomes. clear_to_plan opens planning. exact_prior_reject requires a checked functionally equivalent prior and sends the candidate back to discovery/portfolio. conditional_probe means no exact prior was found but the paper-facing delta depends on an empirical interaction. In that case, remain in novelty_review and run only stage=novelty_probe experiments bound to the review. Current hard caps are:
{novelty_probe_packet}
After one to three completed probes, write the exact bound NOVELTY_REBUTTAL.json schema, register it as provisional, and hand off with state needs_novelty_arbitration. Never write NOVELTY_ARBITRATION.json yourself. A fresh third Codex thread decides clear_to_plan or exact_prior_reject. No pilot, main, ablation, paper-facing baseline, or full implementation work is allowed until final clearance. Preserve the observation when rejected. Never silently downgrade a requested method, architecture, objective, representation, system, data, evaluation, empirical, or theory contribution into an application, reproduction, or diagnostic paper.

Before final novelty clearance, candidate-independent environment/data/model setup is permitted only through campaign.py external-submit within its small discovery-infrastructure cap. Environments must be assembled in PBS jobfs and published as one immutable .sqsh under /g/data/wa66/Xiangyu/enviroment_cache. Datasets must be downloaded/expanded in PBS jobfs and published as packed objects under /g/data/wa66/Xiangyu/Data. A public pretrained model may be acquired only when approval.allow_model_publish=true: use stage=model on copyq, pin an immutable source revision and license, download and validate in PBS jobfs, invoke the audited packer, and publish exactly one .tar.zst directly under /g/data/wa66/Xiangyu/Data/models. Register that archive as a data input, and expand it only into each compute job's PBS jobfs. Never persist expanded dependency trees, dataset trees, model repositories, model shards, or Hugging Face/package caches.

If the selected route requires human evaluation, generate only a packed blinded study bundle, predeclare the protocol, and hand off to waiting_human. Never invent ratings, listeners, consent, demographics, or human-study results. Keep all expanded audio/media samples in PBS jobfs and publish only bounded archives, manifests, aggregate metrics, and a small declared demo subset.

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

Browse primary sources and inspect full papers plus official code when available. Independently cover exact mechanism, synonyms, task-local work, adjacent fields, primitive combinations, code search, and backward/forward citations. Seek the earliest prior, closest prior, newest relevant prior, and a functionally equivalent exact-combination prior. Apply brand substitution and A+B decomposition precisely: transfer of a broad primitive to another ordered modality does not by itself disprove novelty, and replacing the application label defeats only a domain-exclusive claim or a mechanism that remains functionally unchanged. "One could combine A+B" is not evidence of an existing or obvious combination.

Return exactly one current decision. Use exact_prior_reject only when a checked primary source implements the functionally equivalent mechanism; set exact_combination.functionally_equivalent=true and give concrete equivalence evidence. Use clear_to_plan when no exact prior was found and the technically non-obvious delta is adequately established, with no blocking overlap. Use conditional_probe when no exact prior was found, but whether the proposed interaction exceeds a naive A+B baseline is an empirical fact that a cheap distinguishing experiment can resolve. For conditional_probe, provide the schema's probe_plan with the question, naive-combination baseline, distinguishing outcome, and falsifier. Do not hard-reject merely because all primitives are individually known. A system, architecture, data, evaluation, empirical, or theory contribution may be valid when its mission-accepted claim and evidence standard are met; do not mislabel ordinary integration, metric choice, or scale-up as one.

After fixing your independent source set and preliminary judgment, read the mission, route, candidate portfolio, and author artifacts, test the author's strongest rebuttal, and inspect additional cited sources where needed. Classify the actual contribution even when it is outside the mission; the controller will force the author back to discovery rather than accepting a silent downgrade. Write the exact schema from {NOVELTY_REFERENCE} to {root}/NOVELTY_REVIEW.json. Bind it to the recorded audit hash, include at least three independently checked primary sources and a comparison for every primitive, then register it with assurance provisional using campaign.py. Hand off to needs_agent with a concrete verdict. If a reliable review cannot be completed, hand off to waiting_human instead of guessing. The controller will reject the review if this thread matches the author thread, the audit changed, the source workspace changes, the schema is incomplete, an old review is reused, or the required handoff is absent. A fresh same-family review is process-independent but remains scientifically provisional."""


def novelty_arbiter_prompt(root: Path, rebuttal: dict[str, Any]) -> str:
    packet = json.dumps(
        {
            "candidate_id": rebuttal["candidate_id"],
            "audit_sha256": rebuttal["audit_sha256"],
            "review_sha256": rebuttal["review_sha256"],
            "probe_experiment_ids": rebuttal["probe_experiment_ids"],
            "naive_combination_baseline": rebuttal["naive_combination_baseline"],
            "distinguishing_result": rebuttal["distinguishing_result"],
        },
        indent=2,
        sort_keys=True,
    )
    return f"""Use $gadi-autoresearch as the independent novelty arbiter for {root}.
This is a fresh third Codex thread, distinct from both author and cold reviewer. Do not continue the research, edit author/reviewer artifacts, change phases/storage/approval, or register/submit/run experiments. Read {NOVELTY_REFERENCE}, campaign.json, the bound novelty audit, cold review, author rebuttal, completed novelty-probe success markers, and relevant primary sources. The arbitration packet is:

{packet}

Judge the paper-facing contribution, not whether each primitive exists independently. Check that the probe is valid, that the stated naive A+B baseline is faithful and competitive, that the distinguishing result supports a non-obvious interaction rather than tuning or branding, and that the evidence addresses every blocking reviewer objection. Transfer to another modality is not automatically novel or derivative; decide from the mechanism and evidence. Search additional primary sources when needed.

Write the exact NOVELTY_ARBITRATION.json schema from {NOVELTY_REFERENCE} to {root}/NOVELTY_ARBITRATION.json and register it as provisional with campaign.py. The only decisions are clear_to_plan and exact_prior_reject. clear_to_plan requires a mission-accepted primary contribution, no blocking issues, and no exact prior. exact_prior_reject requires a checked primary source that is functionally equivalent, with exact_prior.functionally_equivalent=true and concrete equivalence evidence. If the evidence is merely weak or the probe is invalid but no exact prior exists, do not invent a hard rejection: use waiting_human and explain what cannot be decided. Hand off to needs_agent after recording a valid arbitration. The controller rejects reused threads, changed inputs, workspace changes, incomplete schemas, and missing handoffs."""


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
    prompt = agent_prompt(root, state)
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


def novelty_arbiter_codex_command(
    codex_bin: str,
    workspace: Path,
    root: Path,
    rebuttal: dict[str, Any],
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
    return [*common, "--json", "-C", str(workspace), novelty_arbiter_prompt(root, rebuttal)]


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
                campaign.validate_novelty_review(
                    updated,
                    review_path,
                    current_decisions_only=True,
                )
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
            review_payload = campaign.json_object(review_path, "novelty review")
            if review_payload["decision"] in campaign.NOVELTY_PROBE_DECISIONS:
                try:
                    campaign.current_probe_binding(updated)
                except campaign.CampaignError as exc:
                    updated.pop("research_track", None)
                    if updated["mission"]["fallback_policy"] == "wait_human":
                        fallback_phase = "novelty_review"
                        updated["control"].update(
                            {
                                "state": "waiting_human",
                                "reason": f"conditional novelty review requires a user decision: {exc}",
                            }
                        )
                    else:
                        portfolio = campaign.validate_candidate_portfolio(
                            updated,
                            campaign.artifact_file(updated, "candidate_portfolio"),
                        )
                        has_backup = any(
                            candidate.get("status") == "backup"
                            for candidate in portfolio["candidates"]
                        )
                        fallback_phase = "portfolio" if has_backup else "discovery"
                        updated["phase"] = fallback_phase
                        updated["control"].update(
                            {
                                "state": "needs_agent",
                                "reason": f"conditional novelty review is outside the mission: {exc}; return to {fallback_phase}",
                            }
                        )
                    campaign.add_history(
                        updated,
                        "novelty_review_fallback",
                        decision=review_payload["decision"],
                        claim_class=review_payload["claim_class"],
                        fallback_phase=fallback_phase,
                        reason=str(exc),
                    )
                else:
                    updated.pop("research_track", None)
                    updated["phase"] = "novelty_review"
                    updated["control"].update(
                        {
                            "state": "needs_agent",
                            "reason": (
                                "cold novelty review authorized bounded novelty probes; "
                                "complete the probe/rebuttal packet before independent arbitration"
                            ),
                        }
                    )
                    campaign.add_history(
                        updated,
                        "novelty_probe_authorized",
                        decision=review_payload["decision"],
                        claim_class=review_payload["claim_class"],
                        limits=campaign.novelty_probe_limits(updated),
                    )
            else:
                try:
                    updated["research_track"] = campaign.novelty_resolution(updated)
                except campaign.CampaignError as exc:
                    updated.pop("research_track", None)
                    if updated["mission"]["fallback_policy"] == "wait_human":
                        fallback_phase = "novelty_review"
                        updated["control"].update(
                            {
                                "state": "waiting_human",
                                "reason": f"cold novelty review requires a user decision: {exc}",
                            }
                        )
                    else:
                        portfolio = campaign.validate_candidate_portfolio(
                            updated,
                            campaign.artifact_file(updated, "candidate_portfolio"),
                        )
                        has_backup = any(
                            candidate.get("status") == "backup"
                            for candidate in portfolio["candidates"]
                        )
                        fallback_phase = "portfolio" if has_backup else "discovery"
                        updated["phase"] = fallback_phase
                        updated["control"].update(
                            {
                                "state": "needs_agent",
                                "reason": (
                                    f"cold novelty review rejected or reclassified the active candidate: {exc}; "
                                    f"return to {fallback_phase}"
                                ),
                            }
                        )
                    campaign.add_history(
                        updated,
                        "novelty_review_fallback",
                        decision=review_payload.get("decision"),
                        claim_class=review_payload.get("claim_class"),
                        fallback_phase=fallback_phase,
                        reason=str(exc),
                    )
        campaign.add_history(
            updated,
            "novelty_review_turn_finished",
            returncode=returncode,
            review_thread_id=discovered_thread,
            author_thread_id=author_thread_id,
            validated=not failure,
            failure=failure,
        )


def run_novelty_arbiter(
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
        pause_campaign(root, "approved Codex turn budget exhausted before novelty arbitration")
        return
    try:
        audit_path, _, review_path, review = campaign.attested_novelty_review(state)
        if review["decision"] not in campaign.NOVELTY_PROBE_DECISIONS:
            raise campaign.CampaignError("cold review did not authorize conditional novelty arbitration")
        rebuttal_path = campaign.artifact_file(state, "novelty_rebuttal")
        rebuttal = campaign.validate_novelty_rebuttal(state, rebuttal_path)
        audit_sha256 = campaign.sha256_file(audit_path)
        review_sha256 = campaign.sha256_file(review_path)
        rebuttal_sha256 = campaign.sha256_file(rebuttal_path)
    except (campaign.CampaignError, OSError) as exc:
        pause_campaign(root, f"novelty arbiter input validation failed: {exc}")
        return
    author_thread_id = control.get("thread_id")
    review_thread_id = state["artifacts"]["novelty_review"].get("review_thread_id")
    arbitration_requested_at = control.get("novelty_arbitration_requested_at")
    if not author_thread_id or not review_thread_id or author_thread_id == review_thread_id:
        pause_campaign(root, "novelty arbitration requires distinct attested author and reviewer threads")
        return
    try:
        campaign.live_preflight(state)
    except (campaign.CampaignError, OSError) as exc:
        pause_campaign(root, f"novelty arbiter preflight failed: {exc}")
        return
    workspace = campaign.canonical(state["workspace"], strict=True)
    campaign.validate_workspace(workspace)
    try:
        arbiter_workspace_commit = campaign.git_workspace_info(workspace, require_clean=True)["commit"]
    except (campaign.CampaignError, OSError) as exc:
        pause_campaign(root, f"novelty arbiter requires a clean source workspace: {exc}")
        return
    if not shutil.which(codex_bin):
        pause_campaign(root, f"Codex executable is unavailable: {codex_bin}")
        return

    with campaign.locked_state(root) as current:
        if current["status"] != "active" or current["control"]["state"] != "needs_novelty_arbitration":
            return
        campaign.require_approved(current, "allow_auto_agent")
        campaign.require_current_skill(current)
        try:
            current_audit, _, current_review, _ = campaign.attested_novelty_review(current)
            current_rebuttal = campaign.artifact_file(current, "novelty_rebuttal")
            campaign.validate_novelty_rebuttal(current, current_rebuttal)
            inputs_unchanged = (
                campaign.sha256_file(current_audit) == audit_sha256
                and campaign.sha256_file(current_review) == review_sha256
                and campaign.sha256_file(current_rebuttal) == rebuttal_sha256
            )
        except (campaign.CampaignError, OSError) as exc:
            current["status"] = "paused"
            current["control"].update(
                {
                    "state": "paused",
                    "reason": f"novelty arbitration inputs became invalid before launch: {exc}",
                }
            )
            campaign.add_history(current, "controller_novelty_arbitration_input_changed", reason=str(exc))
            return
        if not inputs_unchanged:
            current["status"] = "paused"
            current["control"].update(
                {
                    "state": "paused",
                    "reason": "novelty arbitration inputs changed before the arbiter launch",
                }
            )
            campaign.add_history(current, "controller_novelty_arbitration_input_changed", reason="hash changed")
            return
        previous_arbitration = current["artifacts"].pop("novelty_arbitration", None)
        current["control"].update(
            {
                "state": "novelty_arbiter_running",
                "reason": "controller launched fresh independent novelty arbiter",
            }
        )
        campaign.add_history(
            current,
            "controller_novelty_arbitration_started",
            audit_sha256=audit_sha256,
            review_sha256=review_sha256,
            rebuttal_sha256=rebuttal_sha256,
            author_thread_id=author_thread_id,
            review_thread_id=review_thread_id,
            invalidated_arbitration_sha256=(previous_arbitration or {}).get("sha256"),
        )

    command = novelty_arbiter_codex_command(
        codex_bin,
        workspace,
        root,
        rebuttal,
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
            f"\n[{campaign.utc_now()}] launch novelty arbiter: "
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
            pause_campaign(root, f"failed to launch novelty arbiter: {exc}")
            raise campaign.CampaignError(f"failed to launch novelty arbiter: {exc}") from exc
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
        log.write(f"[{campaign.utc_now()}] novelty-arbitration exit: {returncode}\n")
    finally:
        log.close()

    with campaign.locked_state(root) as updated:
        updated["control"]["agent_turns"] += 1
        updated["control"]["last_agent_at"] = campaign.utc_now()
        failure: str | None = None
        deferred_to_human = (
            updated["control"]["state"] == "waiting_human"
            and "novelty_arbitration" not in updated["artifacts"]
        )
        if returncode != 0:
            failure = f"novelty arbiter exited with status {returncode}; inspect controller.log"
        elif not discovered_thread:
            failure = "novelty arbiter returned no thread ID"
        elif discovered_thread in {author_thread_id, review_thread_id}:
            failure = "novelty arbiter reused an author or reviewer thread"
        else:
            try:
                current_audit, _, current_review, _ = campaign.attested_novelty_review(updated)
                current_rebuttal = campaign.artifact_file(updated, "novelty_rebuttal")
                if (
                    campaign.sha256_file(current_audit) != audit_sha256
                    or campaign.sha256_file(current_review) != review_sha256
                    or campaign.sha256_file(current_rebuttal) != rebuttal_sha256
                ):
                    raise campaign.CampaignError("novelty arbitration inputs changed during arbitration")
                if not deferred_to_human:
                    arbitration_path = campaign.artifact_file(updated, "novelty_arbitration")
                    campaign.validate_novelty_arbitration(updated, arbitration_path)
                    arbitration_record = updated["artifacts"]["novelty_arbitration"]
                    if arbitration_record.get("assurance") != "provisional":
                        raise campaign.CampaignError("novelty arbitration was not registered as provisional")
                    if arbitration_requested_at and campaign.parse_time(
                        arbitration_record["recorded_at"]
                    ) < campaign.parse_time(arbitration_requested_at):
                        raise campaign.CampaignError("novelty arbiter reused an artifact from before this request")
                current_workspace = campaign.git_workspace_info(workspace, require_clean=True)
                if current_workspace["commit"] != arbiter_workspace_commit:
                    raise campaign.CampaignError("novelty arbiter changed the source workspace commit")
            except (campaign.CampaignError, OSError) as exc:
                failure = f"independent novelty arbitration validation failed: {exc}"
        if not failure and updated["control"]["state"] == "novelty_arbiter_running":
            failure = "novelty arbiter exited without the required campaign handoff"
        if not failure and updated["control"]["state"] not in {"needs_agent", "waiting_human", "paused"}:
            failure = f"novelty arbiter used an invalid handoff: {updated['control']['state']}"

        if failure:
            updated["status"] = "paused"
            updated["control"].update({"state": "paused", "reason": failure})
        elif deferred_to_human:
            updated["control"]["novelty_arbitration_thread_id"] = discovered_thread
            campaign.add_history(
                updated,
                "novelty_arbitration_deferred_to_human",
                arbiter_thread_id=discovered_thread,
                reason=updated["control"].get("reason"),
            )
        else:
            arbitration_record = updated["artifacts"]["novelty_arbitration"]
            arbitration_record.update(
                {
                    "cold_arbitration": True,
                    "arbiter_thread_id": discovered_thread,
                    "author_thread_id": author_thread_id,
                    "review_thread_id": review_thread_id,
                    "reviewed_rebuttal_sha256": rebuttal_sha256,
                }
            )
            updated["control"]["novelty_arbitration_thread_id"] = discovered_thread
            try:
                updated["research_track"] = campaign.novelty_resolution(updated)
                updated["phase"] = "novelty_review"
                updated["control"].update(
                    {
                        "state": "needs_agent",
                        "reason": "independent novelty arbitration cleared the candidate for planning",
                    }
                )
                campaign.add_history(
                    updated,
                    "novelty_arbitration_cleared",
                    claim_class=updated["research_track"],
                )
            except campaign.CampaignError as exc:
                updated.pop("research_track", None)
                if updated["mission"]["fallback_policy"] == "wait_human":
                    fallback_phase = "novelty_review"
                    updated["control"].update(
                        {
                            "state": "waiting_human",
                            "reason": f"novelty arbitration requires a user decision: {exc}",
                        }
                    )
                else:
                    portfolio = campaign.validate_candidate_portfolio(
                        updated,
                        campaign.artifact_file(updated, "candidate_portfolio"),
                    )
                    has_backup = any(
                        candidate.get("status") == "backup" for candidate in portfolio["candidates"]
                    )
                    fallback_phase = "portfolio" if has_backup else "discovery"
                    updated["phase"] = fallback_phase
                    updated["control"].update(
                        {
                            "state": "needs_agent",
                            "reason": f"novelty arbitration rejected the candidate: {exc}; return to {fallback_phase}",
                        }
                    )
                campaign.add_history(
                    updated,
                    "novelty_arbitration_fallback",
                    fallback_phase=fallback_phase,
                    reason=str(exc),
                )
        campaign.add_history(
            updated,
            "novelty_arbitration_turn_finished",
            returncode=returncode,
            arbiter_thread_id=discovered_thread,
            author_thread_id=author_thread_id,
            review_thread_id=review_thread_id,
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
    if control == "needs_novelty_arbitration":
        return "launch one fresh independent novelty-arbitration thread"
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
    if control in {"agent_running", "novelty_reviewer_running", "novelty_arbiter_running"}:
        stale_reasons = {
            "agent_running": "stale agent_running state; inspect the control host before resuming to avoid duplicate agents",
            "novelty_reviewer_running": "stale novelty_reviewer_running state; inspect the control host before resuming to avoid duplicate reviewers",
            "novelty_arbiter_running": "stale novelty_arbiter_running state; inspect the control host before resuming to avoid duplicate arbiters",
        }
        duplicate_reason = stale_reasons[control]
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
    elif control == "needs_novelty_arbitration":
        run_novelty_arbiter(root, codex_bin, model, reasoning_effort)
    return campaign.load_state(root)["status"] == "active"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--model", help="explicit Codex model for every author, reviewer, and arbiter turn")
    parser.add_argument(
        "--reasoning-effort",
        choices=REASONING_EFFORTS,
        help="explicit Codex reasoning effort for every author, reviewer, and arbiter turn",
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
