#!/usr/bin/env python3
"""Validate a Gadi PBS script, inode-safety policy, and estimated SU charge."""

from __future__ import annotations

import argparse
import json
import math
import re
import shlex
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
LIMITS_PATH = SKILL_ROOT / "references" / "queue-limits.json"
CODEX_ROOT = "/g/data/wa66/Xiangyu/.codex"
PERSISTENT_ROOT = "/g/data/wa66/Xiangyu"
SKILL_ROOT_PATH = f"{CODEX_ROOT}/skills/run-on-gadi/"
AUTHORIZED_PROJECTS = {"wa66", "ey69", "po67", "iv96"}


def parse_size_gb(value: str) -> float:
    match = re.fullmatch(r"(?i)\s*([0-9]+(?:\.[0-9]+)?)\s*([kmgt]i?b?|b)?\s*", value)
    if not match:
        raise ValueError(f"invalid size: {value}")
    number = float(match.group(1))
    unit = (match.group(2) or "b").lower()
    factors = {
        "b": 1 / 1024**3,
        "k": 1 / 1024**2,
        "kb": 1 / 1024**2,
        "kib": 1 / 1024**2,
        "m": 1 / 1024,
        "mb": 1 / 1024,
        "mib": 1 / 1024,
        "g": 1,
        "gb": 1,
        "gib": 1,
        "t": 1024,
        "tb": 1024,
        "tib": 1024,
    }
    return number * factors[unit]


def parse_walltime_hours(value: str) -> float:
    parts = value.split(":")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError(f"walltime must be HH:MM:SS, got {value}")
    hours, minutes, seconds = map(int, parts)
    if minutes >= 60 or seconds >= 60:
        raise ValueError(f"invalid walltime: {value}")
    return hours + minutes / 60 + seconds / 3600


def parse_directives(text: str) -> tuple[dict[str, str], list[str]]:
    values: dict[str, str] = {}
    errors: list[str] = []
    saw_command = False
    for line_number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if line_number == 1 and stripped.startswith("#!"):
            continue
        if stripped.startswith("#PBS"):
            if saw_command:
                errors.append(f"line {line_number}: #PBS directive appears after shell commands")
            try:
                tokens = shlex.split(stripped[len("#PBS") :].strip())
            except ValueError as exc:
                errors.append(f"line {line_number}: cannot parse directive: {exc}")
                continue
            if not tokens:
                continue
            if tokens[0] in {"-P", "-q", "-N", "-o", "-e", "-j"} and len(tokens) >= 2:
                values[tokens[0][1:]] = tokens[1]
            elif tokens[0] == "-l" and len(tokens) >= 2:
                for item in tokens[1].split(","):
                    if "=" in item:
                        key, value = item.split("=", 1)
                        values[key.strip()] = value.strip()
                    else:
                        values[item.strip()] = "true"
            continue
        if stripped and not stripped.startswith("#"):
            saw_command = True
    return values, errors


def ncpus_valid(ncpus: int, rule: dict[str, object]) -> bool:
    if ncpus > int(rule["max"]):
        return False
    if "values" in rule:
        return ncpus in rule["values"]
    if "multiple" in rule:
        return ncpus % int(rule["multiple"]) == 0
    if "partial_values" in rule:
        return ncpus in rule["partial_values"] or (
            ncpus > max(rule["partial_values"])
            and ncpus % int(rule["full_node_multiple"]) == 0
        )
    low, high = rule["partial_range"]
    return low <= ncpus <= high or (
        ncpus > high and ncpus % int(rule["full_node_multiple"]) == 0
    )


def allowed_walltime(ncpus: int, tiers: list[list[float]]) -> float | None:
    for low, high, hours in tiers:
        if int(low) <= ncpus <= int(high):
            return float(hours)
    return None


