#!/usr/bin/env python3
"""Tests for immutable Hugging Face snapshot acquisition."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "download_hf_snapshot.py"
SPEC = importlib.util.spec_from_file_location("download_hf_snapshot", SCRIPT)
assert SPEC and SPEC.loader
DOWNLOADER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DOWNLOADER)


class SnapshotHandler(BaseHTTPRequestHandler):
    revision = "a" * 40
    files = {
        "config.json": b'{"model_type":"test"}\n',
        "weights/model.safetensors": b"immutable-weights",
    }

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        route = self.path.split("?", 1)[0]
        metadata_route = f"/api/models/example/model/revision/{self.revision}"
        if route == metadata_route:
            weights = self.files["weights/model.safetensors"]
            payload = {
                "sha": self.revision,
                "siblings": [
                    {"rfilename": "config.json", "size": len(self.files["config.json"])},
                    {
                        "rfilename": "weights/model.safetensors",
                        "lfs": {
                            "size": len(weights),
                            "sha256": hashlib.sha256(weights).hexdigest(),
                        },
                    },
                ],
            }
            body = json.dumps(payload).encode()
        else:
            prefix = f"/example/model/resolve/{self.revision}/"
            if not route.startswith(prefix):
                self.send_error(404)
                return
            name = route.removeprefix(prefix)
            try:
                body = self.files[name]
            except KeyError:
                self.send_error(404)
                return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class DownloadSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.jobfs = Path(self.temp.name) / "jobfs"
        self.jobfs.mkdir()
        self.old_jobfs = os.environ.get("PBS_JOBFS")
        os.environ["PBS_JOBFS"] = str(self.jobfs)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), SnapshotHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        if self.old_jobfs is None:
            os.environ.pop("PBS_JOBFS", None)
        else:
            os.environ["PBS_JOBFS"] = self.old_jobfs
        self.temp.cleanup()

    def test_downloads_exact_revision_and_records_file_hashes(self) -> None:
        destination = self.jobfs / "download" / "model"
        manifest = DOWNLOADER.download_snapshot(
            "example/model",
            SnapshotHandler.revision,
            destination,
            base_url=f"http://127.0.0.1:{self.server.server_port}",
            retries=1,
        )
        self.assertEqual(manifest["revision"], SnapshotHandler.revision)
        self.assertEqual(len(manifest["files"]), 2)
        self.assertEqual(
            (destination / "weights" / "model.safetensors").read_bytes(),
            SnapshotHandler.files["weights/model.safetensors"],
        )
        recorded = json.loads((destination / "HF_SNAPSHOT_MANIFEST.json").read_text())
        self.assertEqual(recorded, manifest)
        self.assertFalse(any(path.is_symlink() for path in destination.rglob("*")))

    def test_rejects_mutable_revision_and_traversal(self) -> None:
        with self.assertRaisesRegex(DOWNLOADER.DownloadError, "immutable"):
            DOWNLOADER.download_snapshot(
                "example/model",
                "main",
                self.jobfs / "download" / "model",
                base_url=f"http://127.0.0.1:{self.server.server_port}",
                retries=1,
            )
        with self.assertRaisesRegex(DOWNLOADER.DownloadError, "unsafe"):
            DOWNLOADER.safe_member(self.jobfs, "../outside")


if __name__ == "__main__":
    unittest.main()
