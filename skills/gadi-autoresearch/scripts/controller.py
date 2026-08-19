#!/usr/bin/env python3
"""Event-driven Codex controller for an approved Gadi autoresearch campaign."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

sys.dont_write_bytecode = True
import campaign


MAX_LOG_BYTES = 5 * 1024 * 1024
NOVELTY_REFERENCE = Path(__file__).resolve().parents[1] / "references" / "novelty-audit.md"
ADAPTER_REFERENCE = Path(__file__).resolve().parents[1] / "references" / "adapter-system.md"
WORKFLOW_REFERENCE = Path(__file__).resolve().parents[1] / "references" / "research-workflow.md"
HARDWARE_REFERENCE = Path(__file__).resolve().parents[1] / "references" / "hardware-routing.md"
LAB_REFERENCE = Path(__file__).resolve().parents[1] / "references" / "lab-operating-model.md"
REASONING_EFFORTS = ("low", "medium", "high", "xhigh", "max", "ultra")
RETRY_DELAYS_SECONDS = (60, 300, 900, 3600)
RUNNING_STATES = {
    "agent_running": ("author", "needs_agent"),
    "novelty_reviewer_running": ("novelty_reviewer", "needs_novelty_review"),
    "novelty_arbiter_running": ("novelty_arbiter", "needs_novelty_arbitration"),
    "failure_reviewer_running": ("failure_reviewer", "needs_failure_review"),
    "opportunity_scout_running": ("opportunity_scout", "needs_opportunity_scouts"),
    "evidence_analyst_running": ("evidence_analyst", "needs_evidence_analysis"),
}


@dataclass(frozen=True)
class CodexInvocation:
    command: list[str]
    prompt: str


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


def recovery_defaults() -> dict[str, Any]:
    return {
        "category": None,
        "attempts": 0,
        "role": None,
        "target_state": None,
        "last_failure": None,
        "thread_rotations": 0,
    }


def ensure_control_schema(root: Path) -> None:
    with campaign.locked_state(root) as state:
        state["control"].setdefault("lease", None)
        state["control"].setdefault("recovery", recovery_defaults())
        state["control"].setdefault("failure_review_thread_id", None)
        state["control"].setdefault("failure_review_requested_at", None)
        state["control"].setdefault("opportunity_scout_thread_ids", {})
        state["control"].setdefault("analysis_thread_id", None)
        state["control"].setdefault("analysis_experiment_id", None)
        state.setdefault("learning", None)
        campaign.ensure_research_os(state)


def clear_recovery(state: dict[str, Any]) -> None:
    rotations = int(state["control"].get("recovery", {}).get("thread_rotations", 0))
    state["control"]["recovery"] = {**recovery_defaults(), "thread_rotations": rotations}
    state["control"]["lease"] = None


def schedule_recovery(
    root: Path,
    *,
    category: str,
    role: str,
    target_state: str,
    reason: str,
) -> None:
    with campaign.locked_state(root) as state:
        control = state["control"]
        recovery = control.setdefault("recovery", recovery_defaults())
        same_failure = recovery.get("category") == category and recovery.get("role") == role
        attempts = int(recovery.get("attempts", 0)) + 1 if same_failure else 1
        rotations = int(recovery.get("thread_rotations", 0))
        if role == "author" and attempts == len(RETRY_DELAYS_SECONDS) + 1:
            control["thread_id"] = None
            rotations += 1
        delay = RETRY_DELAYS_SECONDS[min(attempts - 1, len(RETRY_DELAYS_SECONDS) - 1)]
        wake = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=delay)
        deadline = campaign.parse_time(state["approval"]["deadline"])
        if wake > deadline:
            wake = deadline
        control["recovery"] = {
            "category": category,
            "attempts": attempts,
            "role": role,
            "target_state": target_state,
            "last_failure": reason,
            "thread_rotations": rotations,
        }
        control["lease"] = None
        control.update(
            {
                "state": "waiting_time",
                "reason": (
                    f"automatic recovery {attempts} for {role}/{category}; "
                    f"retry at {wake.isoformat().replace('+00:00', 'Z')}: {reason}"
                ),
                "wake_at": wake.isoformat().replace("+00:00", "Z"),
            }
        )
        campaign.add_history(
            state,
            "controller_recovery_scheduled",
            category=category,
            role=role,
            target_state=target_state,
            attempt=attempts,
            wake_at=control["wake_at"],
            reason=reason,
            thread_rotated=role == "author" and attempts == len(RETRY_DELAYS_SECONDS) + 1,
        )


def record_lease(root: Path, role: str, target_state: str, pid: int | None) -> None:
    with campaign.locked_state(root) as state:
        state["control"]["lease"] = {
            "role": role,
            "target_state": target_state,
            "pid": pid,
            "host": socket.gethostname(),
            "started_at": campaign.utc_now(),
        }


def lease_process_alive(lease: dict[str, Any] | None) -> bool:
    if not lease or lease.get("host") != socket.gethostname():
        return False
    try:
        pid = int(lease.get("pid"))
    except (TypeError, ValueError):
        return False
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
        command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\x00", b" ")
    except (OSError, ValueError):
        return False
    return b"codex" in command


def scientific_fallback(state: dict[str, Any], reason: str) -> str:
    if state["mission"].get("fallback_policy") == "wait_human":
        state["control"].update(
            {
                "state": "waiting_human",
                "reason": f"immutable mission requests human review after scientific fallback: {reason}",
                "wake_at": None,
            }
        )
        return "waiting_human"
    try:
        candidate_id = campaign.pivot_to_backup(state, reason=reason)
    except (campaign.CampaignError, OSError) as exc:
        candidate_id = None
        reason = f"{reason}; backup promotion was unavailable: {exc}"
    if candidate_id:
        return "portfolio"
    invalidated = []
    for name in (
        "candidate_portfolio",
        "idea_report",
        "novelty_audit",
        "novelty_review",
        "novelty_rebuttal",
        "novelty_arbitration",
        "research_contract",
        "experiment_plan",
        "experiment_ledger",
        "results",
        "experiment_audit",
        "claim_audit",
        "narrative_report",
        "paper_source",
        "paper_pdf",
        "citation_audit",
        "final_report",
        "human_evaluation",
    ):
        if state["artifacts"].pop(name, None) is not None:
            invalidated.append(name)
    state.pop("research_track", None)
    if campaign.learning_enabled(state):
        state["learning"].update(
            {
                "portfolio_refresh_required": True,
                "claim_freeze": None,
                "legacy_novelty_adopted": False,
            }
        )
    state["phase"] = "discovery"
    state["control"].update(
        {
            "state": "needs_agent",
            "reason": f"all ranked backups are exhausted; regenerate the portfolio: {reason}",
            "wake_at": None,
        }
    )
    campaign.add_history(
        state,
        "scientific_fallback_to_discovery",
        reason=reason,
        invalidated_artifacts=invalidated,
    )
    return "discovery"


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
        recovery = state["control"].get("recovery") or {}
        target_state = recovery.get("target_state") or "needs_agent"
        set_control(
            root,
            state=target_state,
            reason=f"scheduled wake reached for {target_state}: {wake_at}",
            wake_at=None,
        )
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
        with campaign.locked_state(root) as state:
            recovery = state["control"].get("recovery") or {}
            if recovery.get("category") == "pbs_refresh":
                clear_recovery(state)
        return
    if "once per 600 seconds" in result.stderr:
        return
    schedule_recovery(
        root,
        category="pbs_refresh",
        role="supervisor",
        target_state="waiting_pbs",
        reason=f"PBS refresh failed: {result.stderr.strip()}",
    )


def maybe_repack_workspace(root: Path, state: dict[str, Any]) -> None:
    if any(
        attempt.get("status") in campaign.JOB_ACTIVE
        for experiment in state["experiments"].values()
        for attempt in experiment.get("attempts", [])
    ):
        return
    workspace = campaign.canonical(state["workspace"], strict=True)
    try:
        info = campaign.git_workspace_info(workspace, require_clean=True)
        count = subprocess.run(
            ["git", "-C", str(workspace), "count-objects", "-v"],
            check=False,
            capture_output=True,
            text=True,
        )
        loose = next(
            (
                int(line.split(":", 1)[1].strip())
                for line in count.stdout.splitlines()
                if line.startswith("count:")
            ),
            0,
        )
        if count.returncode != 0 or loose < 256:
            return
        repack = subprocess.run(
            ["git", "-C", str(workspace), "repack", "-ad", "-q"],
            check=False,
            capture_output=True,
            text=True,
        )
        if repack.returncode != 0:
            return
        subprocess.run(
            ["git", "-C", str(workspace), "prune-packed", "-q"],
            check=False,
            capture_output=True,
            text=True,
        )
        with campaign.locked_state(root) as updated:
            campaign.add_history(
                updated,
                "workspace_git_repacked",
                commit=info["commit"],
                loose_objects_before=loose,
            )
    except (campaign.CampaignError, OSError, ValueError):
        return


def compact_research_director_packet(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    """Return bounded launch context; campaign.json remains the scientific source of truth."""
    lab = state.get("research_os") or {}
    portfolio = lab.get("portfolio") or {}
    concept_freeze = portfolio.get("concept_freeze") or {}
    protocol = lab.get("protocol") or {}
    infrastructure = lab.get("infrastructure") or {}
    cells = infrastructure.get("cells") or {}
    scouting = lab.get("scouting") or {}
    reports = scouting.get("reports") or {}
    decisions = lab.get("director_decisions") or []
    latest_decision = decisions[-1] if decisions else None
    health = campaign.research_health(state)
    core_signal_ids = health.get("core_signal_finding_ids") or []
    alerts = health.get("alerts") or []
    active_hypothesis_id = concept_freeze.get("hypothesis_id")
    active_cell_ids = sorted(
        cell_id
        for cell_id, cell in cells.items()
        if isinstance(cell, dict) and cell.get("hypothesis_id") == active_hypothesis_id
    )
    maturity_counts: dict[str, int] = {}
    for maturity in (portfolio.get("branch_maturity") or {}).values():
        maturity_counts[str(maturity)] = maturity_counts.get(str(maturity), 0) + 1
    open_blocker_ids = [
        blocker.get("id")
        for blocker in protocol.get("hard_blockers") or []
        if isinstance(blocker, dict) and blocker.get("status") == "open"
    ]
    latest_decision_index = None
    if isinstance(latest_decision, dict):
        latest_decision_index = {
            key: latest_decision.get(key)
            for key in (
                "decision_id",
                "hypothesis_id",
                "decision",
                "maturity_before",
                "maturity_after",
                "core_signal",
                "next_budget",
                "recorded_at",
            )
        }
        latest_decision_index["sha256"] = campaign.sha256_json(latest_decision)
    compact_health = {
        key: health.get(key)
        for key in (
            "mode",
            "elapsed_hours",
            "scientific_cells",
            "core_mechanism_cells",
            "terminal_attempts",
            "interpretations",
            "independent_analyses",
            "scientific_findings",
            "protocol_diagnostics",
            "technical_invalid_fraction",
            "independent_reviews",
            "time_to_first_core_signal_hours",
            "active_decision_budget",
        )
    }
    compact_health.update(
        {
            "core_signal_count": len(core_signal_ids),
            "recent_core_signal_finding_ids": core_signal_ids[-8:],
            "alert_count": len(alerts),
            "alerts": alerts,
        }
    )
    return {
        "authoritative_state": str(root / "campaign.json"),
        "authoritative_research_os_sha256": campaign.sha256_json(lab),
        "note": (
            "This launch packet is intentionally bounded. Read campaign.json for full scout "
            "reports, protocol history, preliminary novelty, cells, and Director decisions."
        ),
        "research_os_index": {
            "schema_version": lab.get("schema_version"),
            "mode": lab.get("mode"),
            "updated_at": lab.get("updated_at"),
            "authority": lab.get("authority"),
            "portfolio": {
                "active_hypothesis_id": active_hypothesis_id,
                "active_hypothesis_maturity": (portfolio.get("branch_maturity") or {}).get(
                    active_hypothesis_id
                ),
                "branch_count": len(portfolio.get("branch_maturity") or {}),
                "maturity_counts": maturity_counts,
                "concept_freeze": {
                    "frozen_at": concept_freeze.get("frozen_at"),
                    "graph_sha256": concept_freeze.get("graph_sha256"),
                    "hypothesis_id": active_hypothesis_id,
                    "preliminary_novelty_sha256": campaign.sha256_json(
                        concept_freeze.get("preliminary_novelty")
                    )
                    if concept_freeze.get("preliminary_novelty") is not None
                    else None,
                },
                "last_director_decision_id": portfolio.get("last_director_decision_id"),
                "director_decision_required": portfolio.get("director_decision_required") is not None,
                "director_decision_required_sha256": campaign.sha256_json(
                    portfolio.get("director_decision_required")
                )
                if portfolio.get("director_decision_required") is not None
                else None,
                "active_budget": portfolio.get("active_budget"),
            },
            "protocol": {
                "revision": protocol.get("revision"),
                "protocol_id": protocol.get("protocol_id"),
                "status": protocol.get("status"),
                "decision": protocol.get("decision"),
                "claim_ceiling": protocol.get("claim_ceiling"),
                "updated_at": protocol.get("updated_at"),
                "scope_count": len(protocol.get("scope") or []),
                "warning_count": len(protocol.get("warnings") or []),
                "open_hard_blocker_ids": open_blocker_ids,
                "evidence_ids": protocol.get("evidence_ids") or [],
                "current_sha256": campaign.sha256_json(
                    {key: value for key, value in protocol.items() if key != "history"}
                ),
                "history_count": len(protocol.get("history") or []),
            },
            "infrastructure": {
                "cache_policy": infrastructure.get("cache_policy"),
                "cell_count": len(cells),
                "active_hypothesis_cell_ids": active_cell_ids,
                "cells_sha256": campaign.sha256_json(cells),
            },
            "scouting": {
                "round": scouting.get("round"),
                "requested_at": scouting.get("requested_at"),
                "active_role": scouting.get("active_role"),
                "report_roles": sorted(reports),
                "report_sha256": {
                    role: campaign.sha256_json(report) for role, report in sorted(reports.items())
                },
            },
            "director_decision_count": len(decisions),
            "latest_director_decision": latest_decision_index,
            "review_chain": lab.get("review_chain"),
            "signal": {
                "first_core_signal_at": (lab.get("signal") or {}).get("first_core_signal_at"),
                "core_signal_count": len(
                    (lab.get("signal") or {}).get("core_signal_finding_ids") or []
                ),
                "recent_core_signal_finding_ids": (
                    (lab.get("signal") or {}).get("core_signal_finding_ids") or []
                )[-8:],
            },
            "circuit_breakers": lab.get("circuit_breakers"),
        },
        "health": compact_health,
    }


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
    research_packet = json.dumps(
        compact_research_director_packet(root, state),
        indent=2,
        sort_keys=True,
    )
    research_mode = (state.get("research_os") or {}).get("mode", "balanced")
    mode_guidance = {
        "signal_first": (
            "Optimize time-to-first-core-signal: keep scouts minimal, kill quickly, and do not "
            "start paper-facing audits before one branch earns pilot maturity."
        ),
        "balanced": (
            "Balance opportunity search with rigor: keep one primary branch and bounded backups, "
            "then scale evidence only after each maturity promotion."
        ),
        "submission": (
            "Consolidate an existing claim: prioritize frozen-protocol replication, robustness, "
            "claim/citation audits, and paper completion; open a new territory only if the claim fails."
        ),
    }[research_mode]
    return f"""Use $gadi-autoresearch and resume the approved campaign at {root}.