def path_policy_checks(text: str, errors: list[str], warnings: list[str]) -> None:
    codex_lines = [
        (idx, line)
        for idx, line in enumerate(text.splitlines(), 1)
        if CODEX_ROOT in line and not line.lstrip().startswith("#")
    ]
    for idx, line in codex_lines:
        remainder = line.replace(SKILL_ROOT_PATH, "")
        read_only_assignment = re.match(
            r"^\s*(?:export\s+)?(?:RUNNER|BUILDER|PACKER|SKILL_ROOT)\s*=",
            line,
        )
        read_only_invocation = re.match(r"^\s*(?:bash|python3?|source)\s+", line)
        if CODEX_ROOT in remainder or not (read_only_assignment or read_only_invocation):
            errors.append(
                f"line {idx}: only read-only run-on-gadi skill access is allowed under {CODEX_ROOT}"
            )

    cache_names = (
        "APPTAINER_CACHEDIR",
        "APPTAINER_TMPDIR",
        "CARGO_HOME",
        "CONDA_ENVS_PATH",
        "CONDA_PKGS_DIRS",
        "CUDA_CACHE_PATH",
        "HF_HOME",
        "HF_DATASETS_CACHE",
        "HUGGINGFACE_HUB_CACHE",
        "HOME",
        "JAX_COMPILATION_CACHE_DIR",
        "MPLCONFIGDIR",
        "NPM_CONFIG_CACHE",
        "NUMBA_CACHE_DIR",
        "PIP_CACHE_DIR",
        "RUSTUP_HOME",
        "SINGULARITY_CACHEDIR",
        "SINGULARITY_TMPDIR",
        "TRANSFORMERS_CACHE",
        "TORCH_HOME",
        "TORCH_EXTENSIONS_DIR",
        "TORCHINDUCTOR_CACHE_DIR",
        "TRITON_CACHE_DIR",
        "UV_CACHE_DIR",
        "WANDB_CACHE_DIR",
        "WANDB_DIR",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "TMPDIR",
    )

    assignment_values: dict[str, str] = {}
    for match in re.finditer(
        r"(?m)^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=\s*([^\n#]+)",
        text,
    ):
        assignment_values[match.group(1)] = match.group(2).strip().strip("\"'")

    variable_pattern = re.compile(r"\$(?:\{([A-Z][A-Z0-9_]*)\}|([A-Z][A-Z0-9_]*))")

    def expanded_assignment(name: str, seen: set[str] | None = None) -> str:
        seen = set() if seen is None else set(seen)
        if name in seen:
            return assignment_values.get(name, "")
        seen.add(name)
        value = assignment_values.get(name, "")

        def replace(match: re.Match[str]) -> str:
            referenced = match.group(1) or match.group(2)
            if referenced in assignment_values:
                return expanded_assignment(referenced, seen)
            return match.group(0)

        return variable_pattern.sub(replace, value)

    for name in cache_names:
        if name in assignment_values:
            value = expanded_assignment(name)
            if "PBS_JOBFS" not in value:
                errors.append(f"{name} must resolve under $PBS_JOBFS, got {assignment_values[name]}")

    transient_names = (
        "BUILD",
        "BUILD_DIR",
        "CONDA_PREFIX",
        "DOWNLOAD_DIR",
        "DOWNLOAD_ROOT",
        "ENV_PREFIX",
        "EXTRACT_DIR",
        "STAGE_DIR",
        "TEMP_DIR",
        "TMP_ROOT",
        "VIRTUAL_ENV",
    )
    for name in transient_names:
        if name in assignment_values:
            value = expanded_assignment(name)
            if "/g/data/" in value or "/scratch/" in value or "/home/" in value:
                errors.append(
                    f"{name} is transient but resolves to a persistent/shared filesystem: "
                    f"{assignment_values[name]}"
                )

    install_pattern = re.compile(
        r"\b(?:pip3?\s+install|python3?\s+-m\s+pip\s+install|"
        r"(?:conda|mamba|micromamba)\s+(?:create|install|env\s+create)|"
        r"uv\s+pip\s+install|python3?\s+-m\s+venv|npm\s+(?:install|ci)|yarn\s+install)\b"
    )
    network_pattern = re.compile(
        r"^\s*(?:wget|curl|git\s+clone|huggingface-cli\s+download|hf\s+download)\b",
        re.MULTILINE,
    )
    for idx, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if install_pattern.search(line):
            errors.append(
                f"line {idx}: do not install packages directly in a PBS workload; "
                "build an environment in jobfs with build_conda_sqsh.sh"
            )
        if network_pattern.search(line) and ("/g/data/" in line or "/scratch/" in line or "/home/" in line):
            errors.append(
                f"line {idx}: download into $PBS_JOBFS, validate, then publish a packed artifact"
            )

    risky_persistent_patterns = [
        (r"(?m)^\s*(?:conda\s+(?:create|env\s+create)|python\S*\s+-m\s+venv).*?/g/data/", "expanded environment in gdata"),
        (r"(?m)^\s*(?:conda\s+(?:create|env\s+create)|python\S*\s+-m\s+venv).*?/scratch/", "expanded environment in scratch"),
        (r"(?m)^\s*tar\s+[^\n]*\s-C\s+/g/data/", "archive extraction into gdata"),
        (r"(?m)^\s*tar\s+[^\n]*\s-C\s+/scratch/", "archive extraction into scratch"),
        (r"(?m)^\s*unzip\s+[^\n]*\s-d\s+/g/data/", "archive extraction into gdata"),
        (r"(?m)^\s*unzip\s+[^\n]*\s-d\s+/scratch/", "archive extraction into scratch"),
    ]
    for pattern, label in risky_persistent_patterns:
        if re.search(pattern, text):
            errors.append(f"inode-unsafe operation detected: {label}; use $PBS_JOBFS")

    if re.search(network_pattern, text):
        warnings.append("network/download command detected; queue must be copyq")
    if PERSISTENT_ROOT in text and "storage=gdata/wa66" not in text.replace(" ", ""):
        errors.append("script references /g/data/wa66/Xiangyu but does not request storage=gdata/wa66")


