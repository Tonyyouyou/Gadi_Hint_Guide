#!/usr/bin/env python3
"""Schemas for inode-bounded hypothesis evolution and experiment learning."""

from __future__ import annotations

import re
from typing import Any

import research_operating_model


GRAPH_SCHEMA_VERSION = 1
LEDGER_SCHEMA_VERSION = 2
MAX_HYPOTHESES = 64
MAX_ACTIVE_HYPOTHESES = 3
SAFE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")

EVIDENCE_ROLES = {"exploratory", "diagnostic", "confirmatory", "replication"}
VALIDITY_CLASSES = {"valid", "technical_invalid", "contaminated"}
OUTCOME_CLASSES = {
    "supports",
    "falsifies",
    "qualifies",
    "unexpected",
    "inconclusive",
    "not_scientific",
}
NEXT_ACTIONS = {
    "continue",
    "repair",
    "refine",
    "branch",
    "pivot",
    "stop",
    "confirm",
    "protocol_refine",
    "narrow_scope",
    "park",
    "kill",
    "investigate",
}
INFORMATION_GAIN = {"none", "low", "medium", "high"}
MATERIALITY_CLASSES = {"nonmaterial", "branch_material", "claim_material"}
DECISION_SCOPES = {"local", "branch", "portfolio", "claim"}
ASSUMPTION_STATES = {"untested", "supported", "weakened", "falsified", "qualified"}
HYPOTHESIS_STATES = {"active", "backup", "eliminated", "superseded"}
HYPOTHESIS_RELATIONS = {"seed", "refinement", "branch"}
REVIEW_DECISIONS = {"accept", "revise", "reject"}
FAILURE_CLASSES = {
    "implementation",
    "assumption",
    "mechanism",
    "scope",
    "ceiling",
    "anomaly",
    "inconclusive",
}


class LearningError(ValueError):
    pass


