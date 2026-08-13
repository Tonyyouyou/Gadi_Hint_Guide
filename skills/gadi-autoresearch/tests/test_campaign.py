#!/usr/bin/env python3
"""Unit tests for the inode-safe autoresearch campaign guard."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "campaign.py"
SPEC = importlib.util.spec_from_file_location("gadi_autoresearch_campaign", SCRIPT)
assert SPEC and SPEC.loader
CAMPAIGN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CAMPAIGN)


class CampaignTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.persistent = self.base / "Xiangyu"
        self.result_parent = self.persistent / "Result_Test"
        self.env_root = self.persistent / "enviroment_cache"
        self.data_root = self.persistent / "Data"
        self.codex_root = self.persistent / ".codex"
        self.workspace = self.persistent / "workspace"
        for path in (self.result_parent, self.env_root, self.data_root, self.codex_root, self.workspace):
            path.mkdir(parents=True)
        self.image = self.env_root / "test.sqsh"
        self.image.write_bytes(b"sqsh")
        self.data = self.data_root / "data.tar.zst"
        self.data.write_bytes(b"data")
        (self.workspace / "train.py").write_text("print('test')\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(self.workspace)], check=True)
        subprocess.run(["git", "-C", str(self.workspace), "add", "train.py"], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.workspace),
                "-c",
                "user.name=Unit Test",
                "-c",
                "user.email=unit@example.invalid",
                "commit",
                "-qm",
                "initial",
            ],
            check=True,
        )
        self.root = self.result_parent / "campaign"
        self.bin_dir = self.base / "bin"
        self.bin_dir.mkdir()
        self.qsub_log = self.base / "qsub.log"
        self.qdel_log = self.base / "qdel.log"
        self.qstat_output = self.base / "qstat.out"
        self.write_fake_commands()
        self.old_env = os.environ.copy()
        os.environ.update(
            {
                "GADI_AUTORESEARCH_TESTING": "1",
                "GADI_AUTORESEARCH_TEST_ROOT": str(self.persistent),
                "PATH": f"{self.bin_dir}{os.pathsep}{self.old_env['PATH']}",
                "QSUB_LOG": str(self.qsub_log),
                "QDEL_LOG": str(self.qdel_log),
                "QSTAT_OUTPUT": str(self.qstat_output),
            }
        )

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.old_env)
        self.temp.cleanup()

    def write_fake_commands(self) -> None:
        commands = {
            "id": "#!/bin/sh\nprintf '%s\\n' 'wa66 ey69 po67 iv96'\n",
            "nci_account": (
                "#!/bin/sh\n"
                "cat <<'EOF'\n"
                "Usage Report: Project=test Period=2026.q3\n"
                "Avail: 10.00 KSU\n"
                "Filesystem Used iUsed Allocation iAllocation\n"
                "gdata7 1.00 TiB 10.00 K 10.00 TiB 1.00 M\n"
                "EOF\n"
            ),
            "qsub": "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$QSUB_LOG\"\nprintf '%s\\n' '12345.gadi-pbs'\n",
            "qdel": "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$QDEL_LOG\"\n",
            "qstat": "#!/bin/sh\ncat \"$QSTAT_OUTPUT\"\n",
        }
        for name, content in commands.items():
            path = self.bin_dir / name
            path.write_text(content, encoding="utf-8")
            path.chmod(0o755)

    def call(self, *args: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = CAMPAIGN.main(list(args))
        return result, stdout.getvalue(), stderr.getvalue()

    def init(self, *, max_files: int = 64, max_su: int = 500) -> None:
        code, _, error = self.call(
            "init",
            str(self.root),
            "--campaign-id",
            "test-campaign",
            "--idea",
            "test a broad idea",
            "--workspace",
            str(self.workspace),
            "--projects",
            "wa66,ey69",
            "--max-su",
            str(max_su),
            "--max-files",
            str(max_files),
            "--deadline",
            "2099-01-01T00:00:00Z",
            "--environment",
            str(self.image),
            "--data",
            str(self.data),
        )
        self.assertEqual(code, 0, error)

    def approve(self, *, allow_cancel: bool = False, allow_storage: bool = False) -> None:
        arguments = [
            "approve",
            str(self.root),
            "--by",
            "unit-test",
            "--allow-auto-submit",
            "--allow-interactive",
            "--allow-auto-agent",
        ]
        if allow_cancel:
            arguments.append("--allow-auto-cancel")
        if allow_storage:
            arguments.append("--allow-storage-publish")
        code, _, error = self.call(*arguments)
        self.assertEqual(code, 0, error)

    def add_sanity(self, *, expected_files: int = 8) -> tuple[int, str, str]:
        return self.call(
            "experiment-add",
            str(self.root),
            "--id",
            "sanity-001",
            "--stage",
            "sanity",
            "--mode",
            "batch",
            "--queue",
            "gpuhopper",
            "--project",
            "wa66",
            "--walltime",
            "00:15:00",
            "--ncpus",
            "12",
            "--ngpus",
            "1",
            "--mem-gb",
            "64",
            "--jobfs-gb",
            "100",
            "--expected-files",
            str(expected_files),
            "--success-file",
            "metrics.json",
            "--command-json",
            '["/env/bin/python","{WORKSPACE}/train.py","--output","{RESULT_DIR}/metrics.json"]',
        )

    def add_interactive(self, *, ncpus: int = 12) -> tuple[int, str, str]:
        return self.call(
            "experiment-add",
            str(self.root),
            "--id",
            "debug-001",
            "--stage",
            "sanity",
            "--mode",
            "interactive",
            "--queue",
            "gpuhopper",
            "--project",
            "wa66",
            "--walltime",
            "04:00:00",
            "--ncpus",
            str(ncpus),
            "--ngpus",
            "1",
            "--mem-gb",
            "64",
            "--jobfs-gb",
            "100",
            "--expected-files",
            "4",
            "--success-file",
            "metrics.json",
            "--command-json",
            '["/env/bin/python","{WORKSPACE}/train.py","--output","{RESULT_DIR}/metrics.json"]',
        )

    def test_init_creates_compact_draft_state(self) -> None:
        self.init()
        state = CAMPAIGN.load_state(self.root)
        self.assertEqual(state["status"], "draft")
        self.assertEqual(state["control"]["state"], "waiting_human")
        self.assertEqual(CAMPAIGN.count_entries(self.root), 2)

    def test_campaign_root_under_codex_is_rejected(self) -> None:
        bad = self.codex_root / "Result_bad" / "campaign"
        code, _, error = self.call(
            "init",
            str(bad),
            "--campaign-id",
            "bad-campaign",
            "--idea",
            "bad",
            "--workspace",
            str(self.workspace),
            "--deadline",
            "2099-01-01T00:00:00Z",
        )
        self.assertNotEqual(code, 0)
        self.assertIn("Result*", error)

    def test_workspace_outside_persistent_root_is_rejected(self) -> None:
        outside = self.base / "outside-workspace"
        outside.mkdir()
        (outside / "train.py").write_text("print('outside')\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(outside)], check=True)
        subprocess.run(["git", "-C", str(outside), "add", "train.py"], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(outside),
                "-c",
                "user.name=Unit Test",
                "-c",
                "user.email=unit@example.invalid",
                "commit",
                "-qm",
                "initial",
            ],
            check=True,
        )
        code, _, error = self.call(
            "init",
            str(self.root),
            "--campaign-id",
            "outside-workspace",
            "--idea",
            "test",
            "--workspace",
            str(outside),
            "--deadline",
            "2099-01-01T00:00:00Z",
        )
        self.assertNotEqual(code, 0)
        self.assertIn("must stay under", error)

    def test_experiment_requires_approval(self) -> None:
        self.init()
        code, _, error = self.add_sanity()
        self.assertNotEqual(code, 0)
        self.assertIn("not approved", error)

    def test_interactive_profile_must_match_debug_helper(self) -> None:
        self.init()
        self.approve()
        code, _, error = self.add_interactive(ncpus=24)
        self.assertNotEqual(code, 0)
        self.assertIn("fixed debug profile", error)

    def test_experiment_registration_requires_clean_git_workspace(self) -> None:
        self.init()
        self.approve()
        dirty = self.workspace / "untracked.txt"
        dirty.write_text("not committed\n", encoding="utf-8")
        code, _, error = self.add_sanity()
        self.assertNotEqual(code, 0)
        self.assertIn("commit or deliberately discard", error)

    def test_registered_environment_image_cannot_change_before_submit(self) -> None:
        self.init()
        self.approve()
        self.assertEqual(self.add_sanity()[0], 0)
        self.image.write_bytes(b"changed-sqsh")
        code, _, error = self.call("submit", str(self.root), "--id", "sanity-001")
        self.assertNotEqual(code, 0)
        self.assertIn("changed after experiment registration", error)

    def test_registered_data_cannot_change_before_submit(self) -> None:
        self.init()
        self.approve()
        self.assertEqual(self.add_sanity()[0], 0)
        self.data.write_bytes(b"changed-data")
        code, _, error = self.call("submit", str(self.root), "--id", "sanity-001")
        self.assertNotEqual(code, 0)
        self.assertIn("data input changed after experiment registration", error)

    def test_interactive_campaign_ceiling_cannot_exceed_four_hours(self) -> None:
        code, _, error = self.call(
            "init",
            str(self.root),
            "--campaign-id",
            "bad-interactive-ceiling",
            "--idea",
            "test",
            "--workspace",
            str(self.workspace),
            "--max-interactive-walltime",
            "04:00:01",
            "--deadline",
            "2099-01-01T00:00:00Z",
        )
        self.assertNotEqual(code, 0)
        self.assertIn("cannot exceed 04:00:00", error)

    def test_preview_has_no_qsub_side_effect(self) -> None:
        self.init()
        self.approve()
        code, _, error = self.add_sanity()
        self.assertEqual(code, 0, error)
        with mock.patch.object(CAMPAIGN, "lint_script", return_value={"errors": [], "warnings": [], "summary": {}}):
            code, output, error = self.call("submit", str(self.root), "--id", "sanity-001")
        self.assertEqual(code, 0, error)
        self.assertIn("pbs_script", output)
        self.assertFalse(self.qsub_log.exists())
        self.assertEqual(CAMPAIGN.load_state(self.root)["experiments"]["sanity-001"]["attempts"], [])

    def test_submission_command_is_rejected_inside_pbs(self) -> None:
        self.init()
        self.approve()
        self.assertEqual(self.add_sanity()[0], 0)
        previous = os.environ.get("PBS_JOBID")
        os.environ["PBS_JOBID"] = "99999.gadi-pbs"
        try:
            code, _, error = self.call("submit", str(self.root), "--id", "sanity-001", "--execute")
        finally:
            if previous is None:
                os.environ.pop("PBS_JOBID", None)
            else:
                os.environ["PBS_JOBID"] = previous
        self.assertNotEqual(code, 0)
        self.assertIn("control-host command", error)
        self.assertFalse(self.qsub_log.exists())

    def test_execute_records_job_and_budget(self) -> None:
        self.init()
        self.approve()
        self.assertEqual(self.add_sanity()[0], 0)
        with mock.patch.object(CAMPAIGN, "lint_script", return_value={"errors": [], "warnings": [], "summary": {}}):
            code, output, error = self.call("submit", str(self.root), "--id", "sanity-001", "--execute")
        self.assertEqual(code, 0, error)
        self.assertIn("12345.gadi-pbs", output)
        self.assertTrue(self.qsub_log.exists())
        state = CAMPAIGN.load_state(self.root)
        attempt = state["experiments"]["sanity-001"]["attempts"][0]
        self.assertEqual(attempt["status"], "queued")
        self.assertGreater(CAMPAIGN.budget_summary(state)["committed_su"], 0)
        self.assertEqual(state["control"]["state"], "waiting_pbs")

    def test_main_experiment_requires_sanity_evidence(self) -> None:
        self.init()
        self.approve()
        code, _, error = self.call(
            "experiment-add",
            str(self.root),
            "--id",
            "main-001",
            "--stage",
            "main",
            "--mode",
            "batch",
            "--queue",
            "dgxa100",
            "--project",
            "ey69",
            "--walltime",
            "01:00:00",
            "--ncpus",
            "16",
            "--ngpus",
            "1",
            "--mem-gb",
            "128",
            "--jobfs-gb",
            "200",
            "--expected-files",
            "8",
            "--success-file",
            "metrics.json",
            "--command-json",
            '["/env/bin/python","{WORKSPACE}/train.py"]',
        )
        self.assertEqual(code, 0, error)
        with mock.patch.object(CAMPAIGN, "lint_script", return_value={"errors": [], "warnings": [], "summary": {}}):
            code, _, error = self.call("submit", str(self.root), "--id", "main-001")
        self.assertNotEqual(code, 0)
        self.assertIn("sanity", error)

    def test_expected_files_are_enforced_before_submission(self) -> None:
        self.init(max_files=8)
        self.approve()
        code, _, error = self.add_sanity(expected_files=20)
        self.assertNotEqual(code, 0)
        self.assertIn("file envelope", error)

    def test_workspace_file_growth_counts_against_campaign_envelope(self) -> None:
        self.init(max_files=12)
        self.approve()
        for index in range(5):
            (self.workspace / f"new-{index}.txt").write_text("x\n", encoding="utf-8")
        code, _, error = self.call("preflight", str(self.root))
        self.assertNotEqual(code, 0)
        self.assertIn("persistent-file envelope", error)

    def test_submission_is_rejected_when_maximum_charge_exceeds_su_envelope(self) -> None:
        self.init(max_su=10)
        self.approve()
        self.assertEqual(self.add_sanity()[0], 0)
        with mock.patch.object(CAMPAIGN, "lint_script", return_value={"errors": [], "warnings": [], "summary": {}}):
            code, _, error = self.call("submit", str(self.root), "--id", "sanity-001")
        self.assertNotEqual(code, 0)
        self.assertIn("SU envelope", error)

    def test_worker_requires_success_marker(self) -> None:
        self.init()
        self.approve()
        self.assertEqual(self.add_sanity()[0], 0)
        with mock.patch.object(CAMPAIGN, "lint_script", return_value={"errors": [], "warnings": [], "summary": {}}):
            self.assertEqual(self.call("submit", str(self.root), "--id", "sanity-001", "--execute")[0], 0)
        old_job = os.environ.get("PBS_JOBID")
        old_jobfs = os.environ.get("PBS_JOBFS")
        jobfs = self.base / "jobfs"
        jobfs.mkdir()
        os.environ.update({"PBS_JOBID": "12345.gadi-pbs", "PBS_JOBFS": str(jobfs)})
        try:
            with mock.patch.object(CAMPAIGN.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)):
                with self.assertRaises(SystemExit) as raised:
                    CAMPAIGN.cmd_worker_run(argparse_namespace(root=str(self.root), id="sanity-001"))
            self.assertEqual(raised.exception.code, 86)
        finally:
            if old_job is None:
                os.environ.pop("PBS_JOBID", None)
            else:
                os.environ["PBS_JOBID"] = old_job
            if old_jobfs is None:
                os.environ.pop("PBS_JOBFS", None)
            else:
                os.environ["PBS_JOBFS"] = old_jobfs
        state = CAMPAIGN.load_state(self.root)
        self.assertEqual(state["experiments"]["sanity-001"]["status"], "finishing")
        self.assertEqual(
            state["experiments"]["sanity-001"]["attempts"][-1]["worker_outcome"],
            "failed",
        )

    def test_worker_stages_in_jobfs_before_atomic_publication(self) -> None:
        self.init()
        self.approve()
        self.assertEqual(self.add_sanity()[0], 0)
        with mock.patch.object(CAMPAIGN, "lint_script", return_value={"errors": [], "warnings": [], "summary": {}}):
            self.assertEqual(self.call("submit", str(self.root), "--id", "sanity-001", "--execute")[0], 0)
        result_dir = self.root / "runs" / "sanity-001"
        self.assertFalse(result_dir.exists())
        jobfs = self.base / "jobfs-publish"
        jobfs.mkdir()
        old_job = os.environ.get("PBS_JOBID")
        old_jobfs = os.environ.get("PBS_JOBFS")
        os.environ.update({"PBS_JOBID": "12345.gadi-pbs", "PBS_JOBFS": str(jobfs)})
        real_run = subprocess.run

        def fake_runner(invocation: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            if not invocation or invocation[0] != "bash":
                return real_run(invocation, **kwargs)
            output = Path(invocation[-1])
            self.assertTrue(str(output).startswith(str(jobfs)))
            self.assertFalse(any(str(self.workspace) in argument for argument in invocation))
            self.assertTrue(any("gadi-autoresearch-source" in argument for argument in invocation))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text('{"status":"ok"}\n', encoding="utf-8")
            self.assertFalse(result_dir.exists())
            return subprocess.CompletedProcess(invocation, 0)

        try:
            with mock.patch.object(CAMPAIGN.subprocess, "run", side_effect=fake_runner):
                with self.assertRaises(SystemExit) as raised:
                    CAMPAIGN.cmd_worker_run(argparse_namespace(root=str(self.root), id="sanity-001"))
            self.assertEqual(raised.exception.code, 0)
        finally:
            if old_job is None:
                os.environ.pop("PBS_JOBID", None)
            else:
                os.environ["PBS_JOBID"] = old_job
            if old_jobfs is None:
                os.environ.pop("PBS_JOBFS", None)
            else:
                os.environ["PBS_JOBFS"] = old_jobfs
        self.assertEqual((result_dir / "metrics.json").read_text(encoding="utf-8"), '{"status":"ok"}\n')
        state = CAMPAIGN.load_state(self.root)
        self.assertEqual(state["experiments"]["sanity-001"]["status"], "finishing")
        self.assertEqual(state["experiments"]["sanity-001"]["attempts"][-1]["worker_outcome"], "completed")
        self.qstat_output.write_text(
            "Job Id: 12345.gadi-pbs\n"
            "    job_state = F\n"
            "    Exit_status = 0\n"
            "    resources_used.walltime = 00:02:00\n",
            encoding="utf-8",
        )
        self.assertEqual(self.call("refresh", str(self.root))[0], 0)
        self.assertEqual(
            CAMPAIGN.load_state(self.root)["experiments"]["sanity-001"]["status"],
            "completed",
        )

    def test_worker_file_overflow_is_never_published(self) -> None:
        self.init()
        self.approve()
        self.assertEqual(self.add_sanity(expected_files=2)[0], 0)
        with mock.patch.object(CAMPAIGN, "lint_script", return_value={"errors": [], "warnings": [], "summary": {}}):
            self.assertEqual(self.call("submit", str(self.root), "--id", "sanity-001", "--execute")[0], 0)
        result_dir = self.root / "runs" / "sanity-001"
        jobfs = self.base / "jobfs-overflow"
        jobfs.mkdir()
        old_job = os.environ.get("PBS_JOBID")
        old_jobfs = os.environ.get("PBS_JOBFS")
        os.environ.update({"PBS_JOBID": "12345.gadi-pbs", "PBS_JOBFS": str(jobfs)})
        real_run = subprocess.run

        def overflowing_runner(invocation: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            if not invocation or invocation[0] != "bash":
                return real_run(invocation, **kwargs)
            output = Path(invocation[-1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("ok\n", encoding="utf-8")
            (output.parent / "extra-1.txt").write_text("x\n", encoding="utf-8")
            (output.parent / "extra-2.txt").write_text("x\n", encoding="utf-8")
            return subprocess.CompletedProcess(invocation, 0)

        try:
            with mock.patch.object(CAMPAIGN.subprocess, "run", side_effect=overflowing_runner):
                with self.assertRaises(SystemExit) as raised:
                    CAMPAIGN.cmd_worker_run(argparse_namespace(root=str(self.root), id="sanity-001"))
            self.assertEqual(raised.exception.code, 87)
        finally:
            if old_job is None:
                os.environ.pop("PBS_JOBID", None)
            else:
                os.environ["PBS_JOBID"] = old_job
            if old_jobfs is None:
                os.environ.pop("PBS_JOBFS", None)
            else:
                os.environ["PBS_JOBFS"] = old_jobfs
        state = CAMPAIGN.load_state(self.root)
        self.assertFalse(result_dir.exists())
        self.assertEqual(state["status"], "paused")
        self.assertEqual(state["experiments"]["sanity-001"]["status"], "finishing")
        self.assertIn("exceeds declared limit", state["control"]["reason"])

    def test_interactive_run_publish_exit_close_lifecycle(self) -> None:
        self.init()
        self.approve()
        self.assertEqual(self.add_interactive()[0], 0)
        real_run = subprocess.run

        def start_helper(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            if command and command[0] == "bash":
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
            return real_run(command, **kwargs)

        with mock.patch.object(
            CAMPAIGN.subprocess,
            "run",
            side_effect=start_helper,
        ):
            code, _, error = self.call(
                "interactive",
                str(self.root),
                "--id",
                "debug-001",
                "--session",
                "debug-test",
                "--execute",
            )
        self.assertEqual(code, 0, error)
        jobfs = self.base / "interactive-jobfs"
        jobfs.mkdir()
        old_job = os.environ.get("PBS_JOBID")
        old_jobfs = os.environ.get("PBS_JOBFS")
        os.environ.update({"PBS_JOBID": "54321.gadi-pbs", "PBS_JOBFS": str(jobfs)})
        real_interactive_run = subprocess.run

        def fake_runner(invocation: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            if not invocation or invocation[0] != "bash":
                return real_interactive_run(invocation, **kwargs)
            output = Path(invocation[-1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("interactive-ok\n", encoding="utf-8")
            return subprocess.CompletedProcess(invocation, 0)

        try:
            with contextlib.redirect_stdout(io.StringIO()):
                with mock.patch.object(CAMPAIGN.subprocess, "run", side_effect=fake_runner):
                    CAMPAIGN.cmd_interactive_run(argparse_namespace(root=str(self.root), id="debug-001"))
                CAMPAIGN.cmd_interactive_publish(argparse_namespace(root=str(self.root), id="debug-001"))
        finally:
            if old_job is None:
                os.environ.pop("PBS_JOBID", None)
            else:
                os.environ["PBS_JOBID"] = old_job
            if old_jobfs is None:
                os.environ.pop("PBS_JOBFS", None)
            else:
                os.environ["PBS_JOBFS"] = old_jobfs
        self.assertEqual(
            self.call(
                "interactive-close",
                str(self.root),
                "--id",
                "debug-001",
                "--outcome",
                "completed",
                "--actual-walltime",
                "01:00:00",
            )[0],
            0,
        )
        state = CAMPAIGN.load_state(self.root)
        self.assertEqual(state["experiments"]["debug-001"]["status"], "completed")
        attempt = state["experiments"]["debug-001"]["attempts"][-1]
        self.assertEqual(attempt["actual_su_source"], "reported")
        self.assertEqual(
            CAMPAIGN.budget_summary(state)["committed_su"],
            state["experiments"]["debug-001"]["max_su"],
        )
        self.assertEqual(
            (self.root / "runs" / "debug-001" / "metrics.json").read_text(encoding="utf-8"),
            "interactive-ok\n",
        )

    def test_external_environment_job_is_previewed_and_tracked(self) -> None:
        self.init()
        self.approve(allow_storage=True)
        pbs = self.workspace / "build-env.pbs"
        success = self.env_root / "new-env.sqsh"
        pbs.write_text(
            "#!/usr/bin/env bash\n"
            "#PBS -P wa66\n#PBS -q copyq\n#PBS -N env\n"
            "#PBS -l ncpus=1\n#PBS -l mem=8GB\n#PBS -l jobfs=100GB\n"
            "#PBS -l walltime=01:00:00\n#PBS -l storage=gdata/wa66\n#PBS -l wd\n"
            f"#PBS -j oe\n#PBS -o {self.root}/build-env.log\n"
            "set -euo pipefail\nexport TMPDIR=\"$PBS_JOBFS/tmp\"\nmkdir -p \"$TMPDIR\"\n"
            "BUILDER=/g/data/wa66/Xiangyu/.codex/skills/run-on-gadi/scripts/build_conda_sqsh.sh\n"
            "bash \"$BUILDER\" --help\n",
            encoding="utf-8",
        )
        lint_report = {
            "errors": [],
            "warnings": [],
            "summary": {
                "project": "wa66",
                "queue": "copyq",
                "ncpus": 1,
                "ngpus": 0,
                "mem_gb": 8,
                "jobfs_gb": 100,
                "walltime_hours": 1.0,
            },
        }
        arguments = (
            "external-submit",
            str(self.root),
            "--id",
            "build-env-v2",
            "--stage",
            "environment",
            "--pbs",
            str(pbs),
            "--success-path",
            str(success),
            "--expected-files",
            "1",
        )
        with mock.patch.object(CAMPAIGN, "lint_script", return_value=lint_report):
            code, _, error = self.call(*arguments)
        self.assertEqual(code, 0, error)
        self.assertFalse(self.qsub_log.exists())
        with mock.patch.object(CAMPAIGN, "lint_script", return_value=lint_report):
            code, output, error = self.call(*arguments, "--execute")
        self.assertEqual(code, 0, error)
        self.assertIn("12345.gadi-pbs", output)
        state = CAMPAIGN.load_state(self.root)
        self.assertEqual(state["experiments"]["build-env-v2"]["mode"], "external")
        self.assertEqual(state["experiments"]["build-env-v2"]["status"], "queued")

    def test_refresh_obeys_ten_minute_guard(self) -> None:
        self.init()
        self.approve()
        self.assertEqual(self.add_sanity()[0], 0)
        with mock.patch.object(CAMPAIGN, "lint_script", return_value={"errors": [], "warnings": [], "summary": {}}):
            self.assertEqual(self.call("submit", str(self.root), "--id", "sanity-001", "--execute")[0], 0)
        self.qstat_output.write_text(
            "Job Id: 12345.gadi-pbs\n    job_state = R\n    resources_used.walltime = 00:01:00\n",
            encoding="utf-8",
        )
        self.assertEqual(self.call("refresh", str(self.root))[0], 0)
        code, _, error = self.call("refresh", str(self.root))
        self.assertNotEqual(code, 0)
        self.assertIn("once per 600 seconds", error)

    def test_cancel_targets_only_recorded_job_after_capability_grant(self) -> None:
        self.init()
        self.approve(allow_cancel=True)
        self.assertEqual(self.add_sanity()[0], 0)
        with mock.patch.object(CAMPAIGN, "lint_script", return_value={"errors": [], "warnings": [], "summary": {}}):
            self.assertEqual(self.call("submit", str(self.root), "--id", "sanity-001", "--execute")[0], 0)
        code, output, error = self.call("cancel", str(self.root), "--id", "sanity-001")
        self.assertEqual(code, 0, error)
        self.assertIn("12345.gadi-pbs", output)
        self.assertFalse(self.qdel_log.exists())
        code, _, error = self.call("cancel", str(self.root), "--id", "sanity-001", "--execute")
        self.assertEqual(code, 0, error)
        self.assertEqual(self.qdel_log.read_text(encoding="utf-8").strip(), "12345.gadi-pbs")
        self.assertEqual(
            CAMPAIGN.load_state(self.root)["experiments"]["sanity-001"]["status"],
            "cancel_requested",
        )
        self.qstat_output.write_text(
            "Job Id: 12345.gadi-pbs\n    job_state = X\n    Exit_status = 271\n",
            encoding="utf-8",
        )
        self.assertEqual(self.call("refresh", str(self.root))[0], 0)
        self.assertEqual(CAMPAIGN.load_state(self.root)["experiments"]["sanity-001"]["status"], "cancelled")

    def test_completion_requires_all_artifacts(self) -> None:
        self.init()
        self.approve()
        code, _, error = self.call("handoff", str(self.root), "--state", "complete", "--reason", "done")
        self.assertNotEqual(code, 0)
        self.assertIn("missing artifacts", error)

    def record_completion_artifacts(self) -> dict[str, Path]:
        paths: dict[str, Path] = {}
        paper_output = self.root / "paper"
        paper_output.mkdir(exist_ok=True)
        paper_source_dir = self.workspace / "paper"
        paper_source_dir.mkdir(exist_ok=True)
        for name in CAMPAIGN.REQUIRED_COMPLETION_ARTIFACTS:
            if name == "paper_source":
                path = paper_source_dir / "main.tex"
                path.write_text("\\documentclass{article}\\begin{document}test\\end{document}\n", encoding="utf-8")
            elif name == "paper_pdf":
                path = paper_output / "main.pdf"
                path.write_bytes(b"%PDF-1.7\n" + b"x" * 256)
            else:
                path = self.root / f"{name}.md"
                path.write_text(f"# {name}\nverified content\n", encoding="utf-8")
            paths[name] = path
        subprocess.run(["git", "-C", str(self.workspace), "add", "paper/main.tex"], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.workspace),
                "-c",
                "user.name=Unit Test",
                "-c",
                "user.email=unit@example.invalid",
                "commit",
                "-qm",
                "add paper",
            ],
            check=True,
        )
        for name, path in paths.items():
            assurance = "provisional" if name == "claim_audit" else "deterministic"
            code, _, error = self.call(
                "artifact",
                str(self.root),
                "--name",
                name,
                "--path",
                str(path),
                "--assurance",
                assurance,
            )
            self.assertEqual(code, 0, error)
        return paths

    def test_completion_checks_fresh_artifacts_and_pdf(self) -> None:
        self.init()
        self.approve()
        self.record_completion_artifacts()
        code, _, error = self.call(
            "handoff",
            str(self.root),
            "--state",
            "complete",
            "--reason",
            "all evidence verified",
        )
        self.assertEqual(code, 0, error)
        state = CAMPAIGN.load_state(self.root)
        self.assertEqual(state["status"], "complete")
        self.assertEqual(state["overall_assurance"], "provisional")

    def test_completion_rejects_artifact_changed_after_audit(self) -> None:
        self.init()
        self.approve()
        paths = self.record_completion_artifacts()
        paths["results"].write_text("changed after audit\n", encoding="utf-8")
        code, _, error = self.call(
            "handoff",
            str(self.root),
            "--state",
            "complete",
            "--reason",
            "should fail",
        )
        self.assertNotEqual(code, 0)
        self.assertIn("changed after it was recorded", error)

    def test_paused_campaign_requires_explicit_resume_reason(self) -> None:
        self.init()
        self.approve()
        self.assertEqual(
            self.call("handoff", str(self.root), "--state", "paused", "--reason", "inspect inode risk")[0],
            0,
        )
        state = CAMPAIGN.load_state(self.root)
        self.assertEqual(state["status"], "paused")
        code, _, error = self.call("resume", str(self.root), "--reason", "inode check now green")
        self.assertEqual(code, 0, error)
        state = CAMPAIGN.load_state(self.root)
        self.assertEqual(state["status"], "active")
        self.assertEqual(state["control"]["state"], "needs_agent")

    def test_reapproval_requires_pause_and_records_new_envelope(self) -> None:
        self.init()
        self.approve()
        code, _, error = self.call(
            "approve",
            str(self.root),
            "--by",
            "unit-test-2",
            "--replace",
            "--max-su",
            "750",
        )
        self.assertNotEqual(code, 0)
        self.assertIn("pause", error)
        self.assertEqual(
            self.call("handoff", str(self.root), "--state", "paused", "--reason", "quarterly reapproval")[0],
            0,
        )
        code, _, error = self.call(
            "approve",
            str(self.root),
            "--by",
            "unit-test-2",
            "--replace",
            "--max-su",
            "750",
            "--allow-auto-submit",
        )
        self.assertEqual(code, 0, error)
        state = CAMPAIGN.load_state(self.root)
        self.assertEqual(state["approval"]["max_su"], 750)
        self.assertTrue(state["approval"]["allow_auto_submit"])
        self.assertFalse(state["approval"]["allow_auto_agent"])


def argparse_namespace(**values: object) -> object:
    class Namespace:
        pass

    namespace = Namespace()
    for key, value in values.items():
        setattr(namespace, key, value)
    return namespace


if __name__ == "__main__":
    unittest.main()