Act as the Research Director and sole workspace writer. Read MISSION.json, campaign.json, {LAB_REFERENCE}, {ADAPTER_REFERENCE}, {WORKFLOW_REFERENCE}, and the research workspace directly. The mission is immutable and defines which final contribution classes are acceptable. Continue the evidence-led discovery-to-paper workflow within the recorded project, SU, GPU, walltime, deadline, and persistent-file envelope. Use campaign.py for every state change and Gadi action. Never call raw qsub/qdel, never compute on the login or persistent-session host, and never write workload data under .codex.

Current adapter packet:
{reference_packet}

Current research-director packet:
{research_packet}

Current research mode `{research_mode}`: {mode_guidance}

Treat the campaign as a portfolio, not a linear review pipeline. The operative loop is question -> cheapest discriminating test -> raw result -> blind independent analysis -> director decision. Keep scientific hypotheses, data/evaluation protocol revisions, and infrastructure repairs in separate lanes. Every experiment must answer one decision-changing question. Optimize time-to-kill during seed/scout, increase rigor only at pilot/claim/paper, and obey every research-health alert without pausing merely because the science is uncertain.

During territory and discovery, request `needs_opportunity_scouts` once per materially new territory. The controller will launch blind literature, systems, and cross-domain scouts in fresh contexts; do not imitate their independence in your own thread. Synthesize their attested reports into one compact DISCOVERY_REPORT.md and CANDIDATE_PORTFOLIO.json. Resolve an explicit dependency-complete route with campaign.py route-set before portfolio. Each candidate needs an observation, causal hypothesis, mechanism, predicted signature, falsifier, cheap distinguishing test, nearest-work delta, and estimated SU/job/file cost. Do not promote a branded idea without an observed or formally defined problem.

After recording the portfolio, initialize the two-file hypothesis workflow with campaign.py learning-init. Read the compact graph, ledger, and research_os decision packet on every turn. Perform a preliminary nearest-prior check, then use concept-freeze; this authorizes real-path scout work without pretending the paper claim is fixed. Register scout/pilot experiments with a stable `--cell-id`, explicit decision question and support/falsify decisions, maturity, protocol revision, compatible queues, and `--core-mechanism-test` when it directly exercises the proposed mechanism. Technical repairs remain attempts in the same scientific cell. Do not use claim-freeze or exhaustive novelty review until a director decision has promoted an empirically supported branch to claim maturity. Never relabel exploratory evidence as confirmation after seeing it.

After every completed evidence-bearing scientific batch, the controller launches a fresh analyst who sees raw output before your interpretation. Failed, cancelled, diagnostic, and interactive attempts return directly to you for infrastructure interpretation and do not spend a blind-analysis turn. Read each required attested analysis, then record exactly one learning interpretation with explicit `lane`, `materiality`, and `decision_scope`. Technical invalidity uses lane=infrastructure and repair. Data/evaluation changes use lane=protocol with protocol_refine or narrow_scope, then protocol-record; they do not mutate the scientific graph and do not summon a mechanism critic. Nonmaterial qualification plus continue does not require review. Only material scientific falsification or mutation requests use needs_failure_review. The critic classifies severity and may request at most one bounded test; after two reviews in one chain, the controller requires your director-decision rather than another critic. Record a bounded director-decision before refine/branch/pivot/park/kill or promotion. Its next_budget is enforced for jobs, SU, and Director turns. A generating finding remains evidence about its parent and never confirms its child.

Use seed -> scout -> pilot -> claim -> paper maturity. Promote at most one level per director decision and attach a jobs/SU/turns/protocol-diagnostic budget. A scout needs a minimal integrated real-model witness. A pilot needs a competitive baseline and discriminating ablation. After promotion to claim, freeze the confirmatory protocol, call claim-freeze to bind the scientific object, refresh exhaustive novelty against that frozen object, obtain the cold review, and only then run confirmatory evidence. Data uncertainty blocks only affected consumed endpoints and claims: actual leakage, invalid metrics, safety, and authorization are hard blockers; untested excluded relations are warnings or scope ceilings. If a relation has no positive real evidence, declare it out of scope instead of manufacturing an endless gate.

