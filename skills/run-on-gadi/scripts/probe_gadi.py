#!/usr/bin/env python3
"""Read-only preflight for the account-specific NCI Gadi skill."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
from pathlib import Path


DEFAULT_PROJECTS = ("wa66", "ey69", "po67", "iv96")
PERSISTENT_ROOT = Path("/g/data/wa66/Xiangyu")
CODEX_ROOT = PERSISTENT_ROOT / ".codex"
ENV_ROOT = PERSISTENT_ROOT / "enviroment_cache"
DATA_ROOT = PERSISTENT_ROOT / "Data"
SKILL_ROOT = CODEX_ROOT / "skills" / "run-on-gadi"


def run(command: list[str]) -> dict[str, object]:
    try:
        proc = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"command": command, "returncode": 127, "stdout": "", "stderr": str(exc)}
    return {
        "command": command,
        "returncode": proc.returncode,
        "stdout": proc.stdout.rstrip(),
        "stderr": proc.stderr.rstrip(),
    }


def path_status(path: Path, purpose: str, workload_writable: bool) -> dict[str, object]:
    return {
        "path": str(path),
        "purpose": purpose,
        "exists": path.exists(),
        "writable": os.access(path, os.W_OK) if path.exists() else False,
        "workload_writable": workload_writable,
    }


def startup_jobfs_references() -> list[dict[str, object]]:
    references: list[dict[str, object]] = []
    for path in (Path.home() / ".bashrc", Path.home() / ".bash_profile", Path.home() / ".profile"):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line_number, line in enumerate(lines, 1):
            if "/jobfs/" in line and not line.lstrip().startswith("#"):
                references.append({"path": str(path), "line": line_number})
    return references


def collect(projects: list[str], include_queues: bool) -> dict[str, object]:
    hostname = socket.getfqdn()
    report: dict[str, object] = {
        "hostname": hostname,
        "is_gadi": hostname.startswith("gadi-") or hostname.endswith(".gadi.nci.org.au"),
        "user": os.environ.get("USER", ""),
        "cwd": os.getcwd(),
        "policy": {
            "codex_root": str(CODEX_ROOT),
            "codex_home_env": os.environ.get("CODEX_HOME", ""),
            "codex_root_workload_writable": False,
            "persistent_root": str(PERSISTENT_ROOT),
            "expanded_artifacts_root": "$PBS_JOBFS",
        },
        "paths": [
            path_status(CODEX_ROOT, "Codex configuration and skills only", False),
            path_status(SKILL_ROOT, "Installed run-on-gadi skill", False),
            path_status(ENV_ROOT, "Single-file .sqsh environments", True),
            path_status(DATA_ROOT, "Packed datasets, approved model archives, and manifests", True),
        ],
        "startup_jobfs_references": startup_jobfs_references(),
        "groups": run(["id", "-nG"]),
        "home_quota": run(["quota", "-s"]),
        "projects": {project: run(["nci_account", "-P", project]) for project in projects},
    }
    if include_queues:
        report["queues"] = run(["qstat", "-Q"])
    return report


def print_human(report: dict[str, object]) -> None:
    print(f"Gadi preflight for {report['user']} on {report['hostname']}")
    print(f"Cluster identity: {'OK' if report['is_gadi'] else 'NOT GADI'}")
    print()
    print("Storage policy:")
    print(f"  Codex-only, never workload output: {CODEX_ROOT}")
    print(f"  Frozen environments:             {ENV_ROOT}")
    print(f"  Packed datasets/models:          {DATA_ROOT}")
    print("  Expanded envs/downloads/caches:  $PBS_JOBFS")
    for item in report["paths"]:
        state = "exists" if item["exists"] else "MISSING"
        host_access = "host writable" if item["writable"] else "host not writable"
        policy = (
            "workload writes allowed"
            if item["workload_writable"]
            else "WORKLOAD WRITES FORBIDDEN"
        )
        print(f"  [{state}, {host_access}, {policy}] {item['path']}")
    if report["policy"]["codex_home_env"]:
        print(f"  CODEX_HOME:                       {report['policy']['codex_home_env']}")

    stale_references = report["startup_jobfs_references"]
    if stale_references:
        print("\nWARNING: shell startup files reference expired /jobfs paths:")
        for item in stale_references:
            print(f"  {item['path']}:{item['line']}")
        print("  PBS_JOBFS is deleted after a job; do not persist its paths in shell startup files.")

    groups = report["groups"]
    print("\nGroups:")
    print(groups["stdout"] or groups["stderr"])

    quota = report["home_quota"]
    print("\nHOME quota:")
    print(quota["stdout"] or quota["stderr"])

    print("\nDynamic project reports:")
    for project, result in report["projects"].items():
        print(f"\n--- {project} ---")
        print(result["stdout"] or result["stderr"])
        if "Over " in str(result["stdout"]):
            print(f"WARNING: {project} reports an exceeded storage quota.")

    queues = report.get("queues")
    if queues:
        print("\nPBS queues:")
        print(queues["stdout"] or queues["stderr"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projects", nargs="+", default=list(DEFAULT_PROJECTS))
    parser.add_argument("--queues", action="store_true", help="also query qstat -Q once")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    report = collect(args.projects, args.queues)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_human(report)
    return 0 if report["is_gadi"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
