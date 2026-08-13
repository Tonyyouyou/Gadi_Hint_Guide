#!/usr/bin/env python3
"""Validate and resolve composable autoresearch adapter packs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ADAPTER_SCHEMA_VERSION = 1
ADAPTER_KINDS = ("task", "model", "lever", "evidence", "constraint")
REQUIRED_ROUTE_KINDS = ("task", "model", "lever", "evidence")
HUMAN_EVALUATION_LEVELS = ("never", "conditional", "required")
SAFE_PACK_ID = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
SAFE_ADAPTER_ID = re.compile(r"^[a-z][a-z0-9-]{0,31}\.[a-z][a-z0-9-]{0,63}$")


class AdapterError(RuntimeError):
    pass


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def adapter_root() -> Path:
    return skill_root() / "adapters"


def canonical_json(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _text(payload: dict[str, Any], key: str, label: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AdapterError(f"{label}.{key} must be non-empty text")
    return value.strip()


def _string_list(payload: dict[str, Any], key: str, label: str, *, allow_empty: bool = True) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise AdapterError(f"{label}.{key} must be a list of non-empty strings")
    if not allow_empty and not value:
        raise AdapterError(f"{label}.{key} cannot be empty")
    if len(set(value)) != len(value):
        raise AdapterError(f"{label}.{key} contains duplicates")
    return value


def _validate_reference(value: str, label: str) -> str:
    relative = value.split("#", 1)[0]
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or not relative.startswith("references/"):
        raise AdapterError(f"{label} must point below references/")
    target = skill_root() / path
    if not target.is_file():
        raise AdapterError(f"{label} does not exist: {target}")
    return value


def validate_pack(payload: Any, source: Path) -> dict[str, Any]:
    label = f"adapter pack {source}"
    if not isinstance(payload, dict):
        raise AdapterError(f"{label} must be a JSON object")
    if payload.get("schema_version") != ADAPTER_SCHEMA_VERSION:
        raise AdapterError(f"{label}.schema_version must be {ADAPTER_SCHEMA_VERSION}")
    pack_id = _text(payload, "pack_id", label)
    if not SAFE_PACK_ID.fullmatch(pack_id):
        raise AdapterError(f"{label}.pack_id is unsafe: {pack_id}")
    _text(payload, "title", label)
    _text(payload, "description", label)
    _validate_reference(_text(payload, "reference", label), f"{label}.reference")
    adapters = payload.get("adapters")
    if not isinstance(adapters, list) or not adapters:
        raise AdapterError(f"{label}.adapters must be a non-empty list")
    seen: set[str] = set()
    for index, adapter in enumerate(adapters):
        adapter_label = f"{label}.adapters[{index}]"
        if not isinstance(adapter, dict):
            raise AdapterError(f"{adapter_label} must be an object")
        adapter_id = _text(adapter, "id", adapter_label)
        if not SAFE_ADAPTER_ID.fullmatch(adapter_id) or not adapter_id.startswith(f"{pack_id}."):
            raise AdapterError(f"{adapter_label}.id must use the {pack_id}. prefix")
        if adapter_id in seen:
            raise AdapterError(f"duplicate adapter id in {label}: {adapter_id}")
        seen.add(adapter_id)
        kind = _text(adapter, "kind", adapter_label)
        if kind not in ADAPTER_KINDS:
            raise AdapterError(f"{adapter_label}.kind must be one of {', '.join(ADAPTER_KINDS)}")
        _text(adapter, "title", adapter_label)
        _text(adapter, "description", adapter_label)
        _validate_reference(_text(adapter, "reference", adapter_label), f"{adapter_label}.reference")
        _string_list(adapter, "required_evidence", adapter_label)
        _string_list(adapter, "discovery_questions", adapter_label, allow_empty=False)
        _string_list(adapter, "novelty_traps", adapter_label, allow_empty=False)
        human = _text(adapter, "human_evaluation", adapter_label)
        if human not in HUMAN_EVALUATION_LEVELS:
            raise AdapterError(
                f"{adapter_label}.human_evaluation must be one of {', '.join(HUMAN_EVALUATION_LEVELS)}"
            )
    defaults = _string_list(payload, "default_adapters", label)
    missing_defaults = sorted(set(defaults) - seen)
    if missing_defaults:
        raise AdapterError(f"{label}.default_adapters are unknown: {', '.join(missing_defaults)}")
    return payload


def load_registry(root: Path | None = None) -> dict[str, Any]:
    root = (root or adapter_root()).resolve()
    paths = sorted(root.glob("*.json"))
    if not paths:
        raise AdapterError(f"no adapter packs found below {root}")
    packs: dict[str, dict[str, Any]] = {}
    adapters: dict[str, dict[str, Any]] = {}
    canonical_packs: list[dict[str, Any]] = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AdapterError(f"invalid adapter JSON in {path}: {exc}") from exc
        pack = validate_pack(payload, path)
        pack_id = pack["pack_id"]
        if pack_id in packs:
            raise AdapterError(f"duplicate adapter pack id: {pack_id}")
        packs[pack_id] = pack
        canonical_packs.append(pack)
        for adapter in pack["adapters"]:
            adapter_id = adapter["id"]
            if adapter_id in adapters:
                raise AdapterError(f"duplicate adapter id across packs: {adapter_id}")
            adapters[adapter_id] = {**adapter, "pack_id": pack_id}
    if "core" not in packs:
        raise AdapterError("adapter registry requires a core pack")
    for adapter_id, adapter in adapters.items():
        for evidence_id in adapter["required_evidence"]:
            evidence = adapters.get(evidence_id)
            if not evidence:
                raise AdapterError(f"{adapter_id} requires unknown evidence adapter {evidence_id}")
            if evidence["kind"] != "evidence":
                raise AdapterError(f"{adapter_id} requires non-evidence adapter {evidence_id}")
    fingerprint = hashlib.sha256(canonical_json(canonical_packs)).hexdigest()
    return {"schema_version": ADAPTER_SCHEMA_VERSION, "sha256": fingerprint, "packs": packs, "adapters": adapters}


def resolve_bundle(
    registry: dict[str, Any],
    pack_ids: list[str],
    adapter_ids: list[str],
) -> dict[str, Any]:
    allowed_packs = list(dict.fromkeys(["core", *pack_ids]))
    unknown_packs = sorted(set(allowed_packs) - set(registry["packs"]))
    if unknown_packs:
        raise AdapterError(f"unknown domain packs: {', '.join(unknown_packs)}")
    selected = set(adapter_ids)
    for pack_id in allowed_packs:
        selected.update(registry["packs"][pack_id]["default_adapters"])
    unknown = sorted(selected - set(registry["adapters"]))
    if unknown:
        raise AdapterError(f"unknown adapters: {', '.join(unknown)}")
    outside = sorted(
        adapter_id
        for adapter_id in selected
        if registry["adapters"][adapter_id]["pack_id"] not in allowed_packs
    )
    if outside:
        raise AdapterError(f"adapters are outside the mission's domain packs: {', '.join(outside)}")
    by_kind = {
        kind: sorted(adapter_id for adapter_id in selected if registry["adapters"][adapter_id]["kind"] == kind)
        for kind in ADAPTER_KINDS
    }
    missing_kinds = [kind for kind in REQUIRED_ROUTE_KINDS if not by_kind[kind]]
    if missing_kinds:
        raise AdapterError(f"adapter route is missing required kinds: {', '.join(missing_kinds)}")
    missing_evidence: dict[str, list[str]] = {}
    for adapter_id in sorted(selected):
        required = sorted(set(registry["adapters"][adapter_id]["required_evidence"]) - selected)
        if required:
            missing_evidence[adapter_id] = required
    if missing_evidence:
        detail = "; ".join(f"{key} requires {', '.join(value)}" for key, value in missing_evidence.items())
        raise AdapterError(f"adapter route is missing required evidence: {detail}")
    human_levels = {
        registry["adapters"][adapter_id]["human_evaluation"] for adapter_id in selected
    }
    if "required" in human_levels:
        human_evaluation = "required"
    elif "conditional" in human_levels:
        human_evaluation = "conditional"
    else:
        human_evaluation = "never"
    references = sorted(
        {
            registry["packs"][pack_id]["reference"] for pack_id in allowed_packs
        }
        | {registry["adapters"][adapter_id]["reference"] for adapter_id in selected}
    )
    return {
        "packs": allowed_packs,
        "adapters": sorted(selected),
        "by_kind": by_kind,
        "human_evaluation": human_evaluation,
        "references": references,
        "registry_sha256": registry["sha256"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=adapter_root(), help="adapter-pack directory")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="validate every adapter pack and cross-pack reference")
    listing = sub.add_parser("list", help="list packs or adapters")
    listing.add_argument("--pack")
    listing.add_argument("--kind", choices=ADAPTER_KINDS)
    listing.add_argument("--json", action="store_true")
    show = sub.add_parser("show", help="show one adapter")
    show.add_argument("adapter_id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        registry = load_registry(args.root)
        if args.command == "validate":
            print(
                json.dumps(
                    {
                        "status": "valid",
                        "packs": sorted(registry["packs"]),
                        "adapter_count": len(registry["adapters"]),
                        "sha256": registry["sha256"],
                    },
                    indent=2,
                )
            )
        elif args.command == "list":
            values = [
                adapter
                for adapter in registry["adapters"].values()
                if (not args.pack or adapter["pack_id"] == args.pack)
                and (not args.kind or adapter["kind"] == args.kind)
            ]
            values.sort(key=lambda item: item["id"])
            if args.json:
                print(json.dumps(values, indent=2))
            else:
                for adapter in values:
                    print(f"{adapter['id']}\t{adapter['kind']}\t{adapter['title']}")
        else:
            adapter = registry["adapters"].get(args.adapter_id)
            if not adapter:
                raise AdapterError(f"unknown adapter: {args.adapter_id}")
            print(json.dumps(adapter, indent=2))
    except (AdapterError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
