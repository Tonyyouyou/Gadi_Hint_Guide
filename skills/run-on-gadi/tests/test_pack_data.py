#!/usr/bin/env python3
"""Functional tests for inode-safe dataset and model packing."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pack_data.sh"


class PackDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.jobfs = self.base / "jobfs"
        self.persistent = self.base / "Xiangyu"
        self.source = self.jobfs / "download" / "model"
        self.source.mkdir(parents=True)
        self.persistent.mkdir()
        (self.source / "config.json").write_text('{"model_type":"test"}\n', encoding="utf-8")
        (self.source / "weights.safetensors").write_bytes(b"weights")
        self.env = {
            **os.environ,
            "PBS_JOBFS": str(self.jobfs),
            "PBS_JOBID": "123.test",
            "PBS_NCPUS": "1",
            "RUN_ON_GADI_TESTING": "1",
            "RUN_ON_GADI_PERSISTENT_ROOT": str(self.persistent),
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_packer(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "bash",
                str(SCRIPT),
                "--kind",
                "model",
                "--name",
                "public-model",
                "--tag",
                "deadbeef",
                "--source",
                str(self.source),
                "--source-uri",
                "https://huggingface.co/example/public-model",
                "--source-revision",
                "a" * 40,
                "--license",
                "Apache-2.0",
                *extra,
            ],
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_model_is_one_archive_with_immutable_provenance(self) -> None:
        result = self.run_packer()
        self.assertEqual(result.returncode, 0, result.stderr)
        archive = self.persistent / "Data" / "models" / "public-model-deadbeef.tar.zst"
        self.assertTrue(archive.is_file())
        self.assertEqual(list((self.persistent / "Data" / "models").iterdir()), [archive])
        manifest = subprocess.run(
            [
                "bash",
                "-c",
                'zstd --quiet --decompress --stdout "$1" | tar --extract --to-stdout --file=- RUN_ON_GADI_MANIFEST.json',
                "bash",
                str(archive),
            ],
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(manifest.stdout)
        self.assertEqual(payload["format"], "run-on-gadi-model-v1")
        self.assertEqual(payload["source_revision"], "a" * 40)
        self.assertEqual(payload["license"], "Apache-2.0")
        self.assertEqual(payload["files"], 2)
        self.assertEqual(payload["symlinks"], 0)

    def test_model_dry_run_does_not_create_persistent_directory(self) -> None:
        result = self.run_packer("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.persistent / "Data").exists())

    def test_model_rejects_mutable_revision_and_symlinks(self) -> None:
        mutable = subprocess.run(
            [
                "bash",
                str(SCRIPT),
                "--kind",
                "model",
                "--name",
                "public-model",
                "--source",
                str(self.source),
                "--source-uri",
                "https://huggingface.co/example/public-model",
                "--source-revision",
                "main",
                "--license",
                "Apache-2.0",
            ],
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(mutable.returncode, 0)
        self.assertIn("immutable", mutable.stderr)

        (self.source / "linked-weights").symlink_to(self.source / "weights.safetensors")
        linked = self.run_packer()
        self.assertNotEqual(linked.returncode, 0)
        self.assertIn("cannot contain symlinks", linked.stderr)


if __name__ == "__main__":
    unittest.main()