def require_text(payload: dict[str, Any], key: str, label: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LearningError(f"{label}.{key} must be non-empty text")
    return value.strip()


def require_id(payload: dict[str, Any], key: str, label: str) -> str:
    value = require_text(payload, key, label)
    if not SAFE_ID.fullmatch(value):
        raise LearningError(f"{label}.{key} is not a safe identifier")
    return value


def require_text_list(
    payload: dict[str, Any],
    key: str,
    label: str,
    *,
    allow_empty: bool = False,
) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise LearningError(f"{label}.{key} must be a list of non-empty strings")
    if not allow_empty and not value:
        raise LearningError(f"{label}.{key} cannot be empty")
    if len(set(value)) != len(value):
        raise LearningError(f"{label}.{key} contains duplicates")
    return [item.strip() for item in value]


def validate_assumptions(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise LearningError(f"{label}.assumptions must be a non-empty list")
    result: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, raw in enumerate(value):
        item_label = f"{label}.assumptions[{index}]"
        if not isinstance(raw, dict):
            raise LearningError(f"{item_label} must be an object")
        assumption_id = require_id(raw, "id", item_label)
        if assumption_id in ids:
            raise LearningError(f"{label}.assumptions contains duplicate id {assumption_id}")
        ids.add(assumption_id)
        require_text(raw, "text", item_label)
        if raw.get("status") not in ASSUMPTION_STATES:
            raise LearningError(f"{item_label}.status is invalid")
        result.append(raw)
    return result


def validate_hypothesis(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LearningError(f"{label} must be an object")
    require_id(value, "id", label)
    require_id(value, "candidate_id", label)
    version = value.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version <= 0:
        raise LearningError(f"{label}.version must be a positive integer")
    parent_id = value.get("parent_id")
    if parent_id is not None and (not isinstance(parent_id, str) or not SAFE_ID.fullmatch(parent_id)):
        raise LearningError(f"{label}.parent_id must be null or a safe identifier")
    if value.get("relation") not in HYPOTHESIS_RELATIONS:
        raise LearningError(f"{label}.relation is invalid")
    if value.get("status") not in HYPOTHESIS_STATES:
        raise LearningError(f"{label}.status is invalid")
    require_text_list(value, "origin_finding_ids", label, allow_empty=True)
    for key in ("observation", "causal_hypothesis", "mechanism"):
        require_text(value, key, label)
    require_text_list(value, "predictions", label)
    require_text_list(value, "falsifiers", label)
    validate_assumptions(value.get("assumptions"), label)
    require_text(value, "created_at", label)
    return value


def validate_graph(
    payload: Any,
    *,
    mission_sha256: str,
    route_sha256: str,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise LearningError("research_graph must be an object")
    if payload.get("schema_version") != GRAPH_SCHEMA_VERSION:
        raise LearningError(f"research_graph.schema_version must be {GRAPH_SCHEMA_VERSION}")
    if payload.get("mission_sha256") != mission_sha256:
        raise LearningError("research_graph is bound to a different mission")
    if payload.get("route_sha256") != route_sha256:
        raise LearningError("research_graph is bound to a different route")
    revision = payload.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision <= 0:
        raise LearningError("research_graph.revision must be a positive integer")
    hypotheses = payload.get("hypotheses")
    if not isinstance(hypotheses, list) or not hypotheses:
        raise LearningError("research_graph.hypotheses must be a non-empty list")
    if len(hypotheses) > MAX_HYPOTHESES:
        raise LearningError(f"research_graph exceeds {MAX_HYPOTHESES} hypotheses")
    records = [validate_hypothesis(item, f"research_graph.hypotheses[{index}]") for index, item in enumerate(hypotheses)]
    by_id = {item["id"]: item for item in records}
    if len(by_id) != len(records):
        raise LearningError("research_graph has duplicate hypothesis ids")
    for item in records:
        parent_id = item.get("parent_id")
        if parent_id is not None and parent_id not in by_id:
            raise LearningError(f"hypothesis {item['id']} has unknown parent {parent_id}")
        if item["relation"] == "seed" and parent_id is not None:
            raise LearningError(f"seed hypothesis {item['id']} cannot have a parent")
        if item["relation"] != "seed" and parent_id is None:
            raise LearningError(f"derived hypothesis {item['id']} requires a parent")
    active = require_text_list(payload, "active_hypothesis_ids", "research_graph")
    if len(active) > MAX_ACTIVE_HYPOTHESES:
        raise LearningError(f"research_graph permits at most {MAX_ACTIVE_HYPOTHESES} active hypotheses")
    for hypothesis_id in active:
        if hypothesis_id not in by_id or by_id[hypothesis_id]["status"] != "active":
            raise LearningError(f"active hypothesis {hypothesis_id} is missing or not active")
    declared_active = {item["id"] for item in records if item["status"] == "active"}
    if set(active) != declared_active:
        raise LearningError("active_hypothesis_ids does not match hypothesis statuses")
    claim_id = payload.get("claim_hypothesis_id")
    if claim_id is not None:
        if not isinstance(claim_id, str) or claim_id not in by_id:
            raise LearningError("research_graph.claim_hypothesis_id is invalid")
        if claim_id not in active:
            raise LearningError("the frozen claim hypothesis must remain active")
        require_text(payload, "claim_frozen_at", "research_graph")
    elif payload.get("claim_frozen_at") is not None:
        raise LearningError("claim_frozen_at requires claim_hypothesis_id")
    require_text(payload, "updated_at", "research_graph")
    return payload


def seed_graph(
    portfolio: dict[str, Any],
    *,
    mission_sha256: str,
    route_sha256: str,
    now: str,
    adopt_current_claim: bool,
) -> dict[str, Any]:
    hypotheses = []
    for candidate in portfolio["candidates"]:
        if candidate["status"] == "eliminated":
            status = "eliminated"
        elif candidate["status"] == "active":
            status = "active"
        else:
            status = "backup"
        candidate_id = candidate["id"]
        hypotheses.append(
            {
                "id": candidate_id,
                "candidate_id": candidate_id,
                "version": 1,
                "parent_id": None,
                "relation": "seed",
                "status": status,
                "origin_route_sha256": route_sha256,
                "origin_finding_ids": [],
                "observation": candidate["observation"],
                "causal_hypothesis": candidate["causal_hypothesis"],
                "mechanism": candidate["mechanism"],
                "predictions": [candidate["predicted_signature"]],
                "falsifiers": [candidate["falsifier"]],
                "assumptions": [
                    {
                        "id": f"{candidate_id[:59]}-core",
                        "text": candidate["causal_hypothesis"],
                        "status": "untested",
                    }
                ],
                "created_at": now,
            }
        )
    active_id = portfolio["active_candidate_id"]
    graph = {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "mission_sha256": mission_sha256,
        "route_sha256": route_sha256,
        "revision": 1,
        "active_hypothesis_ids": [active_id],
        "claim_hypothesis_id": active_id if adopt_current_claim else None,
        "claim_frozen_at": now if adopt_current_claim else None,
        "hypotheses": hypotheses,
        "updated_at": now,
    }
    return validate_graph(graph, mission_sha256=mission_sha256, route_sha256=route_sha256)


def review_required(interpretation: dict[str, Any]) -> bool:
    if interpretation.get("lane") != "scientific":
        return False
    if interpretation.get("materiality") == "nonmaterial":
        return False
    return bool(
        interpretation["validity"] == "valid"
        and (
            interpretation["outcome"] == "falsifies"
            or interpretation["next_action"]
            in {"refine", "branch", "pivot", "stop", "park", "kill"}
        )
    )


def validate_interpretation(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise LearningError("interpretation must be an object")
    if payload.get("schema_version") != LEDGER_SCHEMA_VERSION:
        raise LearningError(f"interpretation.schema_version must be {LEDGER_SCHEMA_VERSION}")
    require_id(payload, "finding_id", "interpretation")
    require_id(payload, "experiment_id", "interpretation")
    require_id(payload, "hypothesis_id", "interpretation")
    if payload.get("evidence_role") not in EVIDENCE_ROLES:
        raise LearningError("interpretation.evidence_role is invalid")
    validity = payload.get("validity")
    outcome = payload.get("outcome")
    action = payload.get("next_action")
    if validity not in VALIDITY_CLASSES:
        raise LearningError("interpretation.validity is invalid")
    if outcome not in OUTCOME_CLASSES:
        raise LearningError("interpretation.outcome is invalid")
    if action not in NEXT_ACTIONS:
        raise LearningError("interpretation.next_action is invalid")
    lane = payload.get("lane")
    if lane not in research_operating_model.LANES:
        raise LearningError("interpretation.lane is invalid")
    if payload.get("materiality") not in MATERIALITY_CLASSES:
        raise LearningError("interpretation.materiality is invalid")
    if payload.get("decision_scope") not in DECISION_SCOPES:
        raise LearningError("interpretation.decision_scope is invalid")
    if validity != "valid" and outcome != "not_scientific":
        raise LearningError("invalid or contaminated work must use outcome=not_scientific")
    if validity != "valid" and action not in {"repair", "stop"}:
        raise LearningError("invalid or contaminated work may only be repaired or stopped")
    if validity == "valid" and outcome == "not_scientific":
        raise LearningError("valid work cannot use outcome=not_scientific")
    if validity == "valid" and action == "repair":
        raise LearningError("valid scientific evidence cannot use next_action=repair")
    if validity != "valid" and action == "stop" and outcome != "not_scientific":
        raise LearningError("a technical stop must remain outcome=not_scientific")
    if outcome == "falsifies" and action not in {"refine", "branch", "pivot", "stop", "park", "kill"}:
        raise LearningError("falsifying evidence must refine, branch, pivot, park, kill, or stop")
    if action == "confirm" and (validity != "valid" or outcome != "supports"):
        raise LearningError("next_action=confirm requires valid supporting evidence")
    if lane == "protocol" and action not in {"continue", "protocol_refine", "narrow_scope", "stop"}:
        raise LearningError("protocol evidence may only continue, refine protocol, narrow scope, or stop")
    if lane == "infrastructure" and action not in {"continue", "repair", "stop"}:
        raise LearningError("infrastructure evidence may only continue, repair, or stop")
    if action in {"protocol_refine", "narrow_scope"} and lane != "protocol":
        raise LearningError(f"next_action={action} requires lane=protocol")
    if action in {"refine", "branch", "pivot", "park", "kill", "confirm"} and lane != "scientific":
        raise LearningError(f"next_action={action} requires lane=scientific")
    if payload["materiality"] == "nonmaterial" and action in {
        "refine",
        "branch",
        "pivot",
        "park",
        "kill",
        "stop",
    }:
        raise LearningError("a nonmaterial interpretation cannot request a branch-level mutation")
    for key in ("expected", "observed", "surprise", "proposed_delta", "discriminating_test"):
        require_text(payload, key, "interpretation")
    require_text_list(payload, "alternative_explanations", "interpretation", allow_empty=outcome == "supports")
    if payload.get("information_gain") not in INFORMATION_GAIN:
        raise LearningError("interpretation.information_gain is invalid")
    updates = payload.get("assumption_updates")
    if not isinstance(updates, list):
        raise LearningError("interpretation.assumption_updates must be a list")
    for index, update in enumerate(updates):
        label = f"interpretation.assumption_updates[{index}]"
        if not isinstance(update, dict):
            raise LearningError(f"{label} must be an object")
        require_id(update, "assumption_id", label)
        if update.get("status") not in ASSUMPTION_STATES - {"untested"}:
            raise LearningError(f"{label}.status is invalid")
        require_text(update, "evidence", label)
    return payload


def validate_failure_review(payload: Any, interpretation: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise LearningError("failure_review must be an object")
    if payload.get("schema_version") != LEDGER_SCHEMA_VERSION:
        raise LearningError(f"failure_review.schema_version must be {LEDGER_SCHEMA_VERSION}")
    if require_id(payload, "finding_id", "failure_review") != interpretation["finding_id"]:
        raise LearningError("failure_review is bound to a different finding")
    if payload.get("decision") not in REVIEW_DECISIONS:
        raise LearningError("failure_review.decision is invalid")
    if payload.get("failure_class") not in FAILURE_CLASSES:
        raise LearningError("failure_review.failure_class is invalid")
    if payload.get("review_kind") not in research_operating_model.REVIEW_KINDS:
        raise LearningError("failure_review.review_kind is invalid")
    if payload.get("objection_severity") not in research_operating_model.OBJECTION_SEVERITIES:
        raise LearningError("failure_review.objection_severity is invalid")
    if payload.get("allowed_action") not in NEXT_ACTIONS:
        raise LearningError("failure_review.allowed_action is invalid")
    if not isinstance(payload.get("material_change"), bool):
        raise LearningError("failure_review.material_change must be boolean")
    for key in (
        "validity_assessment",
        "rationale",
        "affected_claim",
        "decision_changed",
        "required_test",
    ):
        require_text(payload, key, "failure_review")
    require_text_list(payload, "alternative_explanations", "failure_review")
    estimated_cost = payload.get("estimated_cost")
    if not isinstance(estimated_cost, dict):
        raise LearningError("failure_review.estimated_cost must be an object")
    for key in ("jobs", "hours", "su", "persistent_entries"):
        value = estimated_cost.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise LearningError(f"failure_review.estimated_cost.{key} must be non-negative")
    if payload["decision"] == "accept" and payload["allowed_action"] != interpretation["next_action"]:
        raise LearningError("an accepted review must preserve the proposed next action")
    if payload["decision"] == "reject" and payload["allowed_action"] in {
        "refine",
        "branch",
        "pivot",
        "park",
        "kill",
    }:
        raise LearningError("a rejected interpretation cannot authorize a hypothesis mutation")
    if payload["allowed_action"] in {"refine", "branch", "pivot", "park", "kill"} and not payload["material_change"]:
        raise LearningError("hypothesis mutation must declare material_change=true")
    if payload["objection_severity"] == "hard_invalidating" and payload["allowed_action"] == "confirm":
        raise LearningError("a hard-invalidating objection cannot authorize confirmation")
    return payload


def validate_child_spec(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise LearningError("child hypothesis must be an object")
    require_id(payload, "id", "child_hypothesis")
    require_id(payload, "candidate_id", "child_hypothesis")
    for key in ("observation", "causal_hypothesis", "mechanism"):
        require_text(payload, key, "child_hypothesis")
    require_text_list(payload, "predictions", "child_hypothesis")
    require_text_list(payload, "falsifiers", "child_hypothesis")
    validate_assumptions(payload.get("assumptions"), "child_hypothesis")
    require_text_list(payload, "origin_finding_ids", "child_hypothesis")
    return payload
