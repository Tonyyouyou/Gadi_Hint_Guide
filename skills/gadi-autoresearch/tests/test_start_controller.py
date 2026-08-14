#!/usr/bin/env python3
"""CLI tests for clean tmux controller startup."""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts" / "start_controller.sh"
sys.path.insert(0, str(SKILL / "scripts"))
import campaign  # noqa: E402


class StartControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.persistent = self.base / "Xiangyu"
        self.result = self.persistent / "Result_Test"
        self.workspace = self.persistent / "workspace"
        for path in (
            self.result,
            self.workspace,
            self.persistent / ".codex",
            self.persistent / "enviroment_cache",
            self.persistent / "Data",
        ):
            path.mkdir(parents=True)
        (self.workspace / "README.md").write_text("controller helper test\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(self.workspace)], check=True)
        subprocess.run(["git", "-C", str(self.workspace), "add", "README.md"], check=True)
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
        self.root = self.result / "campaign"
        self.old_env = os.environ.copy()
        os.environ.update(
            {
                "GADI_AUTORESEARCH_TESTING": "1",
                "GADI_AUTORESEARCH_TEST_ROOT": str(self.persistent),
            }
        )
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(
                campaign.main(
                    [
                        "init",
                        str(self.root),
                        "--campaign-id",
                        "controller-helper-test",
                        "--idea",
                        "test clean controller startup",
                        "--workspace",
                        str(self.workspace),
                        "--deadline",
                        "2099-01-01T00:00:00Z",
                    ]
                ),
                0,
            )
            self.assertEqual(
                campaign.main(
                    [
                        "approve",
                        str(self.root),
                        "--by",
                        "unit-test",
                        "--allow-auto-agent",
                    ]
                ),
                0,
            )
        self.bin_dir = self.base / "bin"
        self.bin_dir.mkdir()
        self.tmux_log = self.base / "tmux.log"
        self.codex = self.bin_dir / "codex"
        self.codex.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.codex.chmod(0o755)
        hostname = self.bin_dir / "hostname"
        hostname.write_text("#!/bin/sh\nprintf '%s\\n' arisctl.test.wa66.ps.gadi.nci.org.au\n", encoding="utf-8")
        hostname.chmod(0o755)
        tmux = self.bin_dir / "tmux"
        tmux.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = has-session ]; then exit 1; fi\n"
            "printf '%s\\n' \"$*\" >> \"$TMUX_LOG\"\n",
            encoding="utf-8",
        )
        tmux.chmod(0o755)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.old_env)
        self.temp.cleanup()

    def run_helper(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{self.bin_dir}{os.pathsep}{env['PATH']}",
                "PBS_JOBID": "",
                "TMUX_LOG": str(self.tmux_log),
            }
        )
        return subprocess.run(
            [
                "bash",
                str(SCRIPT),
                "--root",
                str(self.root),
                "--session",
                "aris-test",
                "--codex-bin",
                str(self.codex),
                *args,
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=15,
        )

    def test_preview_has_no_tmux_side_effect(self) -> None:
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Preview only", result.stdout)
        self.assertFalse(self.tmux_log.exists())

    def test_start_uses_clean_no_profile_tmux_command(self) -> None:
        result = self.run_helper("--start")
        self.assertEqual(result.returncode, 0, result.stderr)
        log = self.tmux_log.read_text(encoding="utf-8")
        self.assertIn("new-session", log)
        self.assertIn("--noprofile", log)
        self.assertIn("PBS_JOBFS", log)
        self.assertIn("--poll-seconds", log)
        self.assertIn("supervisor.py", log)
        self.assertIn("HF_TOKEN", log)
        self.assertIn("OVERLEAF_TOKEN", log)

    def test_start_persists_explicit_model_and_reasoning_effort(self) -> None:
        result = self.run_helper(
            "--model",
            "gpt-5.6-sol",
            "--reasoning-effort",
            "ultra",
            "--start",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Model:        gpt-5.6-sol", result.stdout)
        self.assertIn("Reasoning:    ultra", result.stdout)
        log = self.tmux_log.read_text(encoding="utf-8")
        self.assertIn("--model", log)
        self.assertIn("gpt-5.6-sol", log)
        self.assertIn("--reasoning-effort", log)
        self.assertIn("ultra", log)


if __name__ == "__main__":
    unittest.main()
