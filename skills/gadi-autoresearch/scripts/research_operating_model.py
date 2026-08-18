#!/usr/bin/env python3
"""Compact schemas for the autonomous research lab operating model."""

from __future__ import annotations

import re
from typing import Any


SCHEMA_VERSION = 1
PRELIMINARY_NOVELTY_SCHEMA_VERSION = 1
PROTOCOL_SCHEMA_VERSION = 1
DIRECTOR_DECISION_SCHEMA_VERSION = 1
SCOUT_SCHEMA_VERSION = 1
ANALYSIS_SCHEMA_VERSION = 1
CLAIM_GRAPH_SCHEMA_VERSION = 1

SAFE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
RESEARCH_MODES = {"signal_first", "balanced", "submission"}
LANES = {"scientific", "protocol", "infrastructure"}
MATURITY_LEVELS = ("seed", "scout", "pilot", "claim", "paper")
CLAIM_CEILINGS = {"exploratory", "pilot", "confirmatory", "submission"}
SCOUT_ROLES = ("literature", "systems", "cross_domain")
PROTOCOL_DECISIONS = {
    "authorize_exploratory",
    "authorize_pilot",
    "freeze_confirmatory",
    "narrow_scope",
    "supersede",
}
DIRECTOR_DECISIONS = {
    "continue",
    "promote",
    "park",
    "kill",
    "refine",
    "branch",
    "pivot",
    "narrow_scope",
    "protocol_refine",
    "confirm",
    "stop",
}
CORE_SIGNAL_STATES = {"none", "positive", "negative", "mixed"}
OBJECTION_SEVERITIES = {"hard_invalidating", "claim_scope", "future_work", "nonblocking"}
REVIEW_KINDS = {"mechanism", "integrity", "reproducibility"}
CLAIM_STATUSES = {"supported", "qualified", "falsified"}

DEFAULT_CIRCUIT_BREAKERS = {
    "hours_to_first_core_signal": 24,
    "max_cells_without_core_signal": 4,
    "max_protocol_diagnostics_per_decision": 2,
    "max_reviews_per_chain": 2,
    "technical_invalid_fraction": 0.50,
    "min_terminal_attempts_for_invalid_fraction": 6,
    "max_inode_growth_per_core_signal": 256,
}


class OperatingModelError(ValueError):
    pass


def require_text(payload: dict[str, Any], key: str, label: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise OperatingModelError(f"{label}.{key} must be non-empty text")
    return value.strip()


def require_id(payload: dict[str, Any], key: str, label: str) -> str:
    value = require_text(payload, key, label)
    if not SAFE_ID.fullmatch(value):
        raise OperatingModelError(f"{label}.{key} is not a safe identifier")
    return value


def require_text_list(
    payload: dict[str, Any],
    key: str,
    label: str,
    *,
    allow_empty: bool = False,
    maximum: int | None = None,
) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise OperatingModelError(f"{label}.{key} must be a list of non-empty strings")
    if not allow_empty and not value:
        raise OperatingModelError(f"{label}.{key} cannot be empty")
    if len(set(value)) != len(value):
        raise OperatingModelError(f"{label}.{key} contains duplicates")
    if maximum is not None and len(value) > maximum:
        raise OperatingModelError(f"{label}.{key} exceeds the limit of {maximum}")
    return [item.strip() for item in value]


def _nonnegative_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise OperatingModelError(f"{label} must be a non-negative number")
    return float(value)


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise OperatingModelError(f"{label} must be a positive integer")
    return value


def new_state(now: str, *, mode: str = "balanced") -> dict[str, Any]:
    if mode not in RESEARCH_MODES:
        raise OperatingModelError(f"unsupported research mode: {mode}")
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "created_at": now,
        "updated_at": now,
        "authority": {
            "director": "author",
            "single_writer": True,
            "critic_veto": ["hard_invalidating"],
            "max_reviews_per_chain": DEFAULT_CIRCUIT_BREAKERS["max_reviews_per_chain"],
        },
        "portfolio": {
            "branch_maturity": {},
            "concept_freeze": None,
            "last_director_decision_id": None,
            "director_decision_required": None,
            "active_budget": None,
        },
        "protocol": {
            "revision": 0,
            "protocol_id": None,
            "status": "unregistered",
            "claim_ceiling": "exploratory",
            "scope": [],
            "hard_blockers": [],
            "warnings": [],
            "evidence_ids": [],
            "updated_at": now,
            "history": [],
        },
        "infrastructure": {
            "cells": {},
            "cache_policy": {
                "environment_root": "/g/data/wa66/Xiangyu/enviroment_cache",
                "data_root": "/g/data/wa66/Xiangyu/Data",
                "expanded_root": "$PBS_JOBFS",
            },
        },
        "scouting": {
            "round": 0,
            "requested_at": None,
            "active_role": None,
            "reports": {},
        },
        "director_decisions": [],
        "review_chain": {
            "hypothesis_id": None,
            "count": 0,
            "finding_ids": [],
        },
        "signal": {
            "first_core_signal_at": None,
            "core_signal_finding_ids": [],
        },
        "circuit_breakers": dict(DEFAULT_CIRCUIT_BREAKERS),
    }