def lint(path: Path) -> tuple[list[str], list[str], dict[str, object]]:
    text = path.read_text(encoding="utf-8")
    limits = json.loads(LIMITS_PATH.read_text(encoding="utf-8"))
    directives, errors = parse_directives(text)
    warnings: list[str] = []
    summary: dict[str, object] = {"verified_at": limits["verified_at"]}

    for required in ("P", "q", "walltime", "ncpus", "mem", "jobfs", "wd", "o"):
        if required not in directives:
            errors.append(f"missing required PBS directive: {required}")
    if directives.get("j", "").lower() not in {"oe", "eo"} and "e" not in directives:
        errors.append("set '#PBS -j oe' or provide an explicit '#PBS -e' path")
    if "CHANGE_ME" in text:
        errors.append("template placeholder CHANGE_ME remains")
    if "set -euo pipefail" not in text:
        warnings.append("add 'set -euo pipefail' after PBS directives")

    queue_name = directives.get("q")
    queue = limits["queues"].get(queue_name)
    project = directives.get("P")
    if project and project not in AUTHORIZED_PROJECTS:
        errors.append(
            f"project {project!r} is not in this skill's authorised set; "
            "run probe_gadi.py and update the site profile if access changed"
        )
    if queue_name and queue_name.endswith("-exec"):
        errors.append("submit to the route queue, not an -exec queue")
    if queue_name and queue is None:
        warnings.append(f"queue {queue_name!r} is not in the dated local snapshot")

    path_policy_checks(text, errors, warnings)

    output_keys = ["o"]
    if directives.get("j", "").lower() not in {"oe", "eo"}:
        output_keys.append("e")
    for key in output_keys:
        value = directives.get(key)
        if not value:
            continue
        if "$" in value or "~" in value:
            errors.append(f"PBS -{key} path must be an explicit absolute path, got {value}")
            continue
        if not value.startswith("/"):
            errors.append(f"PBS -{key} path must be absolute so logs cannot fall back to HOME")
            continue
        if not value.startswith(f"{PERSISTENT_ROOT}/"):
            errors.append(f"PBS -{key} logs must be stored under {PERSISTENT_ROOT}, got {value}")
            continue
        protected = (
            value == CODEX_ROOT
            or value.startswith(f"{CODEX_ROOT}/")
            or value == f"{PERSISTENT_ROOT}/Data"
            or value.startswith(f"{PERSISTENT_ROOT}/Data/")
            or value == f"{PERSISTENT_ROOT}/enviroment_cache"
            or value.startswith(f"{PERSISTENT_ROOT}/enviroment_cache/")
        )
        if protected:
            errors.append(f"PBS -{key} log path uses a protected non-result location: {value}")
            continue
        parent = Path(value).parent
        if "CHANGE_ME" not in value and not parent.is_dir():
            warnings.append(f"create PBS -{key} log directory before qsub: {parent}")

    storage = directives.get("storage", "").replace(" ", "")
    for mounted_project in sorted(set(re.findall(r"/g/data/([a-z][a-z0-9]*)", text))):
        if f"gdata/{mounted_project}" not in storage:
            errors.append(
                f"script references /g/data/{mounted_project} but storage does not include "
                f"gdata/{mounted_project}"
            )
    for scratch_project in sorted(set(re.findall(r"/scratch/([a-z][a-z0-9]*)", text))):
        if scratch_project != project and f"scratch/{scratch_project}" not in storage:
            errors.append(
                f"script references other-project scratch/{scratch_project} without a storage mount"
            )

    ncpus = ngpus = None
    mem_gb = jobfs_gb = walltime_hours = None
    try:
        if "ncpus" in directives:
            ncpus = int(directives["ncpus"])
        if "ngpus" in directives:
            ngpus = int(directives["ngpus"])
        if "mem" in directives:
            mem_gb = parse_size_gb(directives["mem"])
        if "jobfs" in directives:
            jobfs_gb = parse_size_gb(directives["jobfs"])
        if "walltime" in directives:
            walltime_hours = parse_walltime_hours(directives["walltime"])
    except ValueError as exc:
        errors.append(str(exc))

    if queue and ncpus is not None:
        if not ncpus_valid(ncpus, queue["ncpus_rule"]):
            errors.append(f"ncpus={ncpus} is invalid for {queue_name} snapshot")
        max_hours = allowed_walltime(ncpus, queue["walltime_tiers"])
        if max_hours is None:
            errors.append(f"ncpus={ncpus} falls outside documented walltime tiers for {queue_name}")
        elif walltime_hours is not None and walltime_hours > max_hours + 1e-9:
            errors.append(
                f"walltime {walltime_hours:g}h exceeds {max_hours:g}h tier for {queue_name}/{ncpus} CPUs"
            )

        nodes = max(1, math.ceil(ncpus / queue["ncpus_per_node"]))
        if mem_gb is not None and mem_gb > queue["mem_gb_per_node"] * nodes + 1e-9:
            errors.append(f"mem={mem_gb:g}GB exceeds {queue_name} limit for {nodes} node(s)")
        if jobfs_gb is not None and jobfs_gb > queue["jobfs_gb_per_node"] * nodes + 1e-9:
            errors.append(f"jobfs={jobfs_gb:g}GB exceeds {queue_name} limit for {nodes} node(s)")

        if queue["kind"] == "gpu":
            if not ngpus or ngpus < 1:
                errors.append(f"{queue_name} requires an explicit positive ngpus")
            else:
                expected_cpu = ngpus * queue["ncpus_per_gpu"]
                if ncpus != expected_cpu:
                    warnings.append(
                        f"{queue_name} normally pairs {ngpus} GPU(s) with {expected_cpu} CPUs; requested {ncpus}"
                    )
        elif ngpus:
            errors.append(f"ngpus requested from non-GPU queue {queue_name}")

        if queue_name != "copyq" and any("network/download" in warning for warning in warnings):
            errors.append("network/download commands require copyq; standard compute queues have no internet")

        if mem_gb is not None and walltime_hours is not None:
            memory_equivalent = mem_gb / queue["mem_gb_per_node"] * queue["ncpus_per_node"]
            resource_units = max(float(ncpus), memory_equivalent)
            estimated_su = resource_units * queue["charge_su_per_resource_hour"] * walltime_hours
            summary.update(
                {
                    "queue": queue_name,
                    "project": directives.get("P"),
                    "ncpus": ncpus,
                    "ngpus": ngpus or 0,
                    "mem_gb": round(mem_gb, 3),
                    "jobfs_gb": round(jobfs_gb or 0, 3),
                    "walltime_hours": round(walltime_hours, 3),
                    "estimated_su": round(estimated_su, 2),
                }
            )
            if memory_equivalent > ncpus:
                warnings.append(
                    f"memory raises charged resource units from {ncpus} to about {memory_equivalent:.2f}"
                )

    return errors, warnings, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        errors, warnings, summary = lint(args.script)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({"errors": errors, "warnings": warnings, "summary": summary}, indent=2))
    else:
        print(f"PBS lint: {args.script}")
        for message in errors:
            print(f"ERROR: {message}")
        for message in warnings:
            print(f"WARNING: {message}")
        if summary:
            print("Summary: " + json.dumps(summary, sort_keys=True))
        print(f"Result: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
