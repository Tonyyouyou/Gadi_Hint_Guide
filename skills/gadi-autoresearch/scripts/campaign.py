#!/usr/bin/env python3
"""Inode-safe campaign state and PBS submission guard for Gadi autoresearch."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
import re
import shutil
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterator


SCHEMA_VERSION = 1
PHASES = (
    "intake",
    "literature",
    "ideas",
    "planning",
    "implementation",
    "sanity",
    "experiments",
    "review",
    "synthesis",
    "paper",
    "audit",
    "complete",
)
JOB_TERMINAL = {"completed", "failed", "cancelled", "failed_submission"}
JOB_ACTIVE = {
    "submitting",
    "queued",
    "held",
    "running",
    "finishing",
    "cancel_requested",
    "interactive_pending",
    "interactive_running",
}
REQUIRED_COMPLETION_ARTIFACTS = (
    "research_brief",
    "idea_report",
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
)
SAFE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
SAFE_JOB_ID = re.compile(r"^[0-9]+(?:\.[A-Za-z0-9_.-]+)?$")
AUTHORIZED_PROJECTS = {"wa66", "ey69", "po67", "iv96"}
CAMPAIGN_ENTRY_RESERVE = 5  # runs/, controller lock/current/previous log, atomic temp.
CONTROL_PYTHON = Path("/home/561/xz4320/miniconda3/bin/python3")
INTERACTIVE_PROFILES = {
    "normal": {"kind": "cpu", "ncpus": 4, "ngpus": 0},
    "gpuvolta": {"kind": "v100", "ncpus": 12, "ngpus": 1},
    "dgxa100": {"kind": "a100", "ncpus": 16, "ngpus": 1},
    "gpuhopper": {"kind": "h200", "ncpus": 12, "ngpus": 1},
}


class CampaignError(RuntimeError):
    pass


class OutputLimitError(CampaignError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CampaignError(f"invalid ISO-8601 timestamp: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def parse_walltime(value: str) -> int:
    match = re.fullmatch(r"(\d{2,3}):(\d{2}):(\d{2})", value)
    if not match:
        raise CampaignError("walltime must use HH:MM:SS")
    hours, minutes, seconds = (int(part) for part in match.groups())
    if minutes >= 60 or seconds >= 60:
        raise CampaignError(f"invalid walltime: {value}")
    total = hours * 3600 + minutes * 60 + seconds
    if total <= 0:
        raise CampaignError("walltime must be greater than zero")
    return total


def format_walltime(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def policy_roots() -> dict[str, Path]:
    test_root = os.environ.get("GADI_AUTORESEARCH_TEST_ROOT")
    if test_root:
        if os.environ.get("GADI_AUTORESEARCH_TESTING") != "1":
            raise CampaignError("GADI_AUTORESEARCH_TEST_ROOT is test-only")
        persistent = Path(test_root).resolve()
    else:
        persistent = Path("/g/data/wa66/Xiangyu")
    return {
        "persistent": persistent,
        "codex": persistent / ".codex",
        "environment": persistent / "enviroment_cache",
        "data": persistent / "Data",
    }


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def canonical(path: str | Path, *, strict: bool = False) -> Path:
    return Path(path).expanduser().resolve(strict=strict)


def validate_campaign_root(path: Path) -> None:
    roots = policy_roots()
    persistent = roots["persistent"]
    if not is_within(path, persistent) or path == persistent:
        raise CampaignError(f"campaign root must be below {persistent}")
    relative = path.relative_to(persistent)
    if len(relative.parts) < 2 or not relative.parts[0].startswith("Result"):
        raise CampaignError("campaign root must be below an existing Result* tree")
    result_tree = persistent / relative.parts[0]
    if not result_tree.is_dir():
        raise CampaignError(f"campaign root cannot create a new result family: {result_tree}")
    if is_within(path, roots["codex"]):
        raise CampaignError("campaign output can never be stored under .codex")
    if any(character.isspace() for character in str(path)):
        raise CampaignError("campaign root cannot contain whitespace because PBS log directives use it")


def validate_workspace(path: Path) -> None:
    roots = policy_roots()
    if not path.is_dir():
        raise CampaignError(f"workspace does not exist: {path}")
    if not is_within(path, roots["persistent"]):
        raise CampaignError(f"research workspaces must stay under {roots['persistent']}")
    if is_within(path, roots["codex"]):
        raise CampaignError("research workspaces cannot live under .codex")
    if is_within(path, roots["environment"]) or is_within(path, roots["data"]):
        raise CampaignError("workspace cannot live in the environment or data store")
    git_workspace_info(path)


def validate_environment(path: Path) -> None:
    root = policy_roots()["environment"]
    if not path.is_file() or path.suffix != ".sqsh" or not is_within(path, root):
        raise CampaignError(f"environment must be an existing .sqsh under {root}")


def file_identity(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {"size_bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def require_file_identity(path: Path, expected: dict[str, Any], label: str) -> None:
    if file_identity(path) != expected:
        raise CampaignError(f"{label} changed after experiment registration: {path}")


def storage_identity(path: Path) -> dict[str, Any]:
    if path.is_file():
        return {"kind": "file", **file_identity(path)}
    if not path.is_dir():
        raise CampaignError(f"registered storage input is not a regular file or directory: {path}")
    records: list[tuple[str, str, int, int]] = []
    stack = [path]
    while stack:
        current = stack.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                child = Path(entry.path)
                relative = str(child.relative_to(path))
                stat = entry.stat(follow_symlinks=False)
                if entry.is_symlink():
                    raise CampaignError(f"packed data inputs cannot contain symlinks: {child}")
                if entry.is_dir(follow_symlinks=False):
                    records.append((relative, "directory", 0, stat.st_mtime_ns))
                    stack.append(child)
                elif entry.is_file(follow_symlinks=False):
                    records.append((relative, "file", stat.st_size, stat.st_mtime_ns))
                else:
                    raise CampaignError(f"packed data inputs cannot contain special files: {child}")
                if len(records) > 1000:
                    raise CampaignError(f"data directory has more than 1000 entries; pack it first: {path}")
    payload = json.dumps(sorted(records), ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return {
        "kind": "directory",
        "entries": len(records),
        "metadata_sha256": hashlib.sha256(payload).hexdigest(),
    }


def require_storage_identity(path: Path, expected: dict[str, Any]) -> None:
    if storage_identity(path) != expected:
        raise CampaignError(f"data input changed after experiment registration: {path}")


def validate_data_path(path: Path) -> None:
    root = policy_roots()["data"]
    if not path.exists() or not is_within(path, root):
        raise CampaignError(f"data paths must exist under {root}: {path}")


def validate_packed_data(path: Path) -> None:
    validate_data_path(path)
    if path.is_dir() and count_entries(path, 1000) > 1000:
        raise CampaignError(f"data directory has more than 1000 entries; pack or coarsely shard it first: {path}")


def parse_projects(value: str) -> list[str]:
    projects = sorted({item.strip() for item in value.split(",") if item.strip()})
    if not projects:
        raise CampaignError("at least one charging project is required")
    unknown = set(projects) - AUTHORIZED_PROJECTS
    if unknown:
        raise CampaignError(f"unsupported project(s): {', '.join(sorted(unknown))}")
    return projects


def git_workspace_info(path: Path, *, require_clean: bool = False) -> dict[str, Any]:
    root_result = command_output(["git", "-C", str(path), "rev-parse", "--show-toplevel"])
    if root_result.returncode != 0:
        raise CampaignError("research workspace must be a Git repository with an initial commit")
    root = canonical(root_result.stdout.strip(), strict=True)
    if root != path:
        raise CampaignError(f"workspace must be the Git repository root, got {root}")
    commit_result = command_output(["git", "-C", str(path), "rev-parse", "HEAD"])
    if commit_result.returncode != 0:
        raise CampaignError("research workspace needs an initial Git commit")
    status_result = command_output(["git", "-C", str(path), "status", "--porcelain", "--untracked-files=normal"])
    if status_result.returncode != 0:
        raise CampaignError(f"cannot inspect workspace Git status: {status_result.stderr.strip()}")
    if require_clean and status_result.stdout.strip():
        raise CampaignError("commit or deliberately discard workspace changes before registering/running an experiment")
    submodule_result = command_output(["git", "-C", str(path), "ls-files", "--stage"])
    if submodule_result.returncode != 0:
        raise CampaignError(f"cannot inspect workspace index: {submodule_result.stderr.strip()}")
    if any(line.startswith("160000 ") for line in submodule_result.stdout.splitlines()):
        raise CampaignError("Git submodules are not supported by the jobfs source snapshot; vendor or package the dependency")
    return {
        "root": str(root),
        "commit": commit_result.stdout.strip(),
        "dirty": bool(status_result.stdout.strip()),
    }


def state_path(root: str | Path) -> Path:
    path = canonical(root)
    if path.name == "campaign.json":
        return path
    return path / "campaign.json"


def load_state(root: str | Path) -> dict[str, Any]:
    path = state_path(root)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CampaignError(f"campaign state not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CampaignError(f"invalid campaign JSON: {path}: {exc}") from exc
    if state.get("schema_version") != SCHEMA_VERSION:
        raise CampaignError(f"unsupported campaign schema: {state.get('schema_version')}")
    return state


def atomic_write(path: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now()
    payload = json.dumps(state, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=".campaign.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp_name)


@contextlib.contextmanager
def locked_state(root: str | Path) -> Iterator[dict[str, Any]]:
    path = state_path(root)
    lock_path = path.parent / "campaign.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        state = load_state(path)
        yield state
        atomic_write(path, state)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def add_history(state: dict[str, Any], event: str, **details: Any) -> None:
    history = state.setdefault("history", [])
    history.append({"at": utc_now(), "event": event, **details})
    if len(history) > 200:
        del history[:-200]


def count_entries(root: Path, stop_after: int | None = None) -> int:
    count = 0
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    count += 1
                    if stop_after is not None and count > stop_after:
                        return count
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
        except FileNotFoundError:
            continue
    return count


def queue_config() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[2] / "run-on-gadi" / "references" / "queue-limits.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))["queues"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as exc:
        raise CampaignError(f"cannot load run-on-gadi queue limits: {path}") from exc


def worker_cli_path() -> Path:
    installed = policy_roots()["codex"] / "skills" / "gadi-autoresearch" / "scripts" / "campaign.py"
    if installed.is_file():
        return installed
    return Path(__file__).resolve()


def control_python_path() -> Path:
    if os.environ.get("GADI_AUTORESEARCH_TESTING") == "1":
        return Path(sys.executable).resolve()
    return CONTROL_PYTHON


def estimate_su(resources: dict[str, Any]) -> float:
    config = queue_config().get(resources["queue"])
    if not config:
        raise CampaignError(f"unsupported queue: {resources['queue']}")
    memory_units = resources["mem_gb"] / config["mem_gb_per_node"] * config["ncpus_per_node"]
    billable_units = max(resources["ncpus"], memory_units)
    return round(billable_units * config["charge_su_per_resource_hour"] * resources["walltime_seconds"] / 3600, 2)


def validate_resources(resources: dict[str, Any], approval: dict[str, Any], mode: str) -> None:
    queues = queue_config()
    queue = queues.get(resources["queue"])
    if not queue:
        raise CampaignError(f"queue must be one of: {', '.join(sorted(queues))}")
    if resources["project"] not in approval["projects"]:
        raise CampaignError(f"project is outside the approved campaign: {resources['project']}")
    for name in ("ncpus", "mem_gb", "jobfs_gb"):
        if int(resources[name]) <= 0:
            raise CampaignError(f"{name} must be positive")
    ncpus = int(resources["ncpus"])
    rule = queue["ncpus_rule"]
    valid_ncpus = True
    if "values" in rule:
        valid_ncpus = ncpus in {int(value) for value in rule["values"]}
    elif "partial_values" in rule:
        valid_ncpus = ncpus in {int(value) for value in rule["partial_values"]} or (
            ncpus > max(int(value) for value in rule["partial_values"])
            and ncpus % int(rule["full_node_multiple"]) == 0
        )
    elif "partial_range" in rule:
        low, high = (int(value) for value in rule["partial_range"])
        valid_ncpus = low <= ncpus <= high or (ncpus > high and ncpus % int(rule["full_node_multiple"]) == 0)
    elif "multiple" in rule:
        valid_ncpus = ncpus % int(rule["multiple"]) == 0
    if not valid_ncpus or ncpus > int(rule["max"]):
        raise CampaignError(f"invalid ncpus={ncpus} for {resources['queue']}")
    ngpus = int(resources["ngpus"])
    if queue["kind"] == "gpu":
        if ngpus <= 0:
            raise CampaignError("GPU queues require ngpus > 0")
        if ngpus > int(approval["max_gpus_per_job"]):
            raise CampaignError("ngpus exceeds the approved campaign limit")
        minimum_cpus = ngpus * int(queue["ncpus_per_gpu"])
        if resources["ncpus"] < minimum_cpus:
            raise CampaignError(f"{resources['queue']} requires at least {minimum_cpus} CPUs for {ngpus} GPU(s)")
        nodes = max(
            math.ceil(ngpus / int(queue["gpus_per_node"])),
            math.ceil(ncpus / int(queue["ncpus_per_node"])),
        )
    else:
        if ngpus != 0:
            raise CampaignError(f"{resources['queue']} does not accept GPUs")
        nodes = max(1, math.ceil(resources["ncpus"] / int(queue["ncpus_per_node"])))
    if resources["mem_gb"] > float(queue["mem_gb_per_node"]) * nodes:
        raise CampaignError("memory request exceeds the queue limit for the inferred node count")
    if resources["jobfs_gb"] > float(queue["jobfs_gb_per_node"]) * nodes:
        raise CampaignError("jobfs request exceeds the queue limit for the inferred node count")
    walltime_limit = approval["max_interactive_walltime_seconds"] if mode == "interactive" else approval["max_batch_walltime_seconds"]
    if resources["walltime_seconds"] > int(walltime_limit):
        raise CampaignError(f"walltime exceeds approved {mode} limit {format_walltime(int(walltime_limit))}")
    queue_walltime_hours = None
    for low, high, hours in queue["walltime_tiers"]:
        if int(low) <= ncpus <= int(high):
            queue_walltime_hours = float(hours)
            break
    if queue_walltime_hours is None or resources["walltime_seconds"] > queue_walltime_hours * 3600:
        raise CampaignError(f"walltime exceeds the current {resources['queue']} queue tier")
    if mode == "interactive" and resources["walltime_seconds"] > 4 * 3600:
        raise CampaignError("interactive work is hard-capped at 04:00:00")


def attempt_committed_su(attempt: dict[str, Any]) -> float:
    if attempt.get("actual_su") is not None and attempt.get("actual_su_source") == "pbs":
        return float(attempt["actual_su"])
    if attempt.get("status") in JOB_ACTIVE | JOB_TERMINAL:
        return float(attempt["max_su"])
    return 0.0


def experiment_entry_reserve(experiment: dict[str, Any]) -> int:
    if experiment_status(experiment) in JOB_TERMINAL:
        return 0
    overhead = 1  # One persistent output object or result directory.
    if experiment.get("mode") in {"batch", "external"}:
        overhead += 1  # One combined PBS log for the next attempt.
    return int(experiment.get("expected_files", 0)) + overhead


def budget_summary(state: dict[str, Any]) -> dict[str, Any]:
    attempts = [attempt for exp in state["experiments"].values() for attempt in exp.get("attempts", [])]
    committed = round(sum(attempt_committed_su(attempt) for attempt in attempts), 2)
    active = sum(1 for attempt in attempts if attempt.get("status") in JOB_ACTIVE)
    submitted = len(attempts)
    expected_files = sum(experiment_entry_reserve(exp) for exp in state["experiments"].values())
    actual_entries = 1 + count_entries(
        canonical(state["root"]), int(state["approval"]["max_persistent_files"])
    )
    workspace_baseline = int(state.get("workspace_baseline_entries", 0))
    workspace_entries = count_entries(
        canonical(state["workspace"], strict=True),
        workspace_baseline + int(state["approval"]["max_persistent_files"]),
    )
    workspace_delta = max(0, workspace_entries - workspace_baseline)
    external_entries = sum(
        int(attempt.get("produced_entries") or 0)
        for experiment in state["experiments"].values()
        if experiment.get("mode") == "external"
        for attempt in experiment.get("attempts", [])
    )
    actual_persistent = actual_entries + workspace_delta + external_entries
    return {
        "max_su": float(state["approval"]["max_su"]),
        "committed_su": committed,
        "remaining_su": round(float(state["approval"]["max_su"]) - committed, 2),
        "jobs_submitted": submitted,
        "jobs_remaining": int(state["approval"]["max_jobs"]) - submitted,
        "active_jobs": active,
        "reserved_experiment_entries": expected_files,
        "actual_campaign_entries": actual_entries,
        "workspace_baseline_entries": workspace_baseline,
        "workspace_current_entries": workspace_entries,
        "workspace_entry_delta": workspace_delta,
        "published_external_entries": external_entries,
        "actual_persistent_entries": actual_persistent,
        "campaign_entry_reserve": CAMPAIGN_ENTRY_RESERVE,
        "projected_persistent_entries": actual_persistent + expected_files + CAMPAIGN_ENTRY_RESERVE,
        "max_persistent_files": int(state["approval"]["max_persistent_files"]),
    }


def control_after_terminal_attempt(state: dict[str, Any], reason: str) -> None:
    active = any(
        attempt.get("status") in JOB_ACTIVE
        for experiment in state["experiments"].values()
        for attempt in experiment.get("attempts", [])
    )
    state["control"].update(
        {
            "state": "waiting_pbs" if active else "needs_agent",
            "reason": "other tracked PBS work is still active" if active else reason,
        }
    )


def require_approved(
    state: dict[str, Any],
    capability: str | None = None,
    *,
    require_active: bool = True,
    allow_expired: bool = False,
) -> None:
    approval = state["approval"]
    if approval.get("state") != "approved":
        raise CampaignError("campaign is not approved")
    if require_active and state["status"] != "active":
        raise CampaignError(f"campaign is not active: {state['status']}")
    if not allow_expired and parse_time(approval["deadline"]) <= dt.datetime.now(dt.timezone.utc):
        raise CampaignError("campaign approval has expired")
    if capability and not approval.get(capability, False):
        raise CampaignError(f"campaign approval does not grant {capability}")


def command_output(command: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise CampaignError(f"command failed: {shlex.join(command)}: {exc}") from exc


def submitted_job_id(result: subprocess.CompletedProcess[str]) -> str | None:
    if result.returncode != 0 or not result.stdout.strip():
        return None
    candidate = result.stdout.strip().splitlines()[-1].strip()
    return candidate if SAFE_JOB_ID.fullmatch(candidate) else None


def parse_scaled(number: str, suffix: str) -> float:
    multiplier = {"": 1, "K": 1_000, "M": 1_000_000, "G": 1_000_000_000}
    return float(number) * multiplier[suffix.upper()]


def account_report(project: str) -> dict[str, Any]:
    result = command_output(["nci_account", "-P", project])
    if result.returncode != 0:
        raise CampaignError(f"nci_account failed for {project}: {result.stderr.strip()}")
    available = re.search(r"^\s*Avail:\s*([0-9.]+)\s*(K?SU)\s*$", result.stdout, re.MULTILINE)
    if not available:
        raise CampaignError(f"cannot parse available SU for {project}")
    available_su = float(available.group(1)) * (1000 if available.group(2) == "KSU" else 1)
    inode = None
    for line in result.stdout.splitlines():
        match = re.match(
            r"^gdata\S*\s+\S+\s+\S+\s+([0-9.]+)\s*([KMG]?)\s+\S+\s+\S+\s+([0-9.]+)\s*([KMG]?)\s*$",
            line.strip(),
        )
        if match:
            inode = {
                "used": int(parse_scaled(match.group(1), match.group(2))),
                "allocation": int(parse_scaled(match.group(3), match.group(4))),
            }
            inode["remaining"] = inode["allocation"] - inode["used"]
            break
    return {"project": project, "available_su": available_su, "gdata_inodes": inode}


def aris_reference() -> dict[str, Any]:
    repo = policy_roots()["persistent"] / "Auto-claude-code-research-in-sleep"
    reference: dict[str, Any] = {"path": str(repo), "exists": repo.is_dir(), "commit": None, "dirty": None}
    if not repo.is_dir():
        return reference
    commit = command_output(["git", "-C", str(repo), "rev-parse", "HEAD"])
    status = command_output(["git", "-C", str(repo), "status", "--porcelain"])
    if commit.returncode == 0:
        reference["commit"] = commit.stdout.strip()
    if status.returncode == 0:
        reference["dirty"] = bool(status.stdout.strip())
    return reference


def live_preflight(state: dict[str, Any], project: str | None = None) -> dict[str, Any]:
    groups_result = command_output(["id", "-nG"])
    groups = set(groups_result.stdout.split()) if groups_result.returncode == 0 else set()
    if "wa66" not in groups:
        raise CampaignError("current account is not a member of storage project wa66")
    projects = [project] if project else list(state["approval"]["projects"])
    reports = []
    for item in projects:
        if item not in groups:
            raise CampaignError(f"current account is not a member of {item}")
        reports.append(account_report(item))
    storage = account_report("wa66") if "wa66" not in projects else next(report for report in reports if report["project"] == "wa66")
    budget = budget_summary(state)
    if budget["actual_persistent_entries"] > budget["max_persistent_files"]:
        raise CampaignError("campaign persistent file limit has been exceeded")
    if budget["projected_persistent_entries"] > budget["max_persistent_files"]:
        raise CampaignError("campaign planned output and control reserve exceed the persistent-file envelope")
    inode = storage.get("gdata_inodes")
    if inode and inode["remaining"] <= max(1000, budget["max_persistent_files"] - budget["actual_persistent_entries"]):
        raise CampaignError("wa66 inode headroom is too small for the approved campaign")
    return {"projects": reports, "storage": storage, "budget": budget}


def ensure_submission_budget(state: dict[str, Any], experiment: dict[str, Any]) -> dict[str, Any]:
    summary = budget_summary(state)
    if summary["jobs_remaining"] <= 0:
        raise CampaignError("campaign job-count budget is exhausted")
    if summary["active_jobs"] >= int(state["approval"]["max_concurrent_jobs"]):
        raise CampaignError("campaign concurrent-job limit is reached")
    if summary["committed_su"] + float(experiment["max_su"]) > float(state["approval"]["max_su"]):
        raise CampaignError("submission would exceed the campaign SU envelope")
    projected_files = (
        summary["actual_persistent_entries"]
        + summary["reserved_experiment_entries"]
        + CAMPAIGN_ENTRY_RESERVE
    )
    if experiment["id"] not in state["experiments"] or experiment_status(experiment) in JOB_TERMINAL:
        projected_files += experiment_entry_reserve({**experiment, "status": "planned", "attempts": []})
    if projected_files > int(state["approval"]["max_persistent_files"]):
        raise CampaignError("submission would exceed the campaign persistent-file envelope")
    return summary


def build_state(args: argparse.Namespace, root: Path, workspace: Path) -> dict[str, Any]:
    deadline = parse_time(args.deadline)
    if deadline <= dt.datetime.now(dt.timezone.utc):
        raise CampaignError("deadline must be in the future")
    projects = parse_projects(args.projects)
    positive = {
        "max-su": args.max_su,
        "max-jobs": args.max_jobs,
        "max-concurrent": args.max_concurrent,
        "max-gpus": args.max_gpus,
        "max-files": args.max_files,
        "max-agent-turns": args.max_agent_turns,
    }
    for name, value in positive.items():
        if value <= 0:
            raise CampaignError(f"{name} must be positive")
    if args.max_files < CAMPAIGN_ENTRY_RESERVE + 3:
        raise CampaignError(f"max-files must be at least {CAMPAIGN_ENTRY_RESERVE + 3} for campaign control state")
    if args.max_concurrent > args.max_jobs:
        raise CampaignError("max-concurrent cannot exceed max-jobs")
    interactive_walltime = parse_walltime(args.max_interactive_walltime)
    batch_walltime = parse_walltime(args.max_batch_walltime)
    if interactive_walltime > 4 * 3600:
        raise CampaignError("max-interactive-walltime cannot exceed 04:00:00")
    environment = canonical(args.environment, strict=True) if args.environment else None
    if environment:
        validate_environment(environment)
    data_paths = [canonical(item, strict=True) for item in args.data]
    for path in data_paths:
        validate_packed_data(path)
    created = utc_now()
    workspace_git = git_workspace_info(workspace)
    workspace_entries = count_entries(workspace, 100_000)
    if workspace_entries > 100_000:
        raise CampaignError("research workspace is too large; create a small campaign-specific Git repository")
    return {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": args.campaign_id,
        "idea": args.idea,
        "venue": args.venue,
        "assurance": args.assurance,
        "root": str(root),
        "workspace": str(workspace),
        "workspace_git": workspace_git,
        "workspace_baseline_entries": workspace_entries,
        "created_at": created,
        "updated_at": created,
        "status": "draft",
        "phase": "intake",
        "storage": {
            "persistent_root": str(policy_roots()["persistent"]),
            "codex_root_policy": "codex-only",
            "environment": str(environment) if environment else None,
            "data": [str(path) for path in data_paths],
            "expanded_root": "$PBS_JOBFS",
            "storage_project": "wa66",
        },
        "workflow_reference": aris_reference(),
        "approval": {
            "state": "draft",
            "approved_at": None,
            "approved_by": None,
            "projects": projects,
            "max_su": args.max_su,
            "max_jobs": args.max_jobs,
            "max_concurrent_jobs": args.max_concurrent,
            "max_gpus_per_job": args.max_gpus,
            "max_interactive_walltime_seconds": interactive_walltime,
            "max_batch_walltime_seconds": batch_walltime,
            "max_persistent_files": args.max_files,
            "max_agent_turns": args.max_agent_turns,
            "deadline": deadline.isoformat().replace("+00:00", "Z"),
            "allow_auto_submit": False,
            "allow_storage_publish": False,
            "allow_interactive": False,
            "allow_auto_agent": False,
            "allow_auto_cancel": False,
        },
        "control": {
            "state": "waiting_human",
            "reason": "campaign envelope requires explicit approval",
            "thread_id": None,
            "agent_turns": 0,
            "last_agent_at": None,
            "last_pbs_poll_at": None,
            "wake_at": None,
        },
        "artifacts": {},
        "experiments": {},
        "history": [{"at": created, "event": "campaign_initialized"}],
    }


def cmd_init(args: argparse.Namespace) -> None:
    if not SAFE_ID.fullmatch(args.campaign_id):
        raise CampaignError("campaign-id must start with a letter and contain only letters, digits, ._- ")
    root = canonical(args.root)
    validate_campaign_root(root)
    workspace = canonical(args.workspace, strict=True)
    validate_workspace(workspace)
    if is_within(root, workspace) or is_within(workspace, root):
        raise CampaignError("campaign root and research workspace must be separate, non-nested directories")
    if root.exists() and any(root.iterdir()):
        raise CampaignError(f"campaign root is not empty: {root}")
    root.mkdir(parents=True, exist_ok=True)
    state = build_state(args, root, workspace)
    atomic_write(root / "campaign.json", state)
    (root / "campaign.lock").touch(exist_ok=True)
    print(json.dumps({"created": str(root / "campaign.json"), "approval": state["approval"]}, indent=2))


def cmd_approve(args: argparse.Namespace) -> None:
    with locked_state(args.root) as state:
        if not args.by.strip():
            raise CampaignError("approver identity cannot be empty")
        replacing = state["approval"]["state"] == "approved"
        if replacing and not args.replace:
            raise CampaignError("campaign is already approved; use --replace after explicit reapproval")
        if args.replace and not replacing:
            raise CampaignError("--replace requires an existing approval")
        if replacing:
            active = [
                attempt.get("job_id") or exp_id
                for exp_id, exp in state["experiments"].items()
                for attempt in exp.get("attempts", [])
                if attempt.get("status") in JOB_ACTIVE
            ]
            if active:
                raise CampaignError("cannot replace an approval while jobs are active: " + ", ".join(active))
            deadline_expired = parse_time(state["approval"]["deadline"]) <= dt.datetime.now(dt.timezone.utc)
            if state["status"] not in {"paused", "stopped"} and state["control"]["state"] != "waiting_human" and not deadline_expired:
                raise CampaignError("pause the campaign or hand off to waiting_human before replacing its approval")
            previous_approval = dict(state["approval"])
        else:
            previous_approval = None
        approval = state["approval"]
        overrides = {
            "projects": parse_projects(args.projects) if args.projects else None,
            "max_su": args.max_su,
            "max_jobs": args.max_jobs,
            "max_concurrent_jobs": args.max_concurrent,
            "max_gpus_per_job": args.max_gpus,
            "max_interactive_walltime_seconds": parse_walltime(args.max_interactive_walltime) if args.max_interactive_walltime else None,
            "max_batch_walltime_seconds": parse_walltime(args.max_batch_walltime) if args.max_batch_walltime else None,
            "max_persistent_files": args.max_files,
            "max_agent_turns": args.max_agent_turns,
            "deadline": parse_time(args.deadline).isoformat().replace("+00:00", "Z") if args.deadline else None,
        }
        for key, value in overrides.items():
            if value is not None:
                approval[key] = value
        for key in ("max_su", "max_jobs", "max_concurrent_jobs", "max_gpus_per_job", "max_persistent_files", "max_agent_turns"):
            if float(approval[key]) <= 0:
                raise CampaignError(f"{key} must be positive")
        if int(approval["max_concurrent_jobs"]) > int(approval["max_jobs"]):
            raise CampaignError("max-concurrent cannot exceed max-jobs")
        if int(approval["max_persistent_files"]) < CAMPAIGN_ENTRY_RESERVE + 3:
            raise CampaignError(f"max-files must be at least {CAMPAIGN_ENTRY_RESERVE + 3} for campaign control state")
        if int(approval["max_interactive_walltime_seconds"]) > 4 * 3600:
            raise CampaignError("max-interactive-walltime cannot exceed 04:00:00")
        if parse_time(approval["deadline"]) <= dt.datetime.now(dt.timezone.utc):
            raise CampaignError("approval deadline must be in the future")
        if replacing:
            consumed = budget_summary(state)
            if float(approval["max_su"]) < consumed["committed_su"]:
                raise CampaignError("replacement max-su is below already committed SU")
            if int(approval["max_jobs"]) < consumed["jobs_submitted"]:
                raise CampaignError("replacement max-jobs is below already submitted attempts")
            if int(approval["max_concurrent_jobs"]) < consumed["active_jobs"]:
                raise CampaignError("replacement max-concurrent is below current active jobs")
            if int(approval["max_persistent_files"]) < consumed["projected_persistent_entries"]:
                raise CampaignError("replacement max-files is below current plus reserved campaign entries")
            if int(approval["max_agent_turns"]) < int(state["control"]["agent_turns"]):
                raise CampaignError("replacement max-agent-turns is below already used turns")
        approval.update(
            {
                "state": "approved",
                "approved_at": utc_now(),
                "approved_by": args.by,
                "allow_auto_submit": args.allow_auto_submit,
                "allow_storage_publish": args.allow_storage_publish,
                "allow_interactive": args.allow_interactive,
                "allow_auto_agent": args.allow_auto_agent,
                "allow_auto_cancel": args.allow_auto_cancel,
            }
        )
        state["status"] = "active"
        if not replacing:
            state["phase"] = "literature"
        state["control"].update({"state": "needs_agent", "reason": "campaign approved", "wake_at": None})
        add_history(
            state,
            "campaign_reapproved" if replacing else "campaign_approved",
            by=args.by,
            previous_approval=previous_approval,
            capabilities={
                key: approval[key]
                for key in (
                    "allow_auto_submit",
                    "allow_storage_publish",
                    "allow_interactive",
                    "allow_auto_agent",
                    "allow_auto_cancel",
                )
            },
        )
        print(json.dumps(approval, indent=2))


def cmd_storage_set(args: argparse.Namespace) -> None:
    with locked_state(args.root) as state:
        require_approved(state)
        if args.environment:
            image = canonical(args.environment, strict=True)
            validate_environment(image)
            state["storage"]["environment"] = str(image)
        for item in args.data:
            path = canonical(item, strict=True)
            validate_packed_data(path)
            if str(path) not in state["storage"]["data"]:
                state["storage"]["data"].append(str(path))
        add_history(state, "storage_updated", environment=state["storage"]["environment"], data=state["storage"]["data"])
        print(json.dumps(state["storage"], indent=2))


def cmd_status(args: argparse.Namespace) -> None:
    state = load_state(args.root)
    output = {
        "campaign_id": state["campaign_id"],
        "idea": state["idea"],
        "status": state["status"],
        "phase": state["phase"],
        "workflow_reference": state.get("workflow_reference"),
        "control": state["control"],
        "approval": state["approval"],
        "budget": budget_summary(state),
        "experiments": {
            key: {
                "stage": value["stage"],
                "mode": value["mode"],
                "status": value["status"],
                "source_commit": value.get("source_commit"),
                "image": value.get("image"),
                "max_su": value.get("max_su"),
                "expected_files": value.get("expected_files"),
                "attempts": value.get("attempts", []),
            }
            for key, value in state["experiments"].items()
        },
        "artifacts": state["artifacts"],
    }
    print(json.dumps(output, indent=2))


def cmd_preflight(args: argparse.Namespace) -> None:
    state = load_state(args.root)
    require_approved(state, require_active=False, allow_expired=True)
    report = live_preflight(state)
    print(json.dumps(report, indent=2))


def cmd_phase(args: argparse.Namespace) -> None:
    with locked_state(args.root) as state:
        require_approved(state)
        previous = state["phase"]
        if previous == "complete":
            raise CampaignError("completed campaign phases cannot be changed")
        if args.phase == "complete":
            raise CampaignError("use handoff --state complete so the completion audit runs")
        state["phase"] = args.phase
        add_history(state, "phase_changed", previous=previous, current=args.phase, reason=args.reason)
        print(f"{previous} -> {args.phase}")


def validate_artifact_path(state: dict[str, Any], path: Path) -> None:
    roots = policy_roots()
    if not path.exists():
        raise CampaignError(f"artifact does not exist: {path}")
    if is_within(path, roots["codex"]):
        raise CampaignError("research artifacts cannot be stored under .codex")
    campaign = canonical(state["root"])
    workspace = canonical(state["workspace"])
    if not is_within(path, campaign) and not is_within(path, workspace):
        raise CampaignError("artifact must be under the campaign root or research workspace")


def cmd_artifact(args: argparse.Namespace) -> None:
    if not SAFE_ID.fullmatch(args.name):
        raise CampaignError("artifact name must start with a letter and contain only letters, digits, ._- ")
    path = canonical(args.path, strict=True)
    with locked_state(args.root) as state:
        require_approved(state)
        validate_artifact_path(state, path)
        if args.name in REQUIRED_COMPLETION_ARTIFACTS:
            if not path.is_file():
                raise CampaignError(f"completion artifact must be a regular file: {args.name}: {path}")
            if args.assurance == "not-applicable":
                raise CampaignError(f"required completion artifact cannot be not-applicable: {args.name}")
        if args.name == "sanity":
            if not path.is_file() or path.suffix != ".json" or args.assurance != "deterministic":
                raise CampaignError("sanity evidence must be a deterministic JSON file")
            try:
                sanity = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise CampaignError(f"invalid sanity JSON: {exc}") from exc
            required = {
                "status",
                "source_commit",
                "image",
                "command",
                "device",
                "pbs_evidence",
                "result_marker",
                "produced_entries",
            }
            missing = sorted(required - set(sanity)) if isinstance(sanity, dict) else sorted(required)
            if missing or sanity.get("status") != "pass":
                raise CampaignError("sanity JSON is not a passing witness; missing/invalid: " + ", ".join(missing or ["status"]))
        state["artifacts"][args.name] = {
            "path": str(path),
            "recorded_at": utc_now(),
            "assurance": args.assurance,
            "size_bytes": path.stat().st_size if path.is_file() else None,
            "mtime_ns": path.stat().st_mtime_ns,
        }
        add_history(state, "artifact_recorded", name=args.name, path=str(path), assurance=args.assurance)
        print(json.dumps(state["artifacts"][args.name], indent=2))


def experiment_status(exp: dict[str, Any]) -> str:
    attempts = exp.get("attempts", [])
    return attempts[-1]["status"] if attempts else exp.get("status", "planned")


def validate_interactive_profile(resources: dict[str, Any]) -> dict[str, Any]:
    profile = INTERACTIVE_PROFILES.get(resources["queue"])
    if not profile:
        raise CampaignError(
            "interactive work supports only normal, gpuvolta, dgxa100, and gpuhopper"
        )
    if int(resources["ncpus"]) != profile["ncpus"] or int(resources["ngpus"]) != profile["ngpus"]:
        raise CampaignError(
            f"interactive {resources['queue']} uses the fixed debug profile "
            f"ncpus={profile['ncpus']}, ngpus={profile['ngpus']}"
        )
    return profile


def cmd_experiment_add(args: argparse.Namespace) -> None:
    if not SAFE_ID.fullmatch(args.id):
        raise CampaignError("experiment id must start with a letter and contain only letters, digits, ._- ")
    try:
        command = json.loads(args.command_json)
    except json.JSONDecodeError as exc:
        raise CampaignError(f"command-json must be a JSON array: {exc}") from exc
    if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
        raise CampaignError("command-json must be a non-empty JSON array of non-empty strings")
    if args.expected_files <= 0:
        raise CampaignError("expected-files must be positive")
    with locked_state(args.root) as state:
        require_approved(state)
        if args.id in state["experiments"]:
            raise CampaignError(f"experiment already exists: {args.id}")
        image_value = args.image or state["storage"].get("environment")
        if not image_value:
            raise CampaignError("set a campaign environment or pass --image")
        image = canonical(image_value, strict=True)
        validate_environment(image)
        image_fingerprint = file_identity(image)
        source = git_workspace_info(canonical(state["workspace"], strict=True), require_clean=True)
        data_fingerprints = {
            item: storage_identity(canonical(item, strict=True))
            for item in state["storage"].get("data", [])
        }
        resources = {
            "queue": args.queue,
            "project": args.project,
            "walltime_seconds": parse_walltime(args.walltime),
            "ncpus": args.ncpus,
            "ngpus": args.ngpus,
            "mem_gb": args.mem_gb,
            "jobfs_gb": args.jobfs_gb,
        }
        validate_resources(resources, state["approval"], args.mode)
        if args.mode == "interactive":
            validate_interactive_profile(resources)
        result_dir = canonical(state["root"]) / "runs" / args.id
        if result_dir.exists():
            raise CampaignError(f"experiment result path already exists: {result_dir}")
        success_path = result_dir / args.success_file
        if Path(args.success_file).is_absolute() or ".." in Path(args.success_file).parts:
            raise CampaignError("success-file must be a safe path relative to the experiment result directory")
        experiment = {
            "id": args.id,
            "stage": args.stage,
            "mode": args.mode,
            "status": "planned",
            "created_at": utc_now(),
            "command": command,
            "image": str(image),
            "image_fingerprint": image_fingerprint,
            "data_fingerprints": data_fingerprints,
            "source_commit": source["commit"],
            "source_history": [{"at": utc_now(), "commit": source["commit"], "reason": "experiment registered"}],
            "resources": resources,
            "max_su": estimate_su(resources),
            "expected_files": args.expected_files,
            "result_dir": str(result_dir),
            "success_file": str(success_path),
            "depends_on": args.depends_on,
            "attempts": [],
        }
        current_budget = budget_summary(state)
        new_overhead = 2 if args.mode == "batch" else 1
        projected = (
            current_budget["actual_persistent_entries"]
            + current_budget["reserved_experiment_entries"]
            + args.expected_files
            + new_overhead
            + CAMPAIGN_ENTRY_RESERVE
        )
        if projected > int(state["approval"]["max_persistent_files"]):
            raise CampaignError("experiment would exceed the campaign file envelope")
        state["experiments"][args.id] = experiment
        add_history(state, "experiment_added", experiment_id=args.id, max_su=experiment["max_su"], expected_files=args.expected_files)
        print(json.dumps(experiment, indent=2))


def require_dependencies(state: dict[str, Any], experiment: dict[str, Any]) -> None:
    for dependency in experiment.get("depends_on", []):
        if dependency not in state["experiments"]:
            raise CampaignError(f"unknown dependency: {dependency}")
        if experiment_status(state["experiments"][dependency]) != "completed":
            raise CampaignError(f"dependency is not complete: {dependency}")
    if experiment["stage"] not in {"sanity", "pilot"} and experiment["resources"]["ngpus"] > 0:
        if "sanity" not in state["artifacts"]:
            raise CampaignError("a recorded deterministic sanity artifact is required")


def require_registered_inputs(state: dict[str, Any], experiment: dict[str, Any]) -> None:
    image = canonical(experiment["image"], strict=True)
    validate_environment(image)
    require_file_identity(image, experiment["image_fingerprint"], "environment image")
    for value, expected in experiment.get("data_fingerprints", {}).items():
        data_path = canonical(value, strict=True)
        validate_packed_data(data_path)
        require_storage_identity(data_path, expected)
    commit = experiment.get("source_commit", "")
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", commit):
        raise CampaignError("experiment has no valid registered source commit")
    workspace = canonical(state["workspace"], strict=True)
    result = command_output(["git", "-C", str(workspace), "cat-file", "-e", f"{commit}^{{commit}}"])
    if result.returncode != 0:
        raise CampaignError(f"registered source commit is unavailable: {commit}")


def render_pbs(state: dict[str, Any], experiment: dict[str, Any], attempt_number: int) -> str:
    resources = experiment["resources"]
    root = canonical(state["root"])
    log_path = root / f"pbs-{experiment['id']}.a{attempt_number}.log"
    cli = worker_cli_path()
    python = control_python_path()
    if not python.is_file():
        raise CampaignError(f"modern control-plane Python is unavailable: {python}")
    template_path = Path(__file__).resolve().parents[1] / "assets" / "pbs" / "autoresearch-worker.pbs"
    template = template_path.read_text(encoding="utf-8")
    replacements = {
        "__PROJECT__": resources["project"],
        "__QUEUE__": resources["queue"],
        "__JOB_NAME__": ("ar-" + experiment["id"])[:15],
        "__NCPUS__": str(resources["ncpus"]),
        "__NGPUS_DIRECTIVE__": f"#PBS -l ngpus={resources['ngpus']}" if resources["ngpus"] else "",
        "__MEM_GB__": str(resources["mem_gb"]),
        "__JOBFS_GB__": str(resources["jobfs_gb"]),
        "__WALLTIME__": format_walltime(resources["walltime_seconds"]),
        "__LOG_PATH__": str(log_path),
        "__CAMPAIGN_ROOT__": shlex.quote(str(root)),
        "__EXPERIMENT_ID__": shlex.quote(experiment["id"]),
        "__CAMPAIGN_CLI__": shlex.quote(str(cli)),
        "__CONTROL_PYTHON__": shlex.quote(str(python)),
    }
    for token, value in replacements.items():
        template = template.replace(token, value)
    if "__" in template:
        raise CampaignError("unresolved token in PBS worker template")
    return template


def lint_script(script: str) -> dict[str, Any]:
    linter = Path(__file__).resolve().parents[2] / "run-on-gadi" / "scripts" / "lint_pbs.py"
    with tempfile.NamedTemporaryFile("w", suffix=".pbs", prefix="gadi-autoresearch-", dir="/tmp", delete=False, encoding="utf-8") as handle:
        handle.write(script)
        path = Path(handle.name)
    try:
        result = command_output([sys.executable, str(linter), "--json", str(path)])
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise CampaignError(f"PBS linter returned invalid output: {result.stdout} {result.stderr}") from exc
        if result.returncode != 0 or report.get("errors"):
            raise CampaignError("PBS validation failed: " + "; ".join(report.get("errors", [result.stderr.strip()])))
        return report
    finally:
        path.unlink(missing_ok=True)


def cmd_submit(args: argparse.Namespace) -> None:
    state = load_state(args.root)
    require_approved(state, "allow_auto_submit" if args.execute else None)
    experiment = state["experiments"].get(args.id)
    if not experiment:
        raise CampaignError(f"unknown experiment: {args.id}")
    if experiment["mode"] != "batch":
        raise CampaignError("use the interactive command for interactive experiments")
    if experiment_status(experiment) not in {"planned", "failed", "failed_submission", "cancelled"}:
        raise CampaignError(f"experiment cannot be submitted from status {experiment_status(experiment)}")
    require_dependencies(state, experiment)
    require_registered_inputs(state, experiment)
    validate_resources(experiment["resources"], state["approval"], "batch")
    ensure_submission_budget(state, experiment)
    preflight = live_preflight(state, experiment["resources"]["project"])
    project_report = preflight["projects"][0]
    if project_report["available_su"] < float(experiment["max_su"]):
        raise CampaignError("live project allocation is smaller than this job's maximum charge")
    attempt_number = len(experiment.get("attempts", [])) + 1
    script = render_pbs(state, experiment, attempt_number)
    lint_report = lint_script(script)
    preview = {
        "campaign": state["campaign_id"],
        "experiment": args.id,
        "attempt": attempt_number,
        "max_su": experiment["max_su"],
        "live_available_su": project_report["available_su"],
        "budget": preflight["budget"],
        "linter_warnings": lint_report.get("warnings", []),
        "pbs_script": script,
    }
    if not args.execute:
        print(json.dumps(preview, indent=2))
        return

    attempt = {
        "number": attempt_number,
        "status": "submitting",
        "job_id": None,
        "submitted_at": utc_now(),
        "finished_at": None,
        "exit_status": None,
        "max_su": experiment["max_su"],
        "actual_su": None,
        "pbs_script": script,
    }
    with locked_state(args.root) as current:
        require_approved(current, "allow_auto_submit")
        current_exp = current["experiments"][args.id]
        current_status = experiment_status(current_exp)
        if current_status not in {"planned", "failed", "failed_submission", "cancelled"}:
            raise CampaignError(f"experiment cannot be submitted from current status {current_status}")
        require_dependencies(current, current_exp)
        require_registered_inputs(current, current_exp)
        validate_resources(current_exp["resources"], current["approval"], "batch")
        ensure_submission_budget(current, current_exp)
        current_exp["attempts"].append(attempt)
        current_exp["status"] = "submitting"
        add_history(current, "submission_started", experiment_id=args.id, attempt=attempt_number)

    with tempfile.NamedTemporaryFile("w", suffix=".pbs", prefix="gadi-autoresearch-", dir="/tmp", delete=False, encoding="utf-8") as handle:
        handle.write(script)
        script_path = Path(handle.name)
    try:
        result = command_output(["qsub", str(script_path)], timeout=60)
    finally:
        script_path.unlink(missing_ok=True)
    job_id = submitted_job_id(result)
    with locked_state(args.root) as current:
        current_attempt = current["experiments"][args.id]["attempts"][-1]
        if result.returncode == 0 and job_id:
            current_attempt.update({"status": "queued", "job_id": job_id})
            current["experiments"][args.id]["status"] = "queued"
            current["control"].update({"state": "waiting_pbs", "reason": f"waiting for {job_id}"})
            add_history(current, "job_submitted", experiment_id=args.id, job_id=job_id, max_su=experiment["max_su"])
        else:
            current_attempt.update({"status": "failed_submission", "finished_at": utc_now(), "exit_status": result.returncode})
            current["experiments"][args.id]["status"] = "failed_submission"
            add_history(current, "submission_failed", experiment_id=args.id, stderr=result.stderr.strip())
    if not job_id:
        raise CampaignError(f"qsub failed: {result.stderr.strip()}")
    print(json.dumps({"job_id": job_id, "experiment": args.id, "max_su": experiment["max_su"]}, indent=2))


def pbs_output_path(script: str) -> Path:
    match = re.search(r"^#PBS\s+-o\s+(\S+)\s*$", script, re.MULTILINE)
    if not match:
        raise CampaignError("external PBS script needs an absolute #PBS -o path")
    output = Path(match.group(1))
    if not output.is_absolute():
        raise CampaignError("external PBS output path must be absolute")
    return canonical(output)


def cmd_external_submit(args: argparse.Namespace) -> None:
    if not SAFE_ID.fullmatch(args.id):
        raise CampaignError("external job id must start with a letter and contain only letters, digits, ._- ")
    if args.expected_files <= 0:
        raise CampaignError("expected-files must be positive")
    pbs_path = canonical(args.pbs, strict=True)
    if pbs_path.stat().st_size > 256 * 1024:
        raise CampaignError("external PBS script is too large to store safely in campaign state")
    script = pbs_path.read_text(encoding="utf-8")
    executable_text = "\n".join(
        line for line in script.splitlines() if not line.lstrip().startswith("#")
    )
    required_helper = (
        "/g/data/wa66/Xiangyu/.codex/skills/run-on-gadi/scripts/build_conda_sqsh.sh"
        if args.stage == "environment"
        else "/g/data/wa66/Xiangyu/.codex/skills/run-on-gadi/scripts/pack_data.sh"
    )
    helper_variable = "BUILDER" if args.stage == "environment" else "PACKER"
    helper_invoked = re.search(
        rf"(?m)^\s*bash\s+(?:[\"']?\$(?:{helper_variable}|\{{{helper_variable}\}})[\"']?|"
        rf"{re.escape(required_helper)})(?:\s|\\|$)",
        executable_text,
    )
    if required_helper not in executable_text or not helper_invoked:
        raise CampaignError(f"external {args.stage} jobs must invoke the audited helper: {required_helper}")
    report = lint_script(script)
    summary = report.get("summary", {})
    if not summary or not summary.get("project") or not summary.get("queue"):
        raise CampaignError("PBS linter did not produce a resource summary")
    success_path = canonical(args.success_path)
    roots = policy_roots()
    if args.stage == "environment":
        if success_path.suffix != ".sqsh" or not is_within(success_path, roots["environment"]):
            raise CampaignError(f"environment success path must be a .sqsh under {roots['environment']}")
    elif not is_within(success_path, roots["data"]):
        raise CampaignError(f"data success path must be under {roots['data']}")
    if success_path.exists():
        raise CampaignError(
            f"external success path already exists; publish an immutable new version instead: {success_path}"
        )
    state = load_state(args.root)
    require_approved(state, "allow_auto_submit" if args.execute else None)
    if args.execute:
        require_approved(state, "allow_storage_publish")
    if args.id in state["experiments"]:
        raise CampaignError(f"experiment already exists: {args.id}")
    output_path = pbs_output_path(script)
    if not is_within(output_path, canonical(state["root"])):
        raise CampaignError("external PBS stdout/stderr must be under the campaign root")
    if not output_path.parent.is_dir():
        raise CampaignError(f"create the external PBS log parent before submission: {output_path.parent}")
    if output_path.exists():
        raise CampaignError(f"external PBS log path already exists; use a unique immutable path: {output_path}")
    resources = {
        "queue": summary["queue"],
        "project": summary["project"],
        "walltime_seconds": max(1, int(float(summary["walltime_hours"]) * 3600)),
        "ncpus": int(summary["ncpus"]),
        "ngpus": int(summary.get("ngpus", 0)),
        "mem_gb": int(math.ceil(float(summary["mem_gb"]))),
        "jobfs_gb": int(math.ceil(float(summary["jobfs_gb"]))),
    }
    validate_resources(resources, state["approval"], "batch")
    external = {
        "id": args.id,
        "stage": args.stage,
        "mode": "external",
        "status": "planned",
        "created_at": utc_now(),
        "command": [],
        "image": None,
        "resources": resources,
        "max_su": estimate_su(resources),
        "expected_files": args.expected_files,
        "result_dir": str(success_path.parent),
        "success_file": str(success_path),
        "depends_on": [],
        "attempts": [],
    }
    ensure_submission_budget(state, external)
    preflight = live_preflight(state, resources["project"])
    if preflight["projects"][0]["available_su"] < external["max_su"]:
        raise CampaignError("live project allocation is smaller than this job's maximum charge")
    preview = {
        "id": args.id,
        "stage": args.stage,
        "pbs": str(pbs_path),
        "success_path": str(success_path),
        "max_su": external["max_su"],
        "budget": preflight["budget"],
        "linter_warnings": report.get("warnings", []),
    }
    if not args.execute:
        print(json.dumps(preview, indent=2))
        return
    attempt = {
        "number": 1,
        "status": "submitting",
        "job_id": None,
        "submitted_at": utc_now(),
        "finished_at": None,
        "exit_status": None,
        "max_su": external["max_su"],
        "actual_su": None,
        "pbs_script": script,
    }
    external["attempts"].append(attempt)
    external["status"] = "submitting"
    with locked_state(args.root) as current:
        require_approved(current, "allow_auto_submit")
        require_approved(current, "allow_storage_publish")
        if args.id in current["experiments"]:
            raise CampaignError(f"experiment already exists: {args.id}")
        validate_resources(external["resources"], current["approval"], "batch")
        ensure_submission_budget(current, external)
        current["experiments"][args.id] = external
        add_history(current, "external_submission_started", experiment_id=args.id, stage=args.stage)
    if success_path.exists():
        with locked_state(args.root) as current:
            current_exp = current["experiments"][args.id]
            current_attempt = current_exp["attempts"][-1]
            current_attempt.update({"status": "failed_submission", "finished_at": utc_now(), "exit_status": 88})
            current_exp["status"] = "failed_submission"
            add_history(current, "external_submission_failed", experiment_id=args.id, stderr="success path appeared before qsub")
        raise CampaignError("external success path appeared before qsub; no job was submitted")
    with tempfile.NamedTemporaryFile("w", suffix=".pbs", prefix="gadi-autoresearch-external-", dir="/tmp", delete=False, encoding="utf-8") as handle:
        handle.write(script)
        validated_script_path = Path(handle.name)
    try:
        result = command_output(["qsub", str(validated_script_path)], timeout=60)
    finally:
        validated_script_path.unlink(missing_ok=True)
    job_id = submitted_job_id(result)
    with locked_state(args.root) as current:
        current_exp = current["experiments"][args.id]
        current_attempt = current_exp["attempts"][-1]
        if job_id:
            current_attempt.update({"status": "queued", "job_id": job_id})
            current_exp["status"] = "queued"
            current["control"].update({"state": "waiting_pbs", "reason": f"waiting for external job {job_id}"})
            add_history(current, "external_job_submitted", experiment_id=args.id, job_id=job_id)
        else:
            current_attempt.update({"status": "failed_submission", "finished_at": utc_now(), "exit_status": result.returncode})
            current_exp["status"] = "failed_submission"
            add_history(current, "external_submission_failed", experiment_id=args.id, stderr=result.stderr.strip())
    if not job_id:
        raise CampaignError(f"qsub failed: {result.stderr.strip()}")
    print(json.dumps({"job_id": job_id, **preview}, indent=2))


def interactive_kind(queue: str) -> str:
    try:
        return str(INTERACTIVE_PROFILES[queue]["kind"])
    except KeyError as exc:
        raise CampaignError(f"queue is not supported for interactive work: {queue}") from exc


def cmd_interactive(args: argparse.Namespace) -> None:
    state = load_state(args.root)
    require_approved(state, "allow_interactive" if args.execute else None)
    experiment = state["experiments"].get(args.id)
    if not experiment or experiment["mode"] != "interactive":
        raise CampaignError(f"unknown interactive experiment: {args.id}")
    if experiment_status(experiment) not in {"planned", "failed", "failed_submission", "cancelled"}:
        raise CampaignError(f"interactive experiment cannot start from {experiment_status(experiment)}")
    require_dependencies(state, experiment)
    require_registered_inputs(state, experiment)
    validate_resources(experiment["resources"], state["approval"], "interactive")
    validate_interactive_profile(experiment["resources"])
    ensure_submission_budget(state, experiment)
    preflight = live_preflight(state, experiment["resources"]["project"])
    if preflight["projects"][0]["available_su"] < float(experiment["max_su"]):
        raise CampaignError("live project allocation is smaller than this interactive job's maximum charge")
    session = args.session or f"aris-{state['campaign_id']}-{args.id}"
    if not SAFE_ID.fullmatch(session):
        raise CampaignError("unsafe tmux session name")
    helper = Path(__file__).resolve().parents[2] / "run-on-gadi" / "scripts" / "debug_session.sh"
    resources = experiment["resources"]
    command = [
        "bash", str(helper), "--kind", interactive_kind(resources["queue"]),
        "--project", resources["project"], "--walltime", format_walltime(resources["walltime_seconds"]),
        "--mem-gb", str(resources["mem_gb"]), "--jobfs-gb", str(resources["jobfs_gb"]),
        "--session", session, "--persistent-control-host",
    ]
    if args.execute:
        command.append("--start")
    if not args.execute:
        print(json.dumps({
            "command": shlex.join(command),
            "max_su": experiment["max_su"],
            "budget": preflight["budget"],
            "jobfs_staging": "$PBS_JOBFS/gadi-autoresearch-output/" + experiment["id"],
            "workload_command": experiment["command"],
        }, indent=2))
        return
    attempt = {
        "number": len(experiment.get("attempts", [])) + 1,
        "status": "submitting",
        "job_id": None,
        "tmux_session": session,
        "submitted_at": utc_now(),
        "finished_at": None,
        "exit_status": None,
        "max_su": experiment["max_su"],
        "actual_su": None,
    }
    with locked_state(args.root) as current:
        require_approved(current, "allow_interactive")
        current_exp = current["experiments"][args.id]
        current_status = experiment_status(current_exp)
        if current_status not in {"planned", "failed", "failed_submission", "cancelled"}:
            raise CampaignError(f"interactive experiment cannot start from current status {current_status}")
        require_dependencies(current, current_exp)
        require_registered_inputs(current, current_exp)
        validate_resources(current_exp["resources"], current["approval"], "interactive")
        ensure_submission_budget(current, current_exp)
        current_exp["attempts"].append(attempt)
        current_exp["status"] = "submitting"
        add_history(current, "interactive_submission_started", experiment_id=args.id, tmux_session=session)
    result = subprocess.run(command, check=False, text=True)
    with locked_state(args.root) as current:
        current_exp = current["experiments"][args.id]
        current_attempt = current_exp["attempts"][-1]
        if result.returncode == 0:
            current_attempt["status"] = "interactive_pending"
            current_exp["status"] = "interactive_pending"
            current["control"].update({"state": "waiting_pbs", "reason": f"interactive tmux {session}"})
            add_history(current, "interactive_started", experiment_id=args.id, tmux_session=session)
        else:
            current_attempt.update({"status": "failed_submission", "finished_at": utc_now(), "exit_status": result.returncode})
            current_exp["status"] = "failed_submission"
            add_history(current, "interactive_submission_failed", experiment_id=args.id, returncode=result.returncode)
    if result.returncode != 0:
        raise CampaignError(f"interactive helper failed with exit {result.returncode}")
    print(json.dumps({"tmux_session": session, "status": "interactive_pending"}, indent=2))


def interactive_jobfs(experiment: dict[str, Any]) -> tuple[Path, Path]:
    if not os.environ.get("PBS_JOBID") or not os.environ.get("PBS_JOBFS"):
        raise CampaignError("this command must run inside the allocated interactive PBS shell")
    jobfs = canonical(os.environ["PBS_JOBFS"], strict=True)
    if is_within(jobfs, policy_roots()["persistent"]):
        raise CampaignError("PBS_JOBFS unexpectedly resolves on persistent storage")
    if not SAFE_JOB_ID.fullmatch(os.environ["PBS_JOBID"]):
        raise CampaignError(f"unexpected PBS job id: {os.environ['PBS_JOBID']}")
    staging = jobfs / "gadi-autoresearch-output" / experiment["id"]
    return jobfs, staging


def cmd_interactive_run(args: argparse.Namespace) -> None:
    initial = load_state(args.root)
    workspace = canonical(initial["workspace"], strict=True)
    source = git_workspace_info(workspace, require_clean=True)
    with locked_state(args.root) as state:
        require_approved(state)
        experiment = state["experiments"].get(args.id)
        if not experiment or experiment["mode"] != "interactive" or not experiment.get("attempts"):
            raise CampaignError(f"interactive experiment has no active attempt: {args.id}")
        attempt = experiment["attempts"][-1]
        if attempt["status"] not in {"interactive_pending", "interactive_running"}:
            raise CampaignError("latest interactive attempt is not active")
        if attempt.get("published_at"):
            raise CampaignError("interactive results are already published; exit PBS and close the attempt")
        jobfs, staging_dir = interactive_jobfs(experiment)
        require_registered_inputs(state, experiment)
        if source["commit"] != experiment["source_commit"]:
            experiment["source_commit"] = source["commit"]
            experiment.setdefault("source_history", []).append({
                "at": utc_now(),
                "commit": source["commit"],
                "reason": "interactive run",
            })
            del experiment["source_history"][:-50]
            add_history(state, "interactive_source_updated", experiment_id=args.id, commit=source["commit"])
        snapshot_state = state
        snapshot_experiment = experiment
    staged_workspace = stage_source_commit(snapshot_state, snapshot_experiment, jobfs)
    staging_dir.mkdir(parents=True, exist_ok=True)
    command = substitute_command(
        snapshot_experiment,
        snapshot_state,
        result_dir=staging_dir,
        jobfs=jobfs,
        workspace=staged_workspace,
    )
    image = canonical(snapshot_experiment["image"], strict=True)
    resources = dict(snapshot_experiment["resources"])
    expected_files = int(snapshot_experiment["expected_files"])
    with locked_state(args.root) as state:
        experiment = state["experiments"][args.id]
        attempt = experiment["attempts"][-1]
        if attempt["status"] not in {"interactive_pending", "interactive_running"} or attempt.get("published_at"):
            raise CampaignError("interactive attempt changed while staging source")
        if experiment["source_commit"] != snapshot_experiment["source_commit"]:
            raise CampaignError("interactive source commit changed concurrently")
        image = canonical(experiment["image"], strict=True)
        attempt.update({
            "status": "interactive_running",
            "job_id": os.environ["PBS_JOBID"],
            "started_at": attempt.get("started_at") or utc_now(),
            "staging_dir": str(staging_dir),
        })
        experiment["status"] = "interactive_running"
        add_history(
            state,
            "interactive_workload_started",
            experiment_id=args.id,
            job_id=os.environ["PBS_JOBID"],
            source_commit=experiment["source_commit"],
        )
    runner = Path(__file__).resolve().parents[2] / "run-on-gadi" / "scripts" / "run_sqsh.sh"
    invocation = ["bash", str(runner)]
    if resources["ngpus"]:
        invocation.append("--nv")
    invocation.extend([str(image), *command])
    completed = subprocess.run(invocation, check=False)
    try:
        produced = validate_output_tree(staging_dir, expected_files)
    except OutputLimitError as exc:
        with locked_state(args.root) as state:
            state["status"] = "paused"
            state["control"].update({"state": "paused", "reason": str(exc)})
            add_history(state, "interactive_output_limit_exceeded", experiment_id=args.id)
        raise CampaignError(f"interactive output limit exceeded; exit the allocation: {exc}") from exc
    with locked_state(args.root) as state:
        attempt = state["experiments"][args.id]["attempts"][-1]
        attempt.update({"last_command_exit": completed.returncode, "staged_entries": produced})
        add_history(
            state,
            "interactive_workload_finished",
            experiment_id=args.id,
            returncode=completed.returncode,
            staged_entries=produced,
        )
    print(json.dumps({
        "returncode": completed.returncode,
        "staging_dir": str(staging_dir),
        "staged_entries": produced,
        "published": False,
    }, indent=2))
    if completed.returncode:
        raise SystemExit(completed.returncode)


def cmd_interactive_publish(args: argparse.Namespace) -> None:
    publish_error: CampaignError | None = None
    with locked_state(args.root) as state:
        require_approved(state)
        experiment = state["experiments"].get(args.id)
        if not experiment or experiment["mode"] != "interactive" or not experiment.get("attempts"):
            raise CampaignError(f"interactive experiment has no active attempt: {args.id}")
        attempt = experiment["attempts"][-1]
        if attempt["status"] != "interactive_running":
            raise CampaignError("latest interactive attempt is not running")
        if attempt.get("published_at"):
            raise CampaignError("interactive results are already published")
        if attempt.get("last_command_exit") != 0:
            raise CampaignError("latest interactive workload did not exit zero")
        _, staging_dir = interactive_jobfs(experiment)
        try:
            produced = publish_staged_output(state, experiment, staging_dir, int(attempt["number"]))
        except CampaignError as exc:
            publish_error = exc
            state["status"] = "paused"
            state["control"].update({"state": "paused", "reason": str(exc)})
            add_history(state, "interactive_publication_failed", experiment_id=args.id, reason=str(exc))
        else:
            attempt.update({"published_at": utc_now(), "produced_entries": produced})
            add_history(state, "interactive_results_published", experiment_id=args.id, produced_entries=produced)
            print(json.dumps({
                "result_dir": experiment["result_dir"],
                "success_file": experiment["success_file"],
                "produced_entries": produced,
                "next": "exit the PBS shell, then call interactive-close on the control host",
            }, indent=2))
    if publish_error:
        raise CampaignError(f"interactive result publication failed and campaign paused: {publish_error}")


def cmd_interactive_close(args: argparse.Namespace) -> None:
    walltime = parse_walltime(args.actual_walltime)
    with locked_state(args.root) as state:
        experiment = state["experiments"].get(args.id)
        if not experiment or experiment["mode"] != "interactive" or not experiment.get("attempts"):
            raise CampaignError(f"interactive experiment has no active attempt: {args.id}")
        attempt = experiment["attempts"][-1]
        if attempt["status"] not in {"interactive_pending", "interactive_running"}:
            raise CampaignError("latest interactive attempt is not active")
        if walltime > int(experiment["resources"]["walltime_seconds"]):
            raise CampaignError("actual interactive walltime cannot exceed the requested walltime")
        if args.outcome == "completed":
            success = canonical(experiment["success_file"])
            if not attempt.get("published_at") or not success.is_file():
                raise CampaignError("completed interactive work must be published inside PBS before closing")
        actual_resources = dict(experiment["resources"])
        actual_resources["walltime_seconds"] = walltime
        attempt.update({
            "status": args.outcome,
            "finished_at": utc_now(),
            "exit_status": 0 if args.outcome == "completed" else 1,
            "actual_su": estimate_su(actual_resources),
            "actual_su_source": "reported",
        })
        experiment["status"] = args.outcome
        if state["status"] == "active":
            control_after_terminal_attempt(state, f"interactive experiment {args.id} {args.outcome}")
        add_history(
            state,
            "interactive_closed",
            experiment_id=args.id,
            outcome=args.outcome,
            actual_su=attempt["actual_su"],
            produced_entries=attempt.get("produced_entries"),
        )
        print(json.dumps(attempt, indent=2))


def cmd_cancel(args: argparse.Namespace) -> None:
    state = load_state(args.root)
    require_approved(
        state,
        "allow_auto_cancel" if args.execute else None,
        require_active=False,
        allow_expired=True,
    )
    experiment = state["experiments"].get(args.id)
    if not experiment or not experiment.get("attempts"):
        raise CampaignError(f"experiment has no submitted attempt: {args.id}")
    attempt = experiment["attempts"][-1]
    if attempt.get("status") not in JOB_ACTIVE:
        raise CampaignError(f"latest attempt is not active: {attempt.get('status')}")
    if attempt.get("status") == "cancel_requested":
        raise CampaignError("cancellation is already awaiting PBS confirmation")
    job_id = attempt.get("job_id")
    if not job_id:
        raise CampaignError("interactive job ID is not recorded; exit the known tmux PBS shell instead of guessing a qdel target")
    preview = {"experiment": args.id, "job_id": job_id, "command": shlex.join(["qdel", job_id])}
    if not args.execute:
        print(json.dumps(preview, indent=2))
        return
    with locked_state(args.root) as current:
        require_approved(
            current,
            "allow_auto_cancel",
            require_active=False,
            allow_expired=True,
        )
        current_exp = current["experiments"][args.id]
        current_attempt = current_exp["attempts"][-1]
        if current_attempt.get("job_id") != job_id or current_attempt.get("status") not in JOB_ACTIVE:
            raise CampaignError("job state changed before cancellation; refresh before acting")
        result = command_output(["qdel", job_id], timeout=30)
        if result.returncode != 0:
            raise CampaignError(f"qdel failed for recorded job {job_id}: {result.stderr.strip()}")
        current_attempt.update({"status": "cancel_requested", "cancel_requested_at": utc_now()})
        current_exp["status"] = "cancel_requested"
        current["control"].update({"state": "waiting_pbs", "reason": f"waiting for PBS to confirm cancellation of {job_id}"})
        add_history(current, "job_cancel_requested", experiment_id=args.id, job_id=job_id)
    print(json.dumps({**preview, "status": "cancel_requested"}, indent=2))


def parse_qstat(text: str) -> dict[str, dict[str, str]]:
    jobs: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    current_key: str | None = None
    for raw in text.splitlines():
        if raw.startswith("Job Id:"):
            job_id = raw.split(":", 1)[1].strip()
            current = {"job_id": job_id}
            jobs[job_id] = current
            current_key = None
            continue
        if current is None:
            continue
        match = re.match(r"\s+([A-Za-z0-9_.-]+)\s*=\s*(.*)$", raw)
        if match:
            current_key = match.group(1)
            current[current_key] = match.group(2).strip()
        elif current_key and raw.startswith("\t"):
            current[current_key] += raw.strip()
    return jobs


def pbs_status(record: dict[str, str]) -> tuple[str, int | None]:
    state = record.get("job_state", "")
    if state in {"Q", "W", "T"}:
        return "queued", None
    if state == "H":
        return "held", None
    if state in {"R", "E", "B"}:
        return "running", None
    if state in {"F", "X"}:
        try:
            exit_status = int(record.get("Exit_status", "1"))
        except ValueError:
            exit_status = 1
        return ("completed" if exit_status == 0 else "failed"), exit_status
    return "queued", None


def cmd_refresh(args: argparse.Namespace) -> None:
    state = load_state(args.root)
    require_approved(state, require_active=False, allow_expired=True)
    active: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for exp_id, experiment in state["experiments"].items():
        for attempt in experiment.get("attempts", []):
            if attempt.get("job_id") and attempt.get("status") in {"queued", "held", "running", "finishing", "cancel_requested", "submitting"}:
                active.append((exp_id, experiment, attempt))
    if not active:
        interactive_active = any(
            attempt.get("status") in {"interactive_pending", "interactive_running"}
            for experiment in state["experiments"].values()
            for attempt in experiment.get("attempts", [])
        )
        with locked_state(args.root) as current:
            if current["status"] == "active" and current["control"]["state"] == "waiting_pbs":
                current["control"].update({
                    "state": "needs_agent",
                    "reason": (
                        "inspect the recorded interactive tmux session"
                        if interactive_active
                        else "no tracked PBS jobs remain active"
                    ),
                })
        print(json.dumps({
            "polled": False,
            "reason": "no active batch jobs",
            "interactive_active": interactive_active,
        }, indent=2))
        return
    last_poll = state["control"].get("last_pbs_poll_at")
    if last_poll:
        elapsed = dt.datetime.now(dt.timezone.utc) - parse_time(last_poll)
        if elapsed.total_seconds() < 600:
            raise CampaignError(f"PBS polling is limited to once per 600 seconds; wait {math.ceil(600 - elapsed.total_seconds())}s")
    job_ids = [attempt["job_id"] for _, _, attempt in active]
    result = command_output(["qstat", "-x", "-f", *job_ids], timeout=60)
    if result.returncode != 0:
        raise CampaignError(f"qstat failed: {result.stderr.strip()}")
    records = parse_qstat(result.stdout)
    changes = []
    with locked_state(args.root) as current:
        current["control"]["last_pbs_poll_at"] = utc_now()
        for exp_id, _, old_attempt in active:
            job_id = old_attempt["job_id"]
            record = records.get(job_id)
            if not record:
                continue
            status, exit_status = pbs_status(record)
            experiment = current["experiments"][exp_id]
            if old_attempt.get("status") == "cancel_requested" and status in JOB_TERMINAL:
                status = "cancelled"
            produced_entries = None
            validation_failure = False
            if status == "completed" and experiment.get("mode") == "external":
                raw_success = Path(experiment["success_file"])
                if not raw_success.exists() or raw_success.is_symlink():
                    status = "failed"
                    exit_status = 86
                    validation_failure = True
                else:
                    try:
                        success = canonical(raw_success, strict=True)
                        if experiment["stage"] == "environment":
                            validate_environment(success)
                            produced_entries = 1
                        else:
                            validate_packed_data(success)
                            storage_identity(success)
                            produced_entries = (
                                1
                                if success.is_file()
                                else 1 + count_entries(success, int(experiment["expected_files"]))
                            )
                        if produced_entries > int(experiment["expected_files"]):
                            raise OutputLimitError("external output exceeds declared entry limit")
                    except OutputLimitError:
                        status = "failed"
                        exit_status = 87
                        validation_failure = True
                    except CampaignError:
                        status = "failed"
                        exit_status = 86
                        validation_failure = True
            elif status == "completed" and experiment.get("mode") == "batch":
                result_dir = canonical(experiment["result_dir"])
                success = canonical(experiment["success_file"])
                try:
                    produced_entries = validate_output_tree(result_dir, int(experiment["expected_files"]))
                    if not success.is_file() or success.is_symlink():
                        raise CampaignError(f"batch success marker is missing or invalid: {success}")
                except OutputLimitError:
                    status = "failed"
                    exit_status = 87
                    validation_failure = True
                except CampaignError:
                    status = "failed"
                    exit_status = 86
                    validation_failure = True
            attempt = next(item for item in experiment["attempts"] if item.get("job_id") == job_id)
            previous = attempt["status"]
            attempt["status"] = status
            experiment["status"] = status
            if exit_status is not None:
                attempt["exit_status"] = exit_status
                attempt["finished_at"] = utc_now()
                walltime_text = record.get("resources_used.walltime")
                if walltime_text:
                    used = dict(experiment["resources"])
                    used["walltime_seconds"] = parse_walltime(walltime_text)
                    attempt["actual_su"] = estimate_su(used)
                    attempt["actual_su_source"] = "pbs"
            if produced_entries is not None:
                attempt["produced_entries"] = produced_entries
            if validation_failure:
                current["status"] = "paused"
                current["control"].update({
                    "state": "paused",
                    "reason": f"job {job_id} reported success but durable output validation failed ({exit_status})",
                })
            if previous != status:
                changes.append({"job_id": job_id, "previous": previous, "status": status})
                add_history(current, "pbs_status_changed", experiment_id=exp_id, job_id=job_id, previous=previous, status=status)
        remaining = any(attempt.get("status") in JOB_ACTIVE for exp in current["experiments"].values() for attempt in exp.get("attempts", []))
        if not remaining and current["status"] == "active":
            current["control"].update({"state": "needs_agent", "reason": "all tracked PBS jobs are terminal"})
    print(json.dumps({"polled": True, "changes": changes}, indent=2))


def stage_source_commit(state: dict[str, Any], experiment: dict[str, Any], jobfs: Path) -> Path:
    require_registered_inputs(state, experiment)
    commit = experiment["source_commit"]
    workspace = canonical(state["workspace"], strict=True)
    source_root = jobfs / "gadi-autoresearch-source" / experiment["id"] / commit[:16]
    if source_root.is_dir():
        marker = source_root / ".gadi-autoresearch-source"
        if marker.is_file() and marker.read_text(encoding="utf-8").strip() == commit:
            return source_root
        raise CampaignError(f"partial source staging requires inspection: {source_root}")
    source_root.mkdir(parents=True)
    archive = source_root.parent / f".{commit[:16]}.tar"
    git_result = command_output(
        ["git", "-C", str(workspace), "archive", "--format=tar", f"--output={archive}", commit],
        timeout=300,
    )
    if git_result.returncode != 0:
        raise CampaignError(f"failed to archive source commit {commit}: {git_result.stderr.strip()}")
    try:
        tar_result = command_output(["tar", "-xf", str(archive), "-C", str(source_root)], timeout=300)
        if tar_result.returncode != 0:
            raise CampaignError(f"failed to extract source commit {commit}: {tar_result.stderr.strip()}")
        (source_root / ".gadi-autoresearch-source").write_text(commit + "\n", encoding="utf-8")
    finally:
        archive.unlink(missing_ok=True)
    return source_root


def substitute_command(
    experiment: dict[str, Any],
    state: dict[str, Any],
    *,
    result_dir: Path | None = None,
    jobfs: Path | None = None,
    workspace: Path | None = None,
) -> list[str]:
    replacements = {
        "{RESULT_DIR}": str(result_dir) if result_dir else experiment["result_dir"],
        "{PBS_JOBFS}": str(jobfs) if jobfs else os.environ.get("PBS_JOBFS", ""),
        "{WORKSPACE}": str(workspace) if workspace else state["workspace"],
        "{DATA_ROOT}": str(policy_roots()["data"]),
    }
    output = []
    for argument in experiment["command"]:
        for token, value in replacements.items():
            argument = argument.replace(token, value)
        output.append(argument)
    return output


def validate_output_tree(root: Path, expected_files: int) -> int:
    if not root.is_dir():
        raise CampaignError(f"staged result directory is missing: {root}")
    produced = count_entries(root, expected_files)
    if produced > expected_files:
        raise OutputLimitError(
            f"staged result entry count exceeds declared limit {expected_files}"
        )
    for current, directories, files in os.walk(root, followlinks=False):
        for name in [*directories, *files]:
            path = Path(current) / name
            if path.is_symlink():
                raise CampaignError(f"staged results cannot contain symlinks: {path}")
            if not path.is_dir() and not path.is_file():
                raise CampaignError(f"staged results contain a special file: {path}")
    return produced


def publish_staged_output(
    state: dict[str, Any],
    experiment: dict[str, Any],
    staging_dir: Path,
    attempt_number: int,
) -> int:
    expected_files = int(experiment["expected_files"])
    produced = validate_output_tree(staging_dir, expected_files)
    result_dir = canonical(experiment["result_dir"])
    runs_root = canonical(state["root"]) / "runs"
    if not is_within(result_dir, runs_root):
        raise CampaignError("experiment result directory is outside the campaign runs tree")
    success_path = canonical(experiment["success_file"])
    try:
        success_relative = success_path.relative_to(result_dir)
    except ValueError as exc:
        raise CampaignError("experiment success marker is outside its result directory") from exc
    staged_success = staging_dir / success_relative
    if not staged_success.is_file() or staged_success.is_symlink():
        raise CampaignError(f"staged success marker is missing or invalid: {staged_success}")

    result_dir.parent.mkdir(parents=True, exist_ok=True)
    if result_dir.exists():
        if result_dir.is_dir() and not any(result_dir.iterdir()):
            result_dir.rmdir()
        else:
            raise CampaignError(f"refusing to replace an existing result directory: {result_dir}")
    publishing = result_dir.parent / f".{experiment['id']}.a{attempt_number}.publishing"
    if publishing.exists():
        raise CampaignError(f"stale publishing directory requires inspection: {publishing}")
    try:
        shutil.copytree(staging_dir, publishing, symlinks=True)
        validate_output_tree(publishing, expected_files)
        copied_success = publishing / success_relative
        if not copied_success.is_file():
            raise CampaignError(f"published success marker is missing: {copied_success}")
        os.replace(publishing, result_dir)
    except (OSError, shutil.Error) as exc:
        if publishing.exists():
            shutil.rmtree(publishing)
        raise CampaignError(f"failed to publish compact results: {exc}") from exc
    except CampaignError:
        if publishing.exists():
            shutil.rmtree(publishing)
        raise
    return produced


def cmd_worker_run(args: argparse.Namespace) -> None:
    if not os.environ.get("PBS_JOBID") or not os.environ.get("PBS_JOBFS"):
        raise CampaignError("worker-run may only execute inside a PBS job with PBS_JOBFS")
    started = time.monotonic()
    with locked_state(args.root) as state:
        experiment = state["experiments"].get(args.id)
        if not experiment or experiment["mode"] != "batch" or not experiment.get("attempts"):
            raise CampaignError(f"no submitted batch experiment: {args.id}")
        job_id = os.environ["PBS_JOBID"]
        if not SAFE_JOB_ID.fullmatch(job_id):
            raise CampaignError(f"unexpected PBS job id: {job_id}")
        attempt = experiment["attempts"][-1]
        if attempt.get("job_id") and attempt["job_id"] != job_id:
            raise CampaignError("worker PBS job id does not match the recorded submission")
        attempt.update({"status": "running", "job_id": job_id, "started_at": utc_now()})
        experiment["status"] = "running"
        add_history(
            state,
            "worker_started",
            experiment_id=args.id,
            job_id=job_id,
            source_commit=experiment.get("source_commit"),
        )
        require_registered_inputs(state, experiment)
        image = canonical(experiment["image"], strict=True)
        result_dir = canonical(experiment["result_dir"])
        attempt_number = int(attempt["number"])
        jobfs = canonical(os.environ["PBS_JOBFS"], strict=True)
        if is_within(jobfs, policy_roots()["persistent"]):
            raise CampaignError("PBS_JOBFS unexpectedly resolves on persistent storage")
        staging_dir = jobfs / "gadi-autoresearch-output" / experiment["id"]
        if staging_dir.exists():
            raise CampaignError(f"jobfs staging directory already exists: {staging_dir}")
        staging_dir.mkdir(parents=True)
        expected_files = int(experiment["expected_files"])
        success_file = canonical(experiment["success_file"])
        if not is_within(success_file, result_dir):
            raise CampaignError("experiment success marker resolves outside its result directory")
        resources = dict(experiment["resources"])
        snapshot_state = state
        snapshot_experiment = experiment
    staged_workspace = stage_source_commit(snapshot_state, snapshot_experiment, jobfs)
    command = substitute_command(
        snapshot_experiment,
        snapshot_state,
        result_dir=staging_dir,
        jobfs=jobfs,
        workspace=staged_workspace,
    )
    runner = Path(__file__).resolve().parents[2] / "run-on-gadi" / "scripts" / "run_sqsh.sh"
    invocation = ["bash", str(runner)]
    if resources["ngpus"]:
        invocation.append("--nv")
    invocation.extend([str(image), *command])
    launch_error: OSError | None = None
    try:
        completed = subprocess.run(invocation, check=False)
        exit_status = completed.returncode
    except OSError as exc:
        exit_status = 85
        completed = None
        launch_error = exc
    outcome = "completed"
    reason = "command exited zero and compact results were atomically published"
    if exit_status != 0:
        outcome = "failed"
        reason = f"command exited {exit_status}" if completed else f"runner launch failed: {launch_error}"
    try:
        produced = validate_output_tree(staging_dir, expected_files)
        if outcome == "completed":
            produced = publish_staged_output(state, experiment, staging_dir, attempt_number)
            if not success_file.is_file():
                raise CampaignError(f"published success marker is missing: {success_file}")
    except OutputLimitError as exc:
        produced = expected_files + 1
        exit_status = 87
        outcome = "failed"
        reason = str(exc)
    except CampaignError as exc:
        produced = count_entries(staging_dir, expected_files)
        if outcome == "completed":
            exit_status = 86
            outcome = "failed"
            reason = str(exc)
    used = dict(resources)
    used["walltime_seconds"] = max(1, min(int(time.monotonic() - started), resources["walltime_seconds"]))
    with locked_state(args.root) as state:
        experiment = state["experiments"][args.id]
        attempt = experiment["attempts"][-1]
        recorded_status = "cancel_requested" if attempt.get("status") == "cancel_requested" else "finishing"
        attempt.update({
            "status": recorded_status,
            "worker_outcome": outcome,
            "worker_finished_at": utc_now(),
            "worker_exit_status": exit_status,
            "estimated_worker_su": estimate_su(used),
            "produced_entries": produced,
            "reason": reason,
        })
        experiment["status"] = recorded_status
        if exit_status == 87:
            state["status"] = "paused"
            state["control"].update({"state": "paused", "reason": reason})
        else:
            state["control"].update({"state": "waiting_pbs", "reason": f"waiting for PBS to finalize {os.environ['PBS_JOBID']}"})
        add_history(state, "worker_finished", experiment_id=args.id, outcome=outcome, exit_status=exit_status, produced_entries=produced)
    raise SystemExit(exit_status)


def verify_completion_artifacts(state: dict[str, Any]) -> tuple[str, str]:
    missing = [name for name in REQUIRED_COMPLETION_ARTIFACTS if name not in state["artifacts"]]
    if missing:
        raise CampaignError("cannot complete campaign; missing artifacts: " + ", ".join(missing))
    summary = budget_summary(state)
    if summary["actual_persistent_entries"] > summary["max_persistent_files"]:
        raise CampaignError("cannot complete campaign after exceeding the persistent-file envelope")
    for name in REQUIRED_COMPLETION_ARTIFACTS:
        record = state["artifacts"][name]
        path = canonical(record["path"])
        if not path.is_file():
            raise CampaignError(f"completion artifact is missing or not a file: {name}: {path}")
        stat = path.stat()
        if record.get("size_bytes") != stat.st_size or record.get("mtime_ns") != stat.st_mtime_ns:
            raise CampaignError(f"completion artifact changed after it was recorded: {name}: {path}")
        if stat.st_size <= 0:
            raise CampaignError(f"completion artifact is empty: {name}: {path}")
    paper_source = canonical(state["artifacts"]["paper_source"]["path"])
    if paper_source.suffix != ".tex":
        raise CampaignError("paper_source must be a LaTeX .tex file")
    workspace = canonical(state["workspace"], strict=True)
    if not is_within(paper_source, workspace):
        raise CampaignError("paper_source must be stored in the research Git workspace")
    workspace_git = git_workspace_info(workspace, require_clean=True)
    tracked = command_output(
        ["git", "-C", str(workspace), "ls-files", "--error-unmatch", str(paper_source.relative_to(workspace))]
    )
    if tracked.returncode != 0:
        raise CampaignError("paper_source must be tracked in the final Git commit")
    paper_pdf = canonical(state["artifacts"]["paper_pdf"]["path"])
    with paper_pdf.open("rb") as handle:
        signature = handle.read(5)
    if paper_pdf.stat().st_size < 100 or signature != b"%PDF-":
        raise CampaignError("paper_pdf is not a nontrivial PDF file")
    assurances = {state["artifacts"][name]["assurance"] for name in REQUIRED_COMPLETION_ARTIFACTS}
    return ("provisional" if "provisional" in assurances else "accepted", workspace_git["commit"])


def cmd_handoff(args: argparse.Namespace) -> None:
    with locked_state(args.root) as state:
        allow_expired = args.state in {"waiting_pbs", "waiting_human", "paused", "stopped", "complete"}
        require_approved(state, allow_expired=allow_expired)
        control = state["control"]
        if args.state == "complete":
            state["overall_assurance"], state["final_source_commit"] = verify_completion_artifacts(state)
            incomplete_jobs = [exp_id for exp_id, exp in state["experiments"].items() if experiment_status(exp) in JOB_ACTIVE]
            if incomplete_jobs:
                raise CampaignError("cannot complete campaign with active jobs: " + ", ".join(incomplete_jobs))
            state["status"] = "complete"
            state["phase"] = "complete"
        elif args.state == "paused":
            state["status"] = "paused"
        elif args.state == "stopped":
            state["status"] = "stopped"
        if args.state == "waiting_time":
            if not args.wake_at:
                raise CampaignError("waiting_time requires --wake-at")
            wake = parse_time(args.wake_at)
            if wake <= dt.datetime.now(dt.timezone.utc):
                raise CampaignError("wake-at must be in the future")
            if wake > parse_time(state["approval"]["deadline"]):
                raise CampaignError("wake-at cannot exceed the campaign approval deadline")
            control["wake_at"] = args.wake_at
        else:
            control["wake_at"] = None
        control.update({"state": args.state, "reason": args.reason})
        add_history(state, "agent_handoff", handoff_state=args.state, reason=args.reason)
        print(json.dumps(control, indent=2))


def cmd_resume(args: argparse.Namespace) -> None:
    with locked_state(args.root) as state:
        require_approved(state, require_active=False)
        if state["status"] not in {"paused", "stopped"}:
            raise CampaignError(f"campaign cannot resume from status {state['status']}")
        previous = state["status"]
        state["status"] = "active"
        state["control"].update({"state": "needs_agent", "reason": args.reason, "wake_at": None})
        add_history(state, "campaign_resumed", previous=previous, reason=args.reason)
        print(json.dumps(state["control"], indent=2))


def add_common_init(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("root")
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--idea", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--venue", default="generic-preprint")
    parser.add_argument("--assurance", choices=("draft", "submission"), default="draft")
    parser.add_argument("--projects", default="wa66")
    parser.add_argument("--max-su", type=float, default=500.0)
    parser.add_argument("--max-jobs", type=int, default=12)
    parser.add_argument("--max-concurrent", type=int, default=1)
    parser.add_argument("--max-gpus", type=int, default=1)
    parser.add_argument("--max-interactive-walltime", default="04:00:00")
    parser.add_argument("--max-batch-walltime", default="24:00:00")
    parser.add_argument("--max-files", type=int, default=512)
    parser.add_argument("--max-agent-turns", type=int, default=40)
    parser.add_argument("--deadline", required=True)
    parser.add_argument("--environment")
    parser.add_argument("--data", action="append", default=[])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command_name", required=True)

    init = sub.add_parser("init", help="create a draft campaign")
    add_common_init(init)
    init.set_defaults(func=cmd_init)

    approve = sub.add_parser("approve", help="record an explicit campaign envelope approval")
    approve.add_argument("root")
    approve.add_argument("--by", required=True)
    approve.add_argument("--allow-auto-submit", action="store_true")
    approve.add_argument("--allow-storage-publish", action="store_true")
    approve.add_argument("--allow-interactive", action="store_true")
    approve.add_argument("--allow-auto-agent", action="store_true")
    approve.add_argument("--allow-auto-cancel", action="store_true")
    approve.add_argument("--replace", action="store_true", help="replace an existing paused/expired approval after explicit user reapproval")
    approve.add_argument("--projects")
    approve.add_argument("--max-su", type=float)
    approve.add_argument("--max-jobs", type=int)
    approve.add_argument("--max-concurrent", type=int)
    approve.add_argument("--max-gpus", type=int)
    approve.add_argument("--max-interactive-walltime")
    approve.add_argument("--max-batch-walltime")
    approve.add_argument("--max-files", type=int)
    approve.add_argument("--max-agent-turns", type=int)
    approve.add_argument("--deadline")
    approve.set_defaults(func=cmd_approve)

    storage = sub.add_parser("storage-set", help="record a validated .sqsh or packed dataset")
    storage.add_argument("root")
    storage.add_argument("--environment")
    storage.add_argument("--data", action="append", default=[])
    storage.set_defaults(func=cmd_storage_set)

    status = sub.add_parser("status", help="show phase, approval, jobs, artifacts, and remaining budgets")
    status.add_argument("root")
    status.set_defaults(func=cmd_status)

    preflight = sub.add_parser("preflight", help="run live project, SU, inode, and campaign-file checks")
    preflight.add_argument("root")
    preflight.set_defaults(func=cmd_preflight)

    phase = sub.add_parser("phase", help="record a research phase transition and reason")
    phase.add_argument("root")
    phase.add_argument("phase", choices=PHASES)
    phase.add_argument("--reason", required=True)
    phase.set_defaults(func=cmd_phase)

    artifact = sub.add_parser("artifact", help="record one canonical evidence artifact and assurance class")
    artifact.add_argument("root")
    artifact.add_argument("--name", required=True)
    artifact.add_argument("--path", required=True)
    artifact.add_argument("--assurance", choices=("deterministic", "accepted", "provisional", "not-applicable"), default="deterministic")
    artifact.set_defaults(func=cmd_artifact)

    experiment = sub.add_parser("experiment-add", help="register a structured interactive or batch experiment")
    experiment.add_argument("root")
    experiment.add_argument("--id", required=True)
    experiment.add_argument("--stage", choices=("sanity", "pilot", "baseline", "main", "ablation", "audit", "paper"), required=True)
    experiment.add_argument("--mode", choices=("interactive", "batch"), required=True)
    experiment.add_argument("--queue", required=True)
    experiment.add_argument("--project", required=True)
    experiment.add_argument("--walltime", required=True)
    experiment.add_argument("--ncpus", type=int, required=True)
    experiment.add_argument("--ngpus", type=int, default=0)
    experiment.add_argument("--mem-gb", type=int, required=True)
    experiment.add_argument("--jobfs-gb", type=int, required=True)
    experiment.add_argument("--image")
    experiment.add_argument("--expected-files", type=int, required=True)
    experiment.add_argument("--success-file", required=True)
    experiment.add_argument("--depends-on", action="append", default=[])
    experiment.add_argument("--command-json", required=True, help="JSON array of command arguments; no shell evaluation")
    experiment.set_defaults(func=cmd_experiment_add)

    submit = sub.add_parser("submit", help="preview or submit a registered batch experiment")
    submit.add_argument("root")
    submit.add_argument("--id", required=True)
    submit.add_argument("--execute", action="store_true", help="submit after validation; preview is default")
    submit.set_defaults(func=cmd_submit)

    external = sub.add_parser("external-submit", help="submit a linted environment-build or data-acquisition PBS script")
    external.add_argument("root")
    external.add_argument("--id", required=True)
    external.add_argument("--stage", choices=("environment", "data"), required=True)
    external.add_argument("--pbs", required=True)
    external.add_argument("--success-path", required=True)
    external.add_argument("--expected-files", type=int, required=True)
    external.add_argument("--execute", action="store_true", help="submit after validation; preview is default")
    external.set_defaults(func=cmd_external_submit)

    interactive = sub.add_parser("interactive", help="preview or start a registered tmux-backed qsub -I experiment")
    interactive.add_argument("root")
    interactive.add_argument("--id", required=True)
    interactive.add_argument("--session")
    interactive.add_argument("--execute", action="store_true", help="start tmux qsub -I after validation")
    interactive.set_defaults(func=cmd_interactive)

    interactive_run = sub.add_parser("interactive-run", help="run the registered command in interactive PBS jobfs")
    interactive_run.add_argument("root")
    interactive_run.add_argument("--id", required=True)
    interactive_run.set_defaults(func=cmd_interactive_run)

    interactive_publish = sub.add_parser("interactive-publish", help="atomically publish compact interactive output from jobfs")
    interactive_publish.add_argument("root")
    interactive_publish.add_argument("--id", required=True)
    interactive_publish.set_defaults(func=cmd_interactive_publish)

    close = sub.add_parser("interactive-close", help="close and account for an interactive attempt")
    close.add_argument("root")
    close.add_argument("--id", required=True)
    close.add_argument("--outcome", choices=("completed", "failed", "cancelled"), required=True)
    close.add_argument("--actual-walltime", required=True)
    close.set_defaults(func=cmd_interactive_close)

    cancel = sub.add_parser("cancel", help="cancel only the latest recorded active PBS job; preview is default")
    cancel.add_argument("root")
    cancel.add_argument("--id", required=True)
    cancel.add_argument("--execute", action="store_true")
    cancel.set_defaults(func=cmd_cancel)

    refresh = sub.add_parser("refresh", help="refresh all active PBS jobs with a ten-minute rate guard")
    refresh.add_argument("root")
    refresh.set_defaults(func=cmd_refresh)

    worker = sub.add_parser("worker-run", help="internal PBS worker entrypoint")
    worker.add_argument("root")
    worker.add_argument("--id", required=True)
    worker.set_defaults(func=cmd_worker_run)

    handoff = sub.add_parser("handoff", help="persist the controller's next action, pause, stop, or completion")
    handoff.add_argument("root")
    handoff.add_argument("--state", choices=("needs_agent", "waiting_pbs", "waiting_human", "waiting_time", "paused", "stopped", "complete"), required=True)
    handoff.add_argument("--reason", required=True)
    handoff.add_argument("--wake-at")
    handoff.set_defaults(func=cmd_handoff)

    resume = sub.add_parser("resume", help="resume a paused or explicitly stopped approved campaign")
    resume.add_argument("root")
    resume.add_argument("--reason", required=True)
    resume.set_defaults(func=cmd_resume)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        compute_side_commands = {"worker-run", "interactive-run", "interactive-publish"}
        if os.environ.get("PBS_JOBID") and args.command_name not in compute_side_commands:
            raise CampaignError(
                f"{args.command_name} is a control-host command and cannot run inside PBS"
            )
        args.func(args)
    except (CampaignError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
