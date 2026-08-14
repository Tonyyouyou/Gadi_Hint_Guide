#!/usr/bin/env python3
"""Download an immutable public Hugging Face model snapshot into PBS jobfs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any


DEFAULT_BASE_URL = "https://huggingface.co"
REVISION = re.compile(r"^[0-9a-fA-F]{40}$")
REPO_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
CHUNK_BYTES = 8 * 1024 * 1024


class DownloadError(RuntimeError):
    """The immutable snapshot could not be validated or downloaded."""


def request_headers() -> dict[str, str]:
    headers = {"User-Agent": "run-on-gadi-packed-model/1"}
    token = os.environ.get("HF_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_json(url: str, headers: dict[str, str], retries: int) -> dict[str, Any]:
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=headers), timeout=120
            ) as response:
                payload = json.load(response)
            if not isinstance(payload, dict):
                raise DownloadError("Hugging Face metadata response is not an object")
            return payload
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            if attempt + 1 == retries:
                raise DownloadError(f"metadata request failed after {retries} attempts: {exc}") from exc
            time.sleep(min(30, 2**attempt))
    raise AssertionError("unreachable")


def safe_member(destination: Path, name: str) -> Path:
    member = PurePosixPath(name)
    if not name or member.is_absolute() or ".." in member.parts or "\x00" in name:
        raise DownloadError(f"unsafe repository member: {name!r}")
    target = (destination / Path(*member.parts)).resolve()
    try:
        target.relative_to(destination)
    except ValueError as exc:
        raise DownloadError(f"repository member escapes destination: {name!r}") from exc
    return target


def expected_size(sibling: dict[str, Any]) -> int | None:
    lfs = sibling.get("lfs")
    value = lfs.get("size") if isinstance(lfs, dict) else sibling.get("size")
    return int(value) if isinstance(value, int) and value >= 0 else None


def expected_sha256(sibling: dict[str, Any]) -> str | None:
    lfs = sibling.get("lfs")
    value = lfs.get("sha256") if isinstance(lfs, dict) else None
    return value.lower() if isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{64}", value) else None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_download(path: Path, sibling: dict[str, Any]) -> None:
    size = expected_size(sibling)
    if size is not None and path.stat().st_size != size:
        raise DownloadError(f"size mismatch for {path.name}: {path.stat().st_size} != {size}")
    sha256 = expected_sha256(sibling)
    if sha256 is not None and sha256_file(path) != sha256:
        raise DownloadError(f"SHA-256 mismatch for {path.name}")


def download_file(
    url: str,
    target: Path,
    sibling: dict[str, Any],
    headers: dict[str, str],
    retries: int,
) -> None:
    if target.is_file():
        try:
            validate_download(target, sibling)
            return
        except DownloadError:
            target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f".{target.name}.partial")
    for attempt in range(retries):
        start = partial.stat().st_size if partial.exists() else 0
        current_headers = dict(headers)
        if start:
            current_headers["Range"] = f"bytes={start}-"
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=current_headers), timeout=300
            ) as response:
                append = start > 0 and getattr(response, "status", None) == 206
                with partial.open("ab" if append else "wb") as handle:
                    while chunk := response.read(CHUNK_BYTES):
                        handle.write(chunk)
            validate_download(partial, sibling)
            os.replace(partial, target)
            return
        except (OSError, urllib.error.URLError, DownloadError) as exc:
            if isinstance(exc, DownloadError):
                partial.unlink(missing_ok=True)
            if attempt + 1 == retries:
                partial.unlink(missing_ok=True)
                raise DownloadError(f"download failed for {target.name}: {exc}") from exc
            time.sleep(min(30, 2**attempt))


def download_snapshot(
    repo: str,
    revision: str,
    destination: Path,
    *,
    base_url: str = DEFAULT_BASE_URL,
    retries: int = 5,
) -> dict[str, Any]:
    if not REPO_ID.fullmatch(repo):
        raise DownloadError("repo must have the form owner/name")
    if not REVISION.fullmatch(revision):
        raise DownloadError("revision must be an immutable 40-character hexadecimal commit")
    jobfs_value = os.environ.get("PBS_JOBFS")
    if not jobfs_value:
        raise DownloadError("PBS_JOBFS is required")
    jobfs = Path(jobfs_value).resolve(strict=True)
    destination = destination.resolve()
    try:
        destination.relative_to(jobfs)
    except ValueError as exc:
        raise DownloadError(f"destination must be beneath PBS_JOBFS: {destination}") from exc
    destination.mkdir(parents=True, exist_ok=True)

    headers = request_headers()
    quoted_repo = urllib.parse.quote(repo, safe="/")
    quoted_revision = urllib.parse.quote(revision, safe="")
    metadata_url = f"{base_url}/api/models/{quoted_repo}/revision/{quoted_revision}?blobs=true"
    metadata = fetch_json(metadata_url, headers, retries)
    if str(metadata.get("sha", "")).lower() != revision.lower():
        raise DownloadError("metadata did not resolve to the requested immutable revision")
    siblings = metadata.get("siblings")
    if not isinstance(siblings, list) or not siblings or len(siblings) > 10000:
        raise DownloadError("model repository has an invalid or excessive sibling list")
    if any(
        not isinstance(sibling, dict) or not isinstance(sibling.get("rfilename"), str)
        for sibling in siblings
    ):
        raise DownloadError("model repository has invalid sibling metadata")

    records = []
    for sibling in sorted(siblings, key=lambda item: str(item.get("rfilename", ""))):
        name = sibling["rfilename"]
        if name == "HF_SNAPSHOT_MANIFEST.json":
            raise DownloadError("model repository collides with the reserved snapshot manifest")
        target = safe_member(destination, name)
        quoted_name = urllib.parse.quote(name, safe="/")
        url = f"{base_url}/{quoted_repo}/resolve/{quoted_revision}/{quoted_name}?download=true"
        download_file(url, target, sibling, headers, retries)
        records.append(
            {
                "path": name,
                "bytes": target.stat().st_size,
                "sha256": sha256_file(target),
                "upstream_lfs_sha256": expected_sha256(sibling),
            }
        )

    manifest = {
        "format": "run-on-gadi-hf-snapshot-v1",
        "repo": repo,
        "revision": revision.lower(),
        "files": records,
    }
    temporary = destination / ".HF_SNAPSHOT_MANIFEST.json.partial"
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, destination / "HF_SNAPSHOT_MANIFEST.json")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.retries < 1 or args.retries > 10:
        raise DownloadError("retries must be between 1 and 10")
    if args.base_url != DEFAULT_BASE_URL and os.environ.get("RUN_ON_GADI_TESTING") != "1":
        raise DownloadError("base-url override is test-only")
    manifest = download_snapshot(
        args.repo,
        args.revision,
        Path(args.destination),
        base_url=args.base_url.rstrip("/"),
        retries=args.retries,
    )
    print(json.dumps({"repo": manifest["repo"], "revision": manifest["revision"], "files": len(manifest["files"])}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DownloadError as exc:
        print(f"ERROR: {exc}", file=os.sys.stderr)
        raise SystemExit(2)