def ensure_state(value: Any, *, now: str, mode: str = "balanced") -> dict[str, Any]:
    if value is None:
        return new_state(now, mode=mode)
    if not isinstance(value, dict):
        raise OperatingModelError("research_os must be an object")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise OperatingModelError(f"research_os.schema_version must be {SCHEMA_VERSION}")
    if value.get("mode") not in RESEARCH_MODES:
        raise OperatingModelError("research_os.mode is invalid")
    value.setdefault("created_at", now)
    value.setdefault("updated_at", now)
    value.setdefault(
        "authority",
        {
            "director": "author",
            "single_writer": True,
            "critic_veto": ["hard_invalidating"],
            "max_reviews_per_chain": DEFAULT_CIRCUIT_BREAKERS["max_reviews_per_chain"],
        },
    )
    portfolio = value.setdefault("portfolio", {})
    portfolio.setdefault("branch_maturity", {})
    portfolio.setdefault("concept_freeze", None)
    portfolio.setdefault("last_director_decision_id", None)
    portfolio.setdefault("director_decision_required", None)
    portfolio.setdefault("active_budget", None)
    protocol = value.setdefault("protocol", {})
    for key, default in {
        "revision": 0,
        "protocol_id": None,
        "status": "unregistered",
        "claim_ceiling": "exploratory",
        "scope": [],
        "hard_blockers": [],
        "warnings": [],
        "evidence_ids": [],
        "updated_at": now,
        "history": [],
    }.items():
        protocol.setdefault(key, default)
    infrastructure = value.setdefault("infrastructure", {})
    infrastructure.setdefault("cells", {})
    infrastructure.setdefault(
        "cache_policy",
        {
            "environment_root": "/g/data/wa66/Xiangyu/enviroment_cache",
            "data_root": "/g/data/wa66/Xiangyu/Data",
            "expanded_root": "$PBS_JOBFS",
        },
    )
    scouting = value.setdefault("scouting", {})
    scouting.setdefault("round", 0)
    scouting.setdefault("requested_at", None)
    scouting.setdefault("active_role", None)
    scouting.setdefault("reports", {})
    value.setdefault("director_decisions", [])
    value.setdefault(
        "review_chain",
        {"hypothesis_id": None, "count": 0, "finding_ids": []},
    )
    value.setdefault(
        "signal",
        {"first_core_signal_at": None, "core_signal_finding_ids": []},
    )
    breakers = value.setdefault("circuit_breakers", {})
    for key, default in DEFAULT_CIRCUIT_BREAKERS.items():
        breakers.setdefault(key, default)
    return value