At claim promotion, read {NOVELTY_REFERENCE} and satisfy the exhaustive machine-enforced novelty gate. Bind the audit to the mission, route, candidate portfolio, idea report, and frozen scientific claim. Describe the mechanism without its coined name, search exact/synonym/task/adjacent/combination/code/citation-neighbor routes, compare checked primary sources, and request a fresh reviewer. Preliminary novelty is triage only; exhaustive novelty is required before confirmatory work and refreshed before submission.

The cold reviewer has three current outcomes. clear_to_plan opens planning. exact_prior_reject requires a checked functionally equivalent prior and sends the candidate back to discovery/portfolio. conditional_probe means no exact prior was found but the paper-facing delta depends on an empirical interaction. In that case, remain in novelty_review and run only stage=novelty_probe experiments bound to the review. Current hard caps are:
{novelty_probe_packet}
After one to three completed probes, write the exact bound NOVELTY_REBUTTAL.json schema, register it as provisional, and hand off with state needs_novelty_arbitration. Never write NOVELTY_ARBITRATION.json yourself. A fresh third Codex thread decides clear_to_plan or exact_prior_reject. No pilot, main, ablation, paper-facing baseline, or full implementation work is allowed until final clearance. Preserve the observation when rejected. Use campaign.py candidate-pivot to atomically promote a ranked backup; do not hand-edit several hash-bound artifacts. If every backup is exhausted, return to discovery, generate and register a new portfolio from the accumulated negative evidence, then use campaign.py learning-reseed before freezing another claim. Never silently downgrade a requested method, architecture, objective, representation, system, data, evaluation, empirical, or theory contribution into an application, reproduction, or diagnostic paper.

Before final novelty clearance, candidate-independent environment/data/model setup is permitted only through campaign.py external-submit within its discovery-infrastructure recovery envelope. A failed same-stage attempt may be retried under a new immutable experiment ID only after changing the PBS script; the CLI records retry lineage and still charges every attempt against job/SU budgets. Environments must be assembled in PBS jobfs, smoke-tested for /bin/sh, Python, framework imports, and container execution, then published as one immutable .sqsh under /g/data/wa66/Xiangyu/enviroment_cache. Datasets must be downloaded/expanded in PBS jobfs and published as packed objects under /g/data/wa66/Xiangyu/Data. A public pretrained model may be acquired only when approval.allow_model_publish=true: use stage=model on copyq, pin an immutable source revision and license, download and validate in PBS jobfs, invoke the audited packer, and publish exactly one .tar.zst directly under /g/data/wa66/Xiangyu/Data/models. Register that archive as a data input, and expand it only into each compute job's PBS jobfs. Never persist expanded dependency trees, dataset trees, model repositories, model shards, or Hugging Face/package caches.

Before every GPU registration or queue-driven replacement, read {HARDWARE_REFERENCE}. Classify the evidence, derive the compatible GPU set from measured memory, precision, architecture, topology, and deployment requirements, then use one rate-compliant queue observation to choose the shortest credible time to evidence. Portable BF16 diagnostics and pilots that fit A100 should normally use dgxa100; H200 is reserved for measured capacity need, Hopper-specific behavior, or matched final H200 evidence. Record the compatibility set, rejected queues, observation time, selected queue, matched-comparison scope, and one fallback in the campaign policy or bound experiment config. Performance comparisons must be within one GPU family. If a portable job exceeds its declared queue threshold and a compatible route has materially lower pressure, reroute at most once per scientific cell in six hours: only cancel a queued or held attempt, only through campaign.py when allow_auto_cancel is granted, wait for its recorded terminal state, and use a new immutable experiment ID/config/result directory. Never race duplicate cells, oscillate between queues, or cancel a running job merely for turnaround.

If a candidate requires unavailable human evaluation, block only that candidate: generate a packed blinded study bundle when the mission permits it, then promote an objective-evidence backup or return to discovery. Hand off to waiting_human only when the immutable mission explicitly requires human evidence and no acceptable autonomous branch remains. Never invent ratings, listeners, consent, demographics, or human-study results. Keep all expanded audio/media samples in PBS jobfs and publish only bounded archives, manifests, aggregate metrics, and a small declared demo subset.

Recover technical failures autonomously, but never use repeated CPU or GPU batch submissions as an edit-run loop. Before an unproven model/CUDA/parser path, prefer one bounded interactive diagnostic. After one technical batch failure in the same cell, register a same-queue interactive diagnostic with `--debug-for FAILED_ID` and the failed batch's same `--cell-id`; reuse that allocation across clean source commits until the smallest real witness succeeds. A nonzero `interactive-run` returns to the PBS shell. Keep environments, packed datasets, and packed models cached persistently only at their approved roots; stage them into the same PBS jobfs allocation once. Release the allocation only for literature, acquisition, redesign, or external waiting. Use stable source filenames across repairs because Git already preserves versions; do not create v1/v2/v3 source copies. Keep the canonical workspace clean and let the controller repack loose Git objects at safe idle points.

For queue routing, select the smallest compatible resource and normally prefer one V100/A100 for portable scout/debug work; use H200 only for measured capacity, Hopper-specific behavior, or matched final evidence. Bundle sweeps. Never sit in an agent turn waiting for PBS: submit, hand off, and let the event-driven controller wake later. Before paper completion, build a claim graph linking every claim to evidence, code commit, protocol revision, primary literature, assumptions, and limitations; independently reproduce the central result, then write and compile LaTeX. Before this turn exits, call campaign.py handoff with the correct state and concrete reason. A missing handoff is automatically retried."""


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

After fixing your independent source set and preliminary judgment, read the mission, route, candidate portfolio, and author artifacts, test the author's strongest rebuttal, and inspect additional cited sources where needed. Classify the actual contribution even when it is outside the mission; the controller will force the author back to discovery rather than accepting a silent downgrade. Write the exact schema from {NOVELTY_REFERENCE} to {root}/NOVELTY_REVIEW.json. Bind it to the recorded audit hash, include at least three independently checked primary sources and a comparison for every primitive, then register it with assurance provisional using campaign.py. Hand off to needs_agent with a concrete verdict. If source access remains insufficient after bounded retries, do not guess and do not request a human novelty judgment: hand off to needs_agent with a reason beginning `inconclusive novelty review:` so the controller can promote a backup or return to discovery. The controller will reject the review if this thread matches the author thread, the audit changed, the source workspace changes, the schema is incomplete, an old review is reused, or the required handoff is absent. A fresh same-family review is process-independent but remains scientifically provisional."""


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

Write the exact NOVELTY_ARBITRATION.json schema from {NOVELTY_REFERENCE} to {root}/NOVELTY_ARBITRATION.json and register it as provisional with campaign.py. The only decisions are clear_to_plan and exact_prior_reject. clear_to_plan requires a mission-accepted primary contribution, no blocking issues, and no exact prior. exact_prior_reject requires a checked primary source that is functionally equivalent, with exact_prior.functionally_equivalent=true and concrete equivalence evidence. If the evidence is weak or the probe is invalid but no exact prior exists, do not invent a hard rejection and do not request a human novelty judgment: hand off to needs_agent with a reason beginning `inconclusive novelty arbitration:` so the controller can promote a backup or return to discovery. Hand off to needs_agent after recording a valid arbitration. The controller rejects reused threads, changed inputs, workspace changes, incomplete schemas, and missing handoffs."""


def failure_reviewer_prompt(
    root: Path,
    finding_id: str,
    hypothesis: dict[str, Any],
    experiment: dict[str, Any],
) -> str:
    blind_packet = json.dumps(
        {
            "finding_id": finding_id,
            "hypothesis": {
                "id": hypothesis["id"],
                "observation": hypothesis["observation"],
                "causal_hypothesis": hypothesis["causal_hypothesis"],
                "mechanism": hypothesis["mechanism"],
                "predictions": hypothesis["predictions"],
                "falsifiers": hypothesis["falsifiers"],
                "assumptions": hypothesis["assumptions"],
            },
            "experiment": {
                "id": experiment["id"],
                "stage": experiment["stage"],
                "evidence_role": experiment.get("evidence_role"),
                "command": experiment["command"],
                "source_commit": experiment.get("source_commit"),
                "success_file": experiment.get("success_file"),
                "attempts": experiment.get("attempts", []),
            },
        },
        indent=2,
        sort_keys=True,
    )
    maturity = experiment.get("maturity") or "scout"
    review_kind = "integrity" if maturity in {"claim", "paper"} else "mechanism"
    return f"""Use $gadi-autoresearch as the fresh {review_kind} critic for {root}.
You are not the author. Do not edit the source workspace, mutate hypotheses, change phases or approval, register experiments, submit PBS work, or browse for a new idea. Read campaign.json and {WORKFLOW_REFERENCE}. First inspect the registered experiment, raw compact result or success marker, attempt metadata, and any bounded logs without reading the author's interpretation line in LEARNING_LEDGER.jsonl. Form an independent validity and causal assessment from this blind packet:

{blind_packet}

Only after fixing that preliminary assessment, read the interpretation for finding {finding_id}. Decide accept, revise, or reject. Set review_kind={review_kind}. Classify the objection as hard_invalidating, claim_scope, future_work, or nonblocking. State the affected claim, the decision the objection changes, and an estimated cost in jobs, hours, SU, and persistent entries. You may require at most one bounded next test; it must distinguish a named alternative explanation and change a concrete decision. Do not apply submission-grade requirements to scout evidence. Authorize scientific mutation only when the result is valid and material. Protocol scope changes are not child hypotheses. A technical failure authorizes repair without a scientific update, and generating evidence never confirms its child.

