#!/usr/bin/env python3
"""Regression tests for the run-on-gadi PBS policy linter."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "lint_pbs.py"
SPEC = importlib.util.spec_from_file_location("run_on_gadi_lint", SCRIPT)
assert SPEC and SPEC.loader
LINTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LINTER)


BASE = """#!/usr/bin/env bash
#PBS -P wa66
#PBS -q normal
#PBS -N lint-test
#PBS -l ncpus=4
#PBS -l mem=8GB
#PBS -l jobfs=20GB
#PBS -l walltime=01:00:00
#PBS -l storage=gdata/wa66
#PBS -l wd
#PBS -j oe
#PBS -o /g/data/wa66/Xiangyu/Result_lint/pbs.log

set -euo pipefail
export TMPDIR="$PBS_JOBFS/tmp"
export HF_HOME="$PBS_JOBFS/cache/hf"
export HUGGINGFACE_HUB_CACHE="$HF_HOME/hub"
RUNNER=/g/data/wa66/Xiangyu/.codex/skills/run-on-gadi/scripts/run_sqsh.sh
bash "$RUNNER" image.sqsh /env/bin/python /absolute/code.py
"""


class LintTests(unittest.TestCase):
    def lint_text(self, text: str) -> tuple[list[str], list[str], dict[str, object]]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "job.pbs"
            path.write_text(text, encoding="utf-8")
            return LINTER.lint(path)

    def assert_error_contains(self, text: str, fragment: str) -> None:
        errors, _, _ = self.lint_text(text)
        self.assertTrue(
            any(fragment in error for error in errors),
            f"missing {fragment!r} in errors: {errors}",
        )

    def test_valid_cpu_job_and_dependent_cache(self) -> None:
        errors, _, summary = self.lint_text(BASE)
        self.assertEqual(errors, [])
        self.assertEqual(summary["queue"], "normal")

    def test_codex_workload_destination_is_rejected(self) -> None:
        self.assert_error_contains(
            BASE + "OUTPUT=/g/data/wa66/Xiangyu/.codex/model.bin\n",
            "only read-only",
        )

    def test_home_log_is_rejected(self) -> None:
        text = BASE.replace(
            "/g/data/wa66/Xiangyu/Result_lint/pbs.log",
            "/home/561/xz4320/pbs.log",
        )
        self.assert_error_contains(text, "logs must be stored")

    def test_codex_log_is_rejected(self) -> None:
        text = BASE.replace(
            "/g/data/wa66/Xiangyu/Result_lint/pbs.log",
            "/g/data/wa66/Xiangyu/.codex/pbs.log",
        )
        self.assert_error_contains(text, "protected non-result location")

    def test_home_cache_is_rejected(self) -> None:
        self.assert_error_contains(
            BASE + "export PIP_CACHE_DIR=/home/561/xz4320/.cache/pip\n",
            "PIP_CACHE_DIR must resolve under $PBS_JOBFS",
        )

    def test_direct_package_install_is_rejected(self) -> None:
        self.assert_error_contains(BASE + "python -m pip install torch\n", "do not install")

    def test_persistent_download_tree_is_rejected(self) -> None:
        self.assert_error_contains(
            BASE + "DOWNLOAD_ROOT=/g/data/wa66/Xiangyu/Data/expanded\n",
            "DOWNLOAD_ROOT is transient",
        )

    def test_network_requires_copyq(self) -> None:
        text = BASE + 'curl -o "$PBS_JOBFS/source" https://example.invalid/data\n'
        self.assert_error_contains(text, "network/download commands require copyq")

    def test_network_is_allowed_on_copyq(self) -> None:
        text = BASE.replace("#PBS -q normal", "#PBS -q copyq").replace(
            "#PBS -l ncpus=4", "#PBS -l ncpus=1"
        )
        text += 'curl -o "$PBS_JOBFS/source" https://example.invalid/data\n'
        errors, _, summary = self.lint_text(text)
        self.assertEqual(errors, [])
        self.assertEqual(summary["queue"], "copyq")

    def test_h200_walltime_tier_is_enforced(self) -> None:
        text = (
            BASE.replace("#PBS -q normal", "#PBS -q gpuhopper")
            .replace("#PBS -l ncpus=4", "#PBS -l ncpus=12\n#PBS -l ngpus=1")
            .replace("#PBS -l mem=8GB", "#PBS -l mem=128GB")
            .replace("#PBS -l jobfs=20GB", "#PBS -l jobfs=500GB")
            .replace("#PBS -l walltime=01:00:00", "#PBS -l walltime=49:00:00")
        )
        self.assert_error_contains(text, "exceeds 48h tier")

    def test_unknown_project_is_rejected(self) -> None:
        self.assert_error_contains(
            BASE.replace("#PBS -P wa66", "#PBS -P zz99"),
            "not in this skill's authorised set",
        )

    def test_wa66_mount_is_required(self) -> None:
        self.assert_error_contains(
            BASE.replace("#PBS -l storage=gdata/wa66\n", ""),
            "does not request storage=gdata/wa66",
        )


if __name__ == "__main__":
    unittest.main()