def validate_preliminary_novelty(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise OperatingModelError("preliminary_novelty must be an object")
    if payload.get("schema_version") != PRELIMINARY_NOVELTY_SCHEMA_VERSION:
        raise OperatingModelError(
            f"preliminary_novelty.schema_version must be {PRELIMINARY_NOVELTY_SCHEMA_VERSION}"
        )
    require_id(payload, "hypothesis_id", "preliminary_novelty")
    require_text(payload, "mechanism_without_brand", "preliminary_novelty")
    require_text_list(payload, "queries", "preliminary_novelty", maximum=12)
    sources = payload.get("primary_sources")
    if not isinstance(sources, list) or len(sources) < 2 or len(sources) > 8:
        raise OperatingModelError("preliminary_novelty.primary_sources must contain 2-8 checked sources")
    for index, source in enumerate(sources):
        label = f"preliminary_novelty.primary_sources[{index}]"
        if not isinstance(source, dict):
            raise OperatingModelError(f"{label} must be an object")
        for key in ("title", "url", "checked_locator", "mechanism_delta"):
            require_text(source, key, label)
        if not re.match(r"^https?://", source["url"]):
            raise OperatingModelError(f"{label}.url must be an HTTP(S) primary-source URL")
    require_text(payload, "nearest_work_delta", "preliminary_novelty")
    require_text(payload, "checked_at", "preliminary_novelty")
    if not isinstance(payload.get("exact_prior_found"), bool):
        raise OperatingModelError("preliminary_novelty.exact_prior_found must be boolean")
    if payload.get("decision") not in {"proceed_scout", "pivot"}:
        raise OperatingModelError("preliminary_novelty.decision is invalid")
    if payload["exact_prior_found"] != (payload["decision"] == "pivot"):
        raise OperatingModelError("an exact prior requires pivot; proceed_scout requires no exact prior")
    return payload


def validate_protocol_revision(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise OperatingModelError("protocol revision must be an object")
    if payload.get("schema_version") != PROTOCOL_SCHEMA_VERSION:
        raise OperatingModelError(f"protocol.schema_version must be {PROTOCOL_SCHEMA_VERSION}")
    require_id(payload, "protocol_id", "protocol")
    revision = _positive_int(payload.get("revision"), "protocol.revision")
    parent = payload.get("parent_revision")
    if isinstance(parent, bool) or not isinstance(parent, int) or parent < 0 or parent >= revision:
        raise OperatingModelError("protocol.parent_revision must be a smaller non-negative integer")
    if payload.get("decision") not in PROTOCOL_DECISIONS:
        raise OperatingModelError("protocol.decision is invalid")
    if payload.get("claim_ceiling") not in CLAIM_CEILINGS:
        raise OperatingModelError("protocol.claim_ceiling is invalid")
    fixed_ceiling = {
        "authorize_exploratory": "exploratory",
        "authorize_pilot": "pilot",
        "freeze_confirmatory": "confirmatory",
    }.get(payload["decision"])
    if fixed_ceiling and payload["claim_ceiling"] != fixed_ceiling:
        raise OperatingModelError(
            f"protocol decision {payload['decision']} requires claim_ceiling={fixed_ceiling}"
        )
    require_text_list(payload, "scope", "protocol", maximum=24)
    require_text_list(payload, "warnings", "protocol", allow_empty=True, maximum=24)
    require_text_list(payload, "evidence_ids", "protocol", allow_empty=True, maximum=32)
    require_text(payload, "rationale", "protocol")
    blockers = payload.get("hard_blockers")
    if not isinstance(blockers, list) or len(blockers) > 16:
        raise OperatingModelError("protocol.hard_blockers must be a list with at most 16 entries")
    blocker_ids: set[str] = set()
    for index, blocker in enumerate(blockers):
        label = f"protocol.hard_blockers[{index}]"
        if not isinstance(blocker, dict):
            raise OperatingModelError(f"{label} must be an object")
        blocker_id = require_id(blocker, "id", label)
        if blocker_id in blocker_ids:
            raise OperatingModelError("protocol.hard_blockers contains duplicate ids")
        blocker_ids.add(blocker_id)
        if blocker.get("severity") not in {"hard_invalidating", "claim_scope"}:
            raise OperatingModelError(f"{label}.severity is invalid")
        if blocker.get("status") not in {"open", "resolved", "out_of_scope"}:
            raise OperatingModelError(f"{label}.status is invalid")
        for key in ("affects", "evidence"):
            require_text(blocker, key, label)
    return payload


def validate_director_decision(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise OperatingModelError("director decision must be an object")
    if payload.get("schema_version") != DIRECTOR_DECISION_SCHEMA_VERSION:
        raise OperatingModelError(
            f"director_decision.schema_version must be {DIRECTOR_DECISION_SCHEMA_VERSION}"
        )
    require_id(payload, "decision_id", "director_decision")
    require_id(payload, "hypothesis_id", "director_decision")
    if payload.get("decision") not in DIRECTOR_DECISIONS:
        raise OperatingModelError("director_decision.decision is invalid")
    before = payload.get("maturity_before")
    after = payload.get("maturity_after")
    if before not in MATURITY_LEVELS or after not in MATURITY_LEVELS:
        raise OperatingModelError("director_decision maturity is invalid")
    before_index = MATURITY_LEVELS.index(before)
    after_index = MATURITY_LEVELS.index(after)
    if after_index > before_index + 1:
        raise OperatingModelError("a director decision may promote at most one maturity level")
    if payload["decision"] == "promote" and after_index != before_index + 1:
        raise OperatingModelError("decision=promote must advance exactly one maturity level")
    if payload["decision"] != "promote" and after_index > before_index:
        raise OperatingModelError("only decision=promote may advance maturity")
    require_text_list(payload, "finding_ids", "director_decision", allow_empty=True, maximum=16)
    require_text_list(payload, "critic_inputs", "director_decision", allow_empty=True, maximum=8)
    for key in ("question", "rationale", "next_question"):
        require_text(payload, key, "director_decision")
    if payload.get("core_signal") not in CORE_SIGNAL_STATES:
        raise OperatingModelError("director_decision.core_signal is invalid")
    budget = payload.get("next_budget")
    if not isinstance(budget, dict):
        raise OperatingModelError("director_decision.next_budget must be an object")
    _positive_int(budget.get("max_jobs"), "director_decision.next_budget.max_jobs")
    _nonnegative_number(budget.get("max_su"), "director_decision.next_budget.max_su")
    _positive_int(budget.get("max_turns"), "director_decision.next_budget.max_turns")
    diagnostics = budget.get("max_protocol_diagnostics")
    if isinstance(diagnostics, bool) or not isinstance(diagnostics, int) or diagnostics < 0 or diagnostics > 2:
        raise OperatingModelError(
            "director_decision.next_budget.max_protocol_diagnostics must be 0, 1, or 2"
        )
    return payload


def validate_scout_report(payload: Any, *, expected_role: str, expected_round: int) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise OperatingModelError("scout report must be an object")
    if payload.get("schema_version") != SCOUT_SCHEMA_VERSION:
        raise OperatingModelError(f"scout.schema_version must be {SCOUT_SCHEMA_VERSION}")
    if payload.get("role") != expected_role or expected_role not in SCOUT_ROLES:
        raise OperatingModelError("scout.role does not match the controller assignment")
    if payload.get("round") != expected_round:
        raise OperatingModelError("scout.round does not match the active scouting round")
    require_text(payload, "territory_summary", "scout")
    opportunities = payload.get("opportunities")
    if not isinstance(opportunities, list) or not 1 <= len(opportunities) <= 5:
        raise OperatingModelError("scout.opportunities must contain 1-5 opportunities")
    ids: set[str] = set()
    for index, opportunity in enumerate(opportunities):
        label = f"scout.opportunities[{index}]"
        if not isinstance(opportunity, dict):
            raise OperatingModelError(f"{label} must be an object")
        opportunity_id = require_id(opportunity, "id", label)
        if opportunity_id in ids:
            raise OperatingModelError("scout opportunity ids must be unique")
        ids.add(opportunity_id)
        for key in ("observation", "causal_opportunity", "differentiating_test", "nearest_work_delta"):
            require_text(opportunity, key, label)
        require_text_list(opportunity, "closest_prior_queries", label, maximum=8)
        cost = opportunity.get("estimated_cost")
        if not isinstance(cost, dict):
            raise OperatingModelError(f"{label}.estimated_cost must be an object")
        _positive_int(cost.get("jobs"), f"{label}.estimated_cost.jobs")
        _nonnegative_number(cost.get("su"), f"{label}.estimated_cost.su")
        _nonnegative_number(cost.get("hours"), f"{label}.estimated_cost.hours")
    return payload


def validate_independent_analysis(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise OperatingModelError("independent analysis must be an object")
    if payload.get("schema_version") != ANALYSIS_SCHEMA_VERSION:
        raise OperatingModelError(f"analysis.schema_version must be {ANALYSIS_SCHEMA_VERSION}")
    require_id(payload, "experiment_id", "analysis")
    require_id(payload, "hypothesis_id", "analysis")
    if payload.get("validity") not in {"valid", "technical_invalid", "contaminated"}:
        raise OperatingModelError("analysis.validity is invalid")
    if payload.get("likely_outcome") not in {
        "supports",
        "falsifies",
        "qualifies",
        "unexpected",
        "inconclusive",
        "not_scientific",
    }:
        raise OperatingModelError("analysis.likely_outcome is invalid")
    if payload.get("recommended_lane") not in LANES:
        raise OperatingModelError("analysis.recommended_lane is invalid")
    if payload["validity"] != "valid" and payload["likely_outcome"] != "not_scientific":
        raise OperatingModelError("invalid or contaminated analysis must use likely_outcome=not_scientific")
    if payload["validity"] == "valid" and payload["likely_outcome"] == "not_scientific":
        raise OperatingModelError("valid analysis cannot use likely_outcome=not_scientific")
    if payload["validity"] == "technical_invalid" and payload["recommended_lane"] != "infrastructure":
        raise OperatingModelError("technical-invalid analysis must recommend the infrastructure lane")
    for key in ("observed", "validity_rationale", "causal_assessment", "decision_relevance"):
        require_text(payload, key, "analysis")
    require_text_list(payload, "alternative_explanations", "analysis", allow_empty=True, maximum=12)
    require_text_list(payload, "threats", "analysis", allow_empty=True, maximum=12)
    return payload


def validate_claim_graph(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise OperatingModelError("claim_graph must be an object")
    if payload.get("schema_version") != CLAIM_GRAPH_SCHEMA_VERSION:
        raise OperatingModelError(
            f"claim_graph.schema_version must be {CLAIM_GRAPH_SCHEMA_VERSION}"
        )
    for key in (
        "mission_sha256",
        "route_sha256",
        "research_graph_sha256",
        "claim_hypothesis_id",
        "central_claim_id",
        "generated_at",
    ):
        require_text(payload, key, "claim_graph")
    for key in ("mission_sha256", "route_sha256", "research_graph_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", payload[key]):
            raise OperatingModelError(f"claim_graph.{key} must be a lowercase SHA-256 digest")
    claims = payload.get("claims")
    if not isinstance(claims, list) or not 1 <= len(claims) <= 32:
        raise OperatingModelError("claim_graph.claims must contain 1-32 claims")
    claim_ids: set[str] = set()
    for index, claim in enumerate(claims):
        label = f"claim_graph.claims[{index}]"
        if not isinstance(claim, dict):
            raise OperatingModelError(f"{label} must be an object")
        claim_id = require_id(claim, "id", label)
        if claim_id in claim_ids:
            raise OperatingModelError("claim_graph contains duplicate claim ids")
        claim_ids.add(claim_id)
        require_text(claim, "text", label)
        if claim.get("status") not in CLAIM_STATUSES:
            raise OperatingModelError(f"{label}.status is invalid")
        for key in (
            "evidence_finding_ids",
            "experiment_ids",
            "source_commits",
            "reproduction_experiment_ids",
        ):
            require_text_list(claim, key, label, allow_empty=key == "reproduction_experiment_ids")
        for commit in claim["source_commits"]:
            if not re.fullmatch(r"[0-9a-f]{40,64}", commit):
                raise OperatingModelError(f"{label}.source_commits contains an invalid Git digest")
        revisions = claim.get("protocol_revisions")
        if (
            not isinstance(revisions, list)
            or not revisions
            or any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in revisions)
            or len(set(revisions)) != len(revisions)
        ):
            raise OperatingModelError(
                f"{label}.protocol_revisions must be unique non-negative integers"
            )
        for key in ("assumptions", "limitations"):
            require_text_list(claim, key, label, allow_empty=True, maximum=24)
        sources = claim.get("primary_sources")
        if not isinstance(sources, list) or not sources or len(sources) > 24:
            raise OperatingModelError(f"{label}.primary_sources must contain 1-24 checked sources")
        for source_index, source in enumerate(sources):
            source_label = f"{label}.primary_sources[{source_index}]"
            if not isinstance(source, dict):
                raise OperatingModelError(f"{source_label} must be an object")
            for key in ("title", "url", "checked_locator", "supports"):
                require_text(source, key, source_label)
            if not re.match(r"^https?://", source["url"]):
                raise OperatingModelError(f"{source_label}.url must be HTTP(S)")
    if payload["central_claim_id"] not in claim_ids:
        raise OperatingModelError("claim_graph.central_claim_id is not present in claims")
    return payload