Write one temporary JSON object matching the failure_review schema in {WORKFLOW_REFERENCE}, call campaign.py learning-review --file on it, remove the temporary file, and hand off to needs_agent with a concrete assessment. The controller will reject a reused author thread, changed source workspace, changed interpretation, incomplete schema, or missing handoff."""


def opportunity_scout_prompt(root: Path, state: dict[str, Any], role: str, round_number: int) -> str:
    packet = json.dumps(
        {
            "round": round_number,
            "role": role,
            "mission": state["mission"],
            "route": state.get("route"),
            "workspace": state["workspace"],
        },
        indent=2,
        sort_keys=True,
    )
    role_focus = {
        "literature": "Search primary literature and official code for open contradictions, missing comparisons, and mechanism gaps.",
        "systems": "Inspect the research workspace read-only and identify measured or measurable model/runtime/data bottlenecks.",
        "cross_domain": "Search adjacent fields for mechanisms with a non-obvious, falsifiable transfer to this mission.",
    }[role]
    return f"""Use $gadi-autoresearch as a blind {role} opportunity scout for {root}.
This is a fresh context. You are not the Research Director, cannot edit the workspace, cannot read other scout reports, and cannot register or submit experiments. {role_focus}

Assignment packet:
{packet}

Read {LAB_REFERENCE} and only the mission, selected adapter references, primary sources, and read-only workspace material needed for your role. Produce 1-5 causal opportunities, not branded paper pitches. Each needs an observation, a causal opportunity, the cheapest differentiating test, nearest-work delta, closest-prior queries, and estimated jobs/SU/hours. Write one temporary JSON object matching the opportunity_scout schema in {LAB_REFERENCE}, call campaign.py scout-record --file on it, remove the temporary file, and hand off to needs_opportunity_scouts. Do not read campaign.json after launch because it can contain earlier blind reports."""


def evidence_analyst_prompt(
    root: Path,
    experiment: dict[str, Any],
    hypothesis: dict[str, Any],
) -> str:
    packet = json.dumps(
        {
            "experiment": {
                "id": experiment["id"],
                "scientific_cell_id": experiment.get("scientific_cell_id"),
                "stage": experiment["stage"],
                "maturity": experiment.get("maturity"),
                "evidence_role": experiment.get("evidence_role"),
                "decision_question": experiment.get("decision_question"),
                "decision_if_supports": experiment.get("decision_if_supports"),
                "decision_if_falsifies": experiment.get("decision_if_falsifies"),
                "protocol_revision": experiment.get("protocol_revision"),
                "command": experiment["command"],
                "success_file": experiment.get("success_file"),
                "attempts": experiment.get("attempts", []),
            },
            "hypothesis": {
                "id": hypothesis["id"],
                "causal_hypothesis": hypothesis["causal_hypothesis"],
                "predictions": hypothesis["predictions"],
                "falsifiers": hypothesis["falsifiers"],
                "assumptions": hypothesis["assumptions"],
            },
        },
        indent=2,
        sort_keys=True,
    )
    return f"""Use $gadi-autoresearch as the blind raw-result analyst for {root}.
You are a fresh independent context. Do not edit the workspace, browse for a new idea, mutate state outside analysis-record, or read LEARNING_LEDGER.jsonl, author narratives, reviewer reports, or director decisions before fixing your assessment.

Blind evidence packet:
{packet}

Inspect the registered raw compact output/success marker and bounded PBS attempt metadata. Decide validity, likely outcome, recommended scientific/protocol/infrastructure lane, causal assessment, alternative explanations, threats, and what decision the result can actually change. Respect the evidence maturity: a scout can reveal a signal without confirming a paper claim. Write one temporary JSON object matching the independent_analysis schema in {LAB_REFERENCE}, call campaign.py analysis-record --file, remove the temporary file, and hand off to needs_agent. Do not prescribe an unlimited audit chain."""


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


def unattended_exec_prefix(
    codex_bin: str,
    model: str | None,
    reasoning_effort: str | None,
) -> list[str]:
    return [
        *codex_prefix(codex_bin, model, reasoning_effort),
        "exec",
        "--sandbox",
        "danger-full-access",
        "--config",
        'approval_policy="never"',
    ]


def codex_command(
    codex_bin: str,
    workspace: Path,
    state: dict[str, Any],
    root: Path,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> CodexInvocation:
    thread_id = state["control"].get("thread_id")
    prompt = agent_prompt(root, state)
    common = [
        *unattended_exec_prefix(codex_bin, model, reasoning_effort),
        "--add-dir",
        str(root),
    ]
    if thread_id:
        return CodexInvocation([*common, "resume", "--json", thread_id, "-"], prompt)
    return CodexInvocation([*common, "--json", "-C", str(workspace), "-"], prompt)


def novelty_codex_command(
    codex_bin: str,
    workspace: Path,
    root: Path,
    audit: dict[str, Any],
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> CodexInvocation:
    common = [
        *unattended_exec_prefix(codex_bin, model, reasoning_effort),
        "--add-dir",
        str(root),
    ]
    return CodexInvocation(
        [*common, "--json", "-C", str(workspace), "-"],
        novelty_reviewer_prompt(root, audit),
    )


def novelty_arbiter_codex_command(
    codex_bin: str,
    workspace: Path,
    root: Path,
    rebuttal: dict[str, Any],
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> CodexInvocation:
    common = [
        *unattended_exec_prefix(codex_bin, model, reasoning_effort),
        "--add-dir",
        str(root),
    ]
    return CodexInvocation(
        [*common, "--json", "-C", str(workspace), "-"],
        novelty_arbiter_prompt(root, rebuttal),
    )


def failure_reviewer_codex_command(
    codex_bin: str,
    workspace: Path,
    root: Path,
    finding_id: str,
    hypothesis: dict[str, Any],
    experiment: dict[str, Any],
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> CodexInvocation:
    common = [
        *unattended_exec_prefix(codex_bin, model, reasoning_effort),
        "--add-dir",
        str(root),
    ]
    return CodexInvocation(
        [*common, "--json", "-C", str(workspace), "-"],
        failure_reviewer_prompt(root, finding_id, hypothesis, experiment),
    )


def opportunity_scout_codex_command(
    codex_bin: str,
    workspace: Path,
    root: Path,
    state: dict[str, Any],
    role: str,
    round_number: int,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> CodexInvocation:
    return CodexInvocation(
        [
            *unattended_exec_prefix(codex_bin, model, reasoning_effort),
            "--add-dir",
            str(root),
            "--json",
            "-C",
            str(workspace),
            "-",
        ],
        opportunity_scout_prompt(root, state, role, round_number),
    )


def evidence_analyst_codex_command(
    codex_bin: str,
    workspace: Path,
    root: Path,
    experiment: dict[str, Any],
    hypothesis: dict[str, Any],
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> CodexInvocation:
    return CodexInvocation(
        [
            *unattended_exec_prefix(codex_bin, model, reasoning_effort),
            "--add-dir",
            str(root),
            "--json",
            "-C",
            str(workspace),
            "-",
        ],
        evidence_analyst_prompt(root, experiment, hypothesis),
    )


def start_codex_process(invocation: CodexInvocation, *, workspace: Path) -> subprocess.Popen[str]:
    """Launch Codex with its prompt on stdin, outside the kernel argv size limits."""
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", dir="/tmp") as prompt_stream:
        prompt_stream.write(invocation.prompt)
        prompt_stream.seek(0)
        return subprocess.Popen(
            invocation.command,
            cwd=workspace,
            stdin=prompt_stream,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )


def execute_fresh_codex(
    invocation: CodexInvocation,
    *,
    workspace: Path,
    root: Path,
    role: str,
    target_state: str,
    model: str | None,
    reasoning_effort: str | None,
) -> tuple[int, str | None]:
    log_path = root / "controller.log"
    rotate_log(log_path)
    discovered_thread = None
    returncode = 1
    log = log_path.open("a", encoding="utf-8")
    try:
        log.write(
            f"\n[{campaign.utc_now()}] launch {role}: "
            f"model={model or 'config default'} "
            f"reasoning_effort={reasoning_effort or 'config default'}\n"
        )
        log.flush()
        process = start_codex_process(invocation, workspace=workspace)
        record_lease(root, role, target_state, process.pid)
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
            if isinstance(event, dict) and event.get("type") == "thread.started":
                candidate = nested_thread_id(event)
                if candidate:
                    discovered_thread = candidate
        process.stdout.close()
        returncode = process.wait()
        log.write(f"[{campaign.utc_now()}] {role} exit: {returncode}\n")
    finally:
        log.close()
    return returncode, discovered_thread


def run_codex_canary(
    codex_bin: str,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    if not shutil.which(codex_bin):
        raise campaign.CampaignError(f"Codex executable is unavailable: {codex_bin}")
    marker = "gadi-autoresearch-controller-canary-v2"
    with tempfile.TemporaryDirectory(prefix="gadi-autoresearch-canary-", dir="/tmp") as temp:
        workspace = Path(temp)
        init = subprocess.run(
            ["git", "init", "-q", str(workspace)],
            check=False,
            capture_output=True,
            text=True,
        )
        if init.returncode != 0:
            raise campaign.CampaignError(f"could not initialize Codex canary repository: {init.stderr.strip()}")
        invocation = CodexInvocation(
            [
                *unattended_exec_prefix(codex_bin, model, reasoning_effort),
                "--ephemeral",
                "--json",
                "-C",
                str(workspace),
                "-",
            ],
            (
                "Use the apply_patch tool to create canary.txt containing exactly "
                f"{marker} followed by one newline. Do not create the file with shell redirection, "
                "Python, sed, tee, or another file-writing command. Stop after verifying the file."
            ),
        )
        try:
            result = subprocess.run(
                invocation.command,
                input=invocation.prompt,
                check=False,
                capture_output=True,
                text=True,
                timeout=600,
            )
        except subprocess.TimeoutExpired as exc:
            raise campaign.CampaignError("Codex control-host canary timed out") from exc
        canary = workspace / "canary.txt"
        if result.returncode != 0 or not canary.is_file() or canary.read_text(encoding="utf-8") != marker + "\n":
            output = (result.stdout + "\n" + result.stderr)[-4000:].strip()
            raise campaign.CampaignError(
                f"Codex control-host canary failed with status {result.returncode}: {output}"
            )
    return {
        "status": "pass",
        "sandbox_mode": "danger-full-access",
        "approval_policy": "never",
        "host": socket.gethostname(),
    }


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
        schedule_recovery(
            root,
            category="agent_preflight",
            role="author",
            target_state="needs_agent",
            reason=f"agent preflight failed: {exc}",
        )
        return
    workspace = campaign.canonical(state["workspace"], strict=True)
    campaign.validate_workspace(workspace)
    if not shutil.which(codex_bin):
        schedule_recovery(
            root,
            category="codex_unavailable",
            role="author",
            target_state="needs_agent",
            reason=f"Codex executable is unavailable: {codex_bin}",
        )
        return

    with campaign.locked_state(root) as current:
        if current["status"] != "active" or current["control"]["state"] != "needs_agent":
            return
        campaign.require_approved(current, "allow_auto_agent")
        campaign.require_current_skill(current)
        current["control"].update(
            {
                "state": "agent_running",
                "reason": "controller launched Codex",
                "lease": {
                    "role": "author",
                    "target_state": "needs_agent",
                    "pid": None,
                    "host": socket.gethostname(),
                    "started_at": campaign.utc_now(),
                },
            }
        )
        campaign.add_history(current, "controller_transition", control_updates={"state": "agent_running"})
    invocation = codex_command(codex_bin, workspace, current, root, model, reasoning_effort)
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
            process = start_codex_process(invocation, workspace=workspace)
        except OSError as exc:
            schedule_recovery(
                root,
                category="codex_launch",
                role="author",
                target_state="needs_agent",
                reason=f"failed to launch Codex: {exc}",
            )
            return
        record_lease(root, "author", "needs_agent", process.pid)
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
            if isinstance(event, dict) and event.get("type") == "thread.started":
                candidate = nested_thread_id(event)
                if candidate:
                    discovered_thread = candidate
        process.stdout.close()
        returncode = process.wait()
        log.write(f"[{campaign.utc_now()}] exit: {returncode}\n")
    finally:
        log.close()

    recovery_request: tuple[str, str] | None = None
    with campaign.locked_state(root) as updated:
        if discovered_thread:
            updated["control"]["thread_id"] = discovered_thread
        updated["control"]["agent_turns"] += 1
        updated["control"]["last_agent_at"] = campaign.utc_now()
        updated["control"]["lease"] = None
        if returncode != 0:
            recovery_request = (
                f"codex_exit_{returncode}",
                f"Codex exited with status {returncode}; inspect controller.log",
            )
        elif not updated["control"].get("thread_id"):
            recovery_request = (
                "missing_thread_id",
                "Codex returned no resumable thread ID",
            )
        elif updated["control"]["state"] == "agent_running":
            recovery_request = (
                "missing_handoff",
                "Codex exited without the required campaign handoff",
            )
        else:
            clear_recovery(updated)
        campaign.add_history(updated, "agent_turn_finished", returncode=returncode, thread_id=discovered_thread or updated["control"].get("thread_id"))
    if recovery_request:
        category, reason = recovery_request
        schedule_recovery(
            root,
            category=category,
            role="author",
            target_state="needs_agent",
            reason=reason,
        )


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
        schedule_recovery(
            root,
            category="novelty_review_input",
            role="author",
            target_state="needs_agent",
            reason=f"novelty reviewer input validation failed: {exc}",
        )
        return
    author_thread_id = control.get("thread_id")
    review_requested_at = control.get("novelty_review_requested_at")
    try:
        campaign.live_preflight(state)
    except (campaign.CampaignError, OSError) as exc:
        schedule_recovery(
            root,
            category="novelty_review_preflight",
            role="novelty_reviewer",
            target_state="needs_novelty_review",
            reason=f"novelty reviewer preflight failed: {exc}",
        )
        return
    workspace = campaign.canonical(state["workspace"], strict=True)
    campaign.validate_workspace(workspace)
    try:
        reviewer_workspace_commit = campaign.git_workspace_info(
            workspace,
            require_clean=True,
        )["commit"]
    except (campaign.CampaignError, OSError) as exc:
        schedule_recovery(
            root,
            category="novelty_review_workspace",
            role="author",
            target_state="needs_agent",
            reason=f"novelty reviewer requires a clean source workspace: {exc}",
        )
        return
    if not shutil.which(codex_bin):
        schedule_recovery(
            root,
            category="codex_unavailable",
            role="novelty_reviewer",
            target_state="needs_novelty_review",
            reason=f"Codex executable is unavailable: {codex_bin}",
        )
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
            current["control"].update({
                "state": "needs_agent",
                "reason": f"repair novelty inputs before requesting a fresh review: {exc}",
            })
            campaign.add_history(current, "controller_novelty_review_input_changed", reason=str(exc))
            return
        if not audit_unchanged:
            current["control"].update({
                "state": "needs_agent",
                "reason": "novelty audit changed before launch; validate it and request a fresh review",
            })
            campaign.add_history(current, "controller_novelty_review_input_changed", reason="hash changed")
            return
        previous_review = current["artifacts"].pop("novelty_review", None)
        current["control"].update({
            "state": "novelty_reviewer_running",
            "reason": "controller launched fresh adversarial novelty reviewer",
            "lease": {
                "role": "novelty_reviewer",
                "target_state": "needs_novelty_review",
                "pid": None,
                "host": socket.gethostname(),
                "started_at": campaign.utc_now(),
            },
        })
        campaign.add_history(
            current,
            "controller_novelty_review_started",
            audit_sha256=audit_sha256,
            author_thread_id=author_thread_id,
            invalidated_review_sha256=(previous_review or {}).get("sha256"),
        )

    invocation = novelty_codex_command(
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
            process = start_codex_process(invocation, workspace=workspace)
        except OSError as exc:
            schedule_recovery(
                root,
                category="novelty_review_launch",
                role="novelty_reviewer",
                target_state="needs_novelty_review",
                reason=f"failed to launch novelty reviewer: {exc}",
            )
            return
        record_lease(root, "novelty_reviewer", "needs_novelty_review", process.pid)
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
            if isinstance(event, dict) and event.get("type") == "thread.started":
                candidate = nested_thread_id(event)
                if candidate:
                    discovered_thread = candidate
        process.stdout.close()
        returncode = process.wait()
        log.write(f"[{campaign.utc_now()}] novelty-review exit: {returncode}\n")
    finally:
        log.close()

    recovery_request: tuple[str, str] | None = None
    with campaign.locked_state(root) as updated:
        updated["control"]["agent_turns"] += 1
        updated["control"]["last_agent_at"] = campaign.utc_now()
        updated["control"]["lease"] = None
        failure: str | None = None
        inconclusive = False
        if returncode != 0:
            failure = f"novelty reviewer exited with status {returncode}; inspect controller.log"
        elif not discovered_thread:
            failure = "novelty reviewer returned no thread ID"
        elif discovered_thread == author_thread_id:
            failure = "novelty reviewer reused the author thread instead of a fresh context"
        elif (
            updated["control"]["state"] == "needs_agent"
            and updated["control"].get("reason", "").startswith("inconclusive novelty review:")
            and "novelty_review" not in updated["artifacts"]
        ):
            inconclusive = True
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
            recovery_request = ("novelty_review_turn", failure)
        elif inconclusive:
            fallback_phase = scientific_fallback(
                updated,
                updated["control"]["reason"],
            )
            campaign.add_history(
                updated,
                "novelty_review_inconclusive",
                review_thread_id=discovered_thread,
                fallback_phase=fallback_phase,
            )
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
                    fallback_phase = scientific_fallback(
                        updated,
                        f"conditional novelty review is outside the mission: {exc}",
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
                    fallback_phase = scientific_fallback(
                        updated,
                        f"cold novelty review rejected or reclassified the active candidate: {exc}",
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
        if not failure:
            clear_recovery(updated)
    if recovery_request:
        category, reason = recovery_request
        schedule_recovery(
            root,
            category=category,
            role="novelty_reviewer",
            target_state="needs_novelty_review",
            reason=reason,
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
        schedule_recovery(
            root,
            category="novelty_arbitration_input",
            role="author",
            target_state="needs_agent",
            reason=f"novelty arbiter input validation failed: {exc}",
        )
        return
    author_thread_id = control.get("thread_id")
    review_thread_id = state["artifacts"]["novelty_review"].get("review_thread_id")
    arbitration_requested_at = control.get("novelty_arbitration_requested_at")
    if not author_thread_id or not review_thread_id or author_thread_id == review_thread_id:
        schedule_recovery(
            root,
            category="novelty_arbitration_threads",
            role="author",
            target_state="needs_agent",
            reason="novelty arbitration requires distinct attested author and reviewer threads",
        )
        return
    try:
        campaign.live_preflight(state)
    except (campaign.CampaignError, OSError) as exc:
        schedule_recovery(
            root,
            category="novelty_arbitration_preflight",
            role="novelty_arbiter",
            target_state="needs_novelty_arbitration",
            reason=f"novelty arbiter preflight failed: {exc}",
        )
        return
    workspace = campaign.canonical(state["workspace"], strict=True)
    campaign.validate_workspace(workspace)
    try:
        arbiter_workspace_commit = campaign.git_workspace_info(workspace, require_clean=True)["commit"]
    except (campaign.CampaignError, OSError) as exc:
        schedule_recovery(
            root,
            category="novelty_arbitration_workspace",
            role="author",
            target_state="needs_agent",
            reason=f"novelty arbiter requires a clean source workspace: {exc}",
        )
        return
    if not shutil.which(codex_bin):
        schedule_recovery(
            root,
            category="codex_unavailable",
            role="novelty_arbiter",
            target_state="needs_novelty_arbitration",
            reason=f"Codex executable is unavailable: {codex_bin}",
        )
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
            current["control"].update(
                {
                    "state": "needs_agent",
                    "reason": f"repair novelty arbitration inputs before retrying: {exc}",
                }
            )
            campaign.add_history(current, "controller_novelty_arbitration_input_changed", reason=str(exc))
            return
        if not inputs_unchanged:
            current["control"].update(
                {
                    "state": "needs_agent",
                    "reason": "novelty arbitration inputs changed; validate and request a fresh arbitration",
                }
            )
            campaign.add_history(current, "controller_novelty_arbitration_input_changed", reason="hash changed")
            return
        previous_arbitration = current["artifacts"].pop("novelty_arbitration", None)
        current["control"].update(
            {
                "state": "novelty_arbiter_running",
                "reason": "controller launched fresh independent novelty arbiter",
                "lease": {
                    "role": "novelty_arbiter",
                    "target_state": "needs_novelty_arbitration",
                    "pid": None,
                    "host": socket.gethostname(),
                    "started_at": campaign.utc_now(),
                },
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

    invocation = novelty_arbiter_codex_command(
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
            process = start_codex_process(invocation, workspace=workspace)
        except OSError as exc:
            schedule_recovery(
                root,
                category="novelty_arbitration_launch",
                role="novelty_arbiter",
                target_state="needs_novelty_arbitration",
                reason=f"failed to launch novelty arbiter: {exc}",
            )
            return
        record_lease(root, "novelty_arbiter", "needs_novelty_arbitration", process.pid)
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
            if isinstance(event, dict) and event.get("type") == "thread.started":
                candidate = nested_thread_id(event)
                if candidate:
                    discovered_thread = candidate
        process.stdout.close()
        returncode = process.wait()
        log.write(f"[{campaign.utc_now()}] novelty-arbitration exit: {returncode}\n")
    finally:
        log.close()

    recovery_request: tuple[str, str] | None = None
    with campaign.locked_state(root) as updated:
        updated["control"]["agent_turns"] += 1
        updated["control"]["last_agent_at"] = campaign.utc_now()
        updated["control"]["lease"] = None
        failure: str | None = None
        inconclusive = (
            updated["control"]["state"] == "needs_agent"
            and updated["control"].get("reason", "").startswith("inconclusive novelty arbitration:")
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
                if not inconclusive:
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
            recovery_request = ("novelty_arbitration_turn", failure)
        elif inconclusive:
            updated["control"]["novelty_arbitration_thread_id"] = discovered_thread
            fallback_phase = scientific_fallback(updated, updated["control"]["reason"])
            campaign.add_history(
                updated,
                "novelty_arbitration_inconclusive",
                arbiter_thread_id=discovered_thread,
                reason=updated["control"].get("reason"),
                fallback_phase=fallback_phase,
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
                fallback_phase = scientific_fallback(
                    updated,
                    f"novelty arbitration rejected the candidate: {exc}",
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
        if not failure:
            clear_recovery(updated)
    if recovery_request:
        category, reason = recovery_request
        schedule_recovery(
            root,
            category=category,
            role="novelty_arbiter",
            target_state="needs_novelty_arbitration",
            reason=reason,
        )


def run_failure_reviewer(
    root: Path,
    codex_bin: str,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> None:
    state = campaign.load_state(root)
    campaign.require_approved(state, "allow_auto_agent")
    campaign.require_current_skill(state)
    if int(state["control"]["agent_turns"]) >= int(state["approval"]["max_agent_turns"]):
        pause_campaign(root, "approved Codex turn budget exhausted before failure review")
        return
    try:
        if not campaign.learning_enabled(state):
            raise campaign.CampaignError("hypothesis evolution is not initialized")
        finding_id = state["learning"].get("pending_failure_review")
        if not finding_id:
            raise campaign.CampaignError("no failure-review finding is pending")
        interpretation = campaign.learning_interpretation_by_finding(state, finding_id)
        if not interpretation.get("review_required"):
            raise campaign.CampaignError("pending finding does not require independent review")
        experiment = state["experiments"][interpretation["experiment_id"]]
        graph = campaign.load_research_graph(state)
        hypothesis = campaign.hypothesis_by_id(graph, interpretation["hypothesis_id"])
        interpretation_sha256 = campaign.sha256_json(interpretation)
        experiment_sha256 = campaign.sha256_json(experiment)
        hypothesis_sha256 = campaign.sha256_json(hypothesis)
        if interpretation.get("result_sha256"):
            success = campaign.canonical(experiment["success_file"], strict=True)
            if campaign.sha256_file(success) != interpretation["result_sha256"]:
                raise campaign.CampaignError("experiment result changed after interpretation")
    except (campaign.CampaignError, KeyError, OSError) as exc:
        schedule_recovery(
            root,
            category="failure_review_input",
            role="author",
            target_state="needs_agent",
            reason=f"failure-review input validation failed: {exc}",
        )
        return
    author_thread_id = state["control"].get("thread_id")
    forbidden_reviewer_threads = {
        value
        for value in (
            author_thread_id,
            interpretation.get("author_thread_id"),
            *(
                review.get("reviewer_thread_id")
                for review in state["learning"].get("reviews", {}).values()
                if isinstance(review, dict)
            ),
        )
        if value
    }
    requested_at = state["control"].get("failure_review_requested_at")
    if not author_thread_id:
        schedule_recovery(
            root,
            category="failure_review_author_thread",
            role="author",
            target_state="needs_agent",
            reason="failure review requires a recorded author thread ID",
        )
        return
    try:
        campaign.live_preflight(state)
    except (campaign.CampaignError, OSError) as exc:
        schedule_recovery(
            root,
            category="failure_review_preflight",
            role="failure_reviewer",
            target_state="needs_failure_review",
            reason=f"failure-review preflight failed: {exc}",
        )
        return
    workspace = campaign.canonical(state["workspace"], strict=True)
    campaign.validate_workspace(workspace)
    try:
        workspace_commit = campaign.git_workspace_info(workspace, require_clean=True)["commit"]
    except (campaign.CampaignError, OSError) as exc:
        schedule_recovery(
            root,
            category="failure_review_workspace",
            role="author",
            target_state="needs_agent",
            reason=f"failure reviewer requires a clean source workspace: {exc}",
        )
        return
    if not shutil.which(codex_bin):
        schedule_recovery(
            root,
            category="codex_unavailable",
            role="failure_reviewer",
            target_state="needs_failure_review",
            reason=f"Codex executable is unavailable: {codex_bin}",
        )
        return

    with campaign.locked_state(root) as current:
        if current["status"] != "active" or current["control"]["state"] != "needs_failure_review":
            return
        campaign.require_approved(current, "allow_auto_agent")
        campaign.require_current_skill(current)
        current_finding = current.get("learning", {}).get("pending_failure_review")
        if current_finding != finding_id:
            current["control"].update(
                {"state": "needs_agent", "reason": "failure-review finding changed before launch"}
            )
            return
        current_interpretation = campaign.learning_interpretation_by_finding(current, finding_id)
        if campaign.sha256_json(current_interpretation) != interpretation_sha256:
            current["control"].update(
                {"state": "needs_agent", "reason": "failure-review interpretation changed before launch"}
            )
            return
        if campaign.sha256_json(current["experiments"][interpretation["experiment_id"]]) != experiment_sha256:
            current["control"].update(
                {"state": "needs_agent", "reason": "failure-review experiment changed before launch"}
            )
            return
        current["control"].update(
            {
                "state": "failure_reviewer_running",
                "reason": f"controller launched fresh critic for {finding_id}",
                "lease": {
                    "role": "failure_reviewer",
                    "target_state": "needs_failure_review",
                    "pid": None,
                    "host": socket.gethostname(),
                    "started_at": campaign.utc_now(),
                },
            }
        )
        campaign.add_history(
            current,
            "controller_failure_review_started",
            finding_id=finding_id,
            interpretation_sha256=interpretation_sha256,
            author_thread_id=author_thread_id,
        )

    invocation = failure_reviewer_codex_command(
        codex_bin,
        workspace,
        root,
        finding_id,
        hypothesis,
        experiment,
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
            f"\n[{campaign.utc_now()}] launch failure reviewer for {finding_id}: "
            f"model={model or 'config default'} "
            f"reasoning_effort={reasoning_effort or 'config default'}\n"
        )
        log.flush()
        try:
            process = start_codex_process(invocation, workspace=workspace)
        except OSError as exc:
            schedule_recovery(
                root,
                category="failure_review_launch",
                role="failure_reviewer",
                target_state="needs_failure_review",
                reason=f"failed to launch failure reviewer: {exc}",
            )
            return
        record_lease(root, "failure_reviewer", "needs_failure_review", process.pid)
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
            if isinstance(event, dict) and event.get("type") == "thread.started":
                candidate_thread = nested_thread_id(event)
                if candidate_thread:
                    discovered_thread = candidate_thread
        process.stdout.close()
        returncode = process.wait()
        log.write(f"[{campaign.utc_now()}] failure-review exit: {returncode}\n")
    finally:
        log.close()

    recovery_request: tuple[str, str] | None = None
    with campaign.locked_state(root) as updated:
        updated["control"]["agent_turns"] += 1
        updated["control"]["last_agent_at"] = campaign.utc_now()
        updated["control"]["lease"] = None
        failure: str | None = None
        review: dict[str, Any] | None = None
        if returncode != 0:
            failure = f"failure reviewer exited with status {returncode}; inspect controller.log"
        elif not discovered_thread:
            failure = "failure reviewer returned no thread ID"
        elif discovered_thread in forbidden_reviewer_threads:
            failure = "failure reviewer reused an author or prior reviewer thread instead of a fresh context"
        else:
            try:
                current_interpretation = campaign.learning_interpretation_by_finding(
                    updated, finding_id
                )
                if campaign.sha256_json(current_interpretation) != interpretation_sha256:
                    raise campaign.CampaignError("interpretation changed during failure review")
                current_experiment = updated["experiments"][interpretation["experiment_id"]]
                if campaign.sha256_json(current_experiment) != experiment_sha256:
                    raise campaign.CampaignError("registered experiment changed during failure review")
                current_graph = campaign.load_research_graph(updated)
                current_hypothesis = campaign.hypothesis_by_id(
                    current_graph, interpretation["hypothesis_id"]
                )
                if campaign.sha256_json(current_hypothesis) != hypothesis_sha256:
                    raise campaign.CampaignError("hypothesis changed during failure review")
                if interpretation.get("result_sha256"):
                    current_success = campaign.canonical(
                        current_experiment["success_file"], strict=True
                    )
                    if campaign.sha256_file(current_success) != interpretation["result_sha256"]:
                        raise campaign.CampaignError("experiment result changed during failure review")
                review = campaign.learning_failure_review_by_finding(updated, finding_id)
                if review.get("interpretation_sha256") != interpretation_sha256:
                    raise campaign.CampaignError("failure review is bound to another interpretation")
                if requested_at and campaign.parse_time(review["recorded_at"]) < campaign.parse_time(
                    requested_at
                ):
                    raise campaign.CampaignError("failure reviewer reused a pre-request review")
                current_workspace = campaign.git_workspace_info(workspace, require_clean=True)
                if current_workspace["commit"] != workspace_commit:
                    raise campaign.CampaignError("failure reviewer changed the source workspace")
            except (campaign.CampaignError, OSError) as exc:
                failure = f"failure-review validation failed: {exc}"
        if not failure and updated["control"]["state"] == "failure_reviewer_running":
            failure = "failure reviewer exited without the required campaign handoff"
        if not failure and updated["control"]["state"] not in {"needs_agent", "paused"}:
            failure = f"failure reviewer used an invalid handoff: {updated['control']['state']}"
        if failure:
            recovery_request = ("failure_review_turn", failure)
        else:
            assert review is not None and discovered_thread is not None
            entries = campaign.load_learning_ledger(updated)
            for entry in entries:
                if entry.get("entry_type") == "failure_review" and entry.get(
                    "finding_id"
                ) == finding_id:
                    entry.update(
                        {
                            "independent": True,
                            "reviewer_thread_id": discovered_thread,
                            "author_thread_id": author_thread_id,
                            "workspace_commit": workspace_commit,
                            "experiment_sha256": experiment_sha256,
                            "hypothesis_sha256": hypothesis_sha256,
                            "attested_at": campaign.utc_now(),
                        }
                    )
            campaign.rewrite_learning_ledger(updated, entries)
            updated["learning"]["reviews"][finding_id] = {
                "independent": True,
                "decision": review["decision"],
                "allowed_action": review["allowed_action"],
                "material_change": review["material_change"],
                "interpretation_sha256": interpretation_sha256,
                "reviewer_thread_id": discovered_thread,
                "author_thread_id": author_thread_id,
                "workspace_commit": workspace_commit,
                "experiment_sha256": experiment_sha256,
                "hypothesis_sha256": hypothesis_sha256,
                "attested_at": campaign.utc_now(),
            }
            updated["learning"]["pending_failure_review"] = None
            lab = campaign.ensure_research_os(updated)
            chain = lab["review_chain"]
            if chain.get("hypothesis_id") != interpretation["hypothesis_id"]:
                chain.update(
                    {
                        "hypothesis_id": interpretation["hypothesis_id"],
                        "count": 0,
                        "finding_ids": [],
                    }
                )
            chain["count"] = int(chain.get("count", 0)) + 1
            if finding_id not in chain["finding_ids"]:
                chain["finding_ids"].append(finding_id)
            lab["portfolio"]["director_decision_required"] = finding_id
            updated["control"]["failure_review_thread_id"] = discovered_thread
            updated["control"].update(
                {
                    "state": "needs_agent",
                    "reason": (
                        f"fresh failure review {review['decision']} authorizes "
                        f"{review['allowed_action']} for {finding_id}"
                    ),
                }
            )
            clear_recovery(updated)
        campaign.add_history(
            updated,
            "failure_review_turn_finished",
            returncode=returncode,
            finding_id=finding_id,
            reviewer_thread_id=discovered_thread,
            author_thread_id=author_thread_id,
            validated=not failure,
            failure=failure,
        )
    if recovery_request:
        category, reason = recovery_request
        schedule_recovery(
            root,
            category=category,
            role="failure_reviewer",
            target_state="needs_failure_review",
            reason=reason,
        )


def run_opportunity_scout(
    root: Path,
    codex_bin: str,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> None:
    state = campaign.load_state(root)
    campaign.require_approved(state, "allow_auto_agent")
    campaign.require_current_skill(state)
    if int(state["control"]["agent_turns"]) >= int(state["approval"]["max_agent_turns"]):
        pause_campaign(root, "approved Codex turn budget exhausted during opportunity scouting")
        return
    lab = campaign.ensure_research_os(state)
    scouting = lab["scouting"]
    missing = [
        role
        for role in campaign.research_operating_model.SCOUT_ROLES
        if role not in scouting.get("reports", {})
    ]
    if not missing:
        set_control(root, state="needs_agent", reason="blind opportunity scout round is complete")
        return
    role = missing[0]
    round_number = int(scouting["round"])
    try:
        campaign.live_preflight(state)
        workspace = campaign.canonical(state["workspace"], strict=True)
        campaign.validate_workspace(workspace)
        workspace_commit = campaign.git_workspace_info(workspace, require_clean=True)["commit"]
    except (campaign.CampaignError, OSError) as exc:
        schedule_recovery(
            root,
            category="opportunity_scout_preflight",
            role="opportunity_scout",
            target_state="needs_opportunity_scouts",
            reason=f"opportunity scout preflight failed: {exc}",
        )
        return
    if not shutil.which(codex_bin):
        schedule_recovery(
            root,
            category="codex_unavailable",
            role="opportunity_scout",
            target_state="needs_opportunity_scouts",
            reason=f"Codex executable is unavailable: {codex_bin}",
        )
        return
    forbidden_threads = {
        value
        for value in [
            state["control"].get("thread_id"),
            *state["control"].get("opportunity_scout_thread_ids", {}).values(),
        ]
        if value
    }
    with campaign.locked_state(root) as current:
        if current["status"] != "active" or current["control"]["state"] != "needs_opportunity_scouts":
            return
        current_lab = campaign.ensure_research_os(current)
        current_scouting = current_lab["scouting"]
        if int(current_scouting["round"]) != round_number or role in current_scouting["reports"]:
            current["control"].update(
                {"state": "needs_opportunity_scouts", "reason": "scouting assignment changed before launch"}
            )
            return
        current_scouting["active_role"] = role
        current["control"].update(
            {
                "state": "opportunity_scout_running",
                "reason": f"controller launched blind {role} opportunity scout",
                "lease": {
                    "role": "opportunity_scout",
                    "target_state": "needs_opportunity_scouts",
                    "pid": None,
                    "host": socket.gethostname(),
                    "started_at": campaign.utc_now(),
                },
            }
        )
        campaign.add_history(
            current,
            "controller_opportunity_scout_started",
            role=role,
            round=round_number,
        )
        launch_state = current
    invocation = opportunity_scout_codex_command(
        codex_bin,
        workspace,
        root,
        launch_state,
        role,
        round_number,
        model,
        reasoning_effort,
    )
    try:
        returncode, discovered_thread = execute_fresh_codex(
            invocation,
            workspace=workspace,
            root=root,
            role=f"opportunity_scout_{role}",
            target_state="needs_opportunity_scouts",
            model=model,
            reasoning_effort=reasoning_effort,
        )
    except OSError as exc:
        schedule_recovery(
            root,
            category="opportunity_scout_launch",
            role="opportunity_scout",
            target_state="needs_opportunity_scouts",
            reason=f"failed to launch opportunity scout: {exc}",
        )
        return
    recovery_request: tuple[str, str] | None = None
    with campaign.locked_state(root) as updated:
        updated["control"]["agent_turns"] += 1
        updated["control"]["last_agent_at"] = campaign.utc_now()
        updated["control"]["lease"] = None
        failure = None
        updated_lab = campaign.ensure_research_os(updated)
        updated_scouting = updated_lab["scouting"]
        report = updated_scouting.get("reports", {}).get(role)
        if returncode != 0:
            failure = f"opportunity scout exited with status {returncode}"
        elif not discovered_thread:
            failure = "opportunity scout returned no thread ID"
        elif discovered_thread in forbidden_threads:
            failure = "opportunity scout reused an author or earlier scout thread"
        elif not report:
            failure = "opportunity scout returned no structured report"
        elif updated["control"]["state"] != "needs_opportunity_scouts":
            failure = "opportunity scout exited without the required coordinator handoff"
        else:
            try:
                if campaign.git_workspace_info(workspace, require_clean=True)["commit"] != workspace_commit:
                    raise campaign.CampaignError("opportunity scout changed the source workspace")
            except (campaign.CampaignError, OSError) as exc:
                failure = str(exc)
        if failure:
            updated_scouting.get("reports", {}).pop(role, None)
            updated_scouting["active_role"] = None
            recovery_request = ("opportunity_scout_turn", failure)
        else:
            report.update(
                {
                    "independent": True,
                    "thread_id": discovered_thread,
                    "workspace_commit": workspace_commit,
                    "attested_at": campaign.utc_now(),
                }
            )
            updated["control"].setdefault("opportunity_scout_thread_ids", {})[role] = discovered_thread
            updated_scouting["active_role"] = None
            remaining = [
                item
                for item in campaign.research_operating_model.SCOUT_ROLES
                if item not in updated_scouting["reports"]
            ]
            updated["control"].update(
                {
                    "state": "needs_opportunity_scouts" if remaining else "needs_agent",
                    "reason": (
                        f"continue blind scouting with {remaining[0]}"
                        if remaining
                        else "all blind opportunity scouts are attested; director must synthesize the portfolio"
                    ),
                }
            )
            clear_recovery(updated)
        campaign.add_history(
            updated,
            "opportunity_scout_turn_finished",
            role=role,
            round=round_number,
            returncode=returncode,
            thread_id=discovered_thread,
            validated=not failure,
            failure=failure,
        )
    if recovery_request:
        category, reason = recovery_request
        schedule_recovery(
            root,
            category=category,
            role="opportunity_scout",
            target_state="needs_opportunity_scouts",
            reason=reason,
        )


def run_evidence_analyst(
    root: Path,
    codex_bin: str,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> None:
    state = campaign.load_state(root)
    campaign.require_approved(state, "allow_auto_agent")
    campaign.require_current_skill(state)
    pending = campaign.pending_independent_analysis_ids(state)
    if not pending:
        set_control(root, state="needs_agent", reason="no independent evidence analysis is pending")
        return
    if int(state["control"]["agent_turns"]) >= int(state["approval"]["max_agent_turns"]):
        pause_campaign(root, "approved Codex turn budget exhausted before evidence analysis")
        return
    experiment_id = pending[0]
    experiment = state["experiments"][experiment_id]
    graph = campaign.load_research_graph(state)
    hypothesis = campaign.hypothesis_by_id(graph, campaign.experiment_hypothesis_id(experiment))
    experiment_sha256 = campaign.sha256_json(experiment)
    result_sha256 = campaign.sha256_file(
        campaign.canonical(experiment["success_file"], strict=True)
    )
    try:
        campaign.live_preflight(state)
        workspace = campaign.canonical(state["workspace"], strict=True)
        campaign.validate_workspace(workspace)
        workspace_commit = campaign.git_workspace_info(workspace, require_clean=True)["commit"]
    except (campaign.CampaignError, OSError) as exc:
        schedule_recovery(
            root,
            category="evidence_analysis_preflight",
            role="evidence_analyst",
            target_state="needs_evidence_analysis",
            reason=f"evidence analyst preflight failed: {exc}",
        )
        return
    if not shutil.which(codex_bin):
        schedule_recovery(
            root,
            category="codex_unavailable",
            role="evidence_analyst",
            target_state="needs_evidence_analysis",
            reason=f"Codex executable is unavailable: {codex_bin}",
        )
        return
    author_thread = state["control"].get("thread_id")
    with campaign.locked_state(root) as current:
        if current["status"] != "active" or current["control"]["state"] not in {
            "needs_evidence_analysis",
            "needs_agent",
        }:
            return
        if experiment_id not in campaign.pending_independent_analysis_ids(current):
            current["control"].update(
                {"state": "needs_agent", "reason": "analysis target changed before launch"}
            )
            return
        current["control"].update(
            {
                "state": "evidence_analyst_running",
                "reason": f"controller launched blind analyst for {experiment_id}",
                "analysis_experiment_id": experiment_id,
                "analysis_thread_id": None,
                "lease": {
                    "role": "evidence_analyst",
                    "target_state": "needs_evidence_analysis",
                    "pid": None,
                    "host": socket.gethostname(),
                    "started_at": campaign.utc_now(),
                },
            }
        )
        campaign.add_history(current, "controller_evidence_analyst_started", experiment_id=experiment_id)
    invocation = evidence_analyst_codex_command(
        codex_bin,
        workspace,
        root,
        experiment,
        hypothesis,
        model,
        reasoning_effort,
    )
    try:
        returncode, discovered_thread = execute_fresh_codex(
            invocation,
            workspace=workspace,
            root=root,
            role="evidence_analyst",
            target_state="needs_evidence_analysis",
            model=model,
            reasoning_effort=reasoning_effort,
        )
    except OSError as exc:
        schedule_recovery(
            root,
            category="evidence_analysis_launch",
            role="evidence_analyst",
            target_state="needs_evidence_analysis",
            reason=f"failed to launch evidence analyst: {exc}",
        )
        return
    recovery_request: tuple[str, str] | None = None
    with campaign.locked_state(root) as updated:
        updated["control"]["agent_turns"] += 1
        updated["control"]["last_agent_at"] = campaign.utc_now()
        updated["control"]["lease"] = None
        failure = None
        analysis = campaign.independent_analysis_entries(updated).get(experiment_id)
        if returncode != 0:
            failure = f"evidence analyst exited with status {returncode}"
        elif not discovered_thread:
            failure = "evidence analyst returned no thread ID"
        elif discovered_thread == author_thread:
            failure = "evidence analyst reused the author thread"
        elif not analysis:
            failure = "evidence analyst returned no structured analysis"
        elif updated["control"]["state"] != "needs_agent":
            failure = "evidence analyst exited without the required author handoff"
        else:
            try:
                current_experiment = updated["experiments"][experiment_id]
                if campaign.sha256_json(current_experiment) != experiment_sha256:
                    raise campaign.CampaignError("registered experiment changed during analysis")
                if result_sha256 and campaign.sha256_file(
                    campaign.canonical(current_experiment["success_file"], strict=True)
                ) != result_sha256:
                    raise campaign.CampaignError("experiment output changed during analysis")
                if campaign.git_workspace_info(workspace, require_clean=True)["commit"] != workspace_commit:
                    raise campaign.CampaignError("evidence analyst changed the source workspace")
            except (campaign.CampaignError, OSError) as exc:
                failure = str(exc)
        if failure:
            entries = [
                entry
                for entry in campaign.load_learning_ledger(updated)
                if not (
                    entry.get("entry_type") == "independent_analysis"
                    and entry.get("experiment_id") == experiment_id
                    and not entry.get("independent")
                )
            ]
            campaign.rewrite_learning_ledger(updated, entries)
            updated["control"].update(
                {"analysis_experiment_id": None, "analysis_thread_id": None}
            )
            recovery_request = ("evidence_analysis_turn", failure)
        else:
            entries = campaign.load_learning_ledger(updated)
            for entry in entries:
                if entry.get("entry_type") == "independent_analysis" and entry.get(
                    "experiment_id"
                ) == experiment_id:
                    entry.update(
                        {
                            "independent": True,
                            "analyst_thread_id": discovered_thread,
                            "workspace_commit": workspace_commit,
                            "attested_at": campaign.utc_now(),
                        }
                    )
            campaign.rewrite_learning_ledger(updated, entries)
            updated["control"]["analysis_thread_id"] = discovered_thread
            remaining = campaign.pending_independent_analysis_ids(updated)
            updated["control"].update(
                {
                    "state": "needs_evidence_analysis" if remaining else "needs_agent",
                    "analysis_experiment_id": remaining[0] if remaining else None,
                    "reason": (
                        f"blind analysis remains for {remaining[0]}"
                        if remaining
                        else f"blind analysis for {experiment_id} is attested; director must interpret it"
                    ),
                }
            )
            clear_recovery(updated)
        campaign.add_history(
            updated,
            "evidence_analyst_turn_finished",
            experiment_id=experiment_id,
            returncode=returncode,
            analyst_thread_id=discovered_thread,
            validated=not failure,
            failure=failure,
        )
    if recovery_request:
        category, reason = recovery_request
        schedule_recovery(
            root,
            category=category,
            role="evidence_analyst",
            target_state="needs_evidence_analysis",
            reason=reason,
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
    if control == "needs_failure_review":
        return "launch one fresh independent failure-critic thread"
    if control == "needs_opportunity_scouts":
        return "launch the next blind opportunity-scout thread"
    if control == "needs_evidence_analysis":
        return "launch one fresh blind raw-result analyst"
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
    ensure_control_schema(root)
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
    if control in RUNNING_STATES:
        role, target_state = RUNNING_STATES[control]
        if lease_process_alive(state["control"].get("lease")):
            return True
        schedule_recovery(
            root,
            category=f"stale_{role}",
            role=role,
            target_state=target_state,
            reason=f"{control} lease has no live matching Codex process",
        )
        return True
    if control == "waiting_time":
        wake_due(root, state)
        state = campaign.load_state(root)
        control = state["control"]["state"]
    if control == "waiting_pbs":
        refresh_pbs(root)
        state = campaign.load_state(root)
        control = state["control"]["state"]
    if control == "needs_agent":
        if campaign.pending_independent_analysis_ids(state):
            set_control(
                root,
                state="needs_evidence_analysis",
                reason="terminal evidence requires blind analysis before the director resumes",
            )
            state = campaign.load_state(root)
            control = state["control"]["state"]
    if control == "needs_agent":
        maybe_repack_workspace(root, state)
        run_agent(root, codex_bin, model, reasoning_effort)
    elif control == "needs_novelty_review":
        run_novelty_reviewer(root, codex_bin, model, reasoning_effort)
    elif control == "needs_novelty_arbitration":
        run_novelty_arbiter(root, codex_bin, model, reasoning_effort)
    elif control == "needs_failure_review":
        run_failure_reviewer(root, codex_bin, model, reasoning_effort)
    elif control == "needs_opportunity_scouts":
        run_opportunity_scout(root, codex_bin, model, reasoning_effort)
    elif control == "needs_evidence_analysis":
        run_evidence_analyst(root, codex_bin, model, reasoning_effort)
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
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--start", action="store_true", help="perform controller actions; preview is default")
    parser.add_argument("--loop", action="store_true", help="keep watching until the campaign pauses or completes")
    parser.add_argument("--canary", action="store_true", help="run one ephemeral real Codex apply_patch canary")
    args = parser.parse_args(argv)
    try:
        root = campaign.canonical(args.root, strict=True)
        state = campaign.load_state(root)
        campaign.require_approved(state, require_active=False, allow_expired=True)
        if args.poll_seconds < 60:
            raise campaign.CampaignError("poll-seconds must be at least 60")
        if args.canary:
            print(
                json.dumps(
                    run_codex_canary(args.codex_bin, args.model, args.reasoning_effort),
                    indent=2,
                )
            )
            return 0
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
                if state["control"]["state"] in {"paused", "complete"}:
                    break
                time.sleep(args.poll_seconds)
    except (campaign.CampaignError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
