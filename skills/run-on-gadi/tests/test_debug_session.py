#!/usr/bin/env python3
"""CLI guard tests for the interactive debug helper."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "debug_session.sh"


class DebugSessionTests(unittest.TestCase):
    def fake_gadi_env(self, root: Path) -> tuple[dict[str, str], Path, Path]:
        bin_dir = root / "bin"
        bin_dir.mkdir()
        qsub_log = root / "qsub.log"
        tmux_log = root / "tmux.log"
        commands = {
            "hostname": "#!/bin/sh\nprintf '%s\\n' gadi-login-99.gadi.nci.org.au\n",
            "id": "#!/bin/sh\nprintf '%s\\n' 'wa66 ey69 po67 iv96'\n",
            "nci_account": "#!/bin/sh\nprintf '%s\\n' 'Avail: 1.00 KSU'\n",
            "qsub": "#!/bin/sh\nprintf '%s\\n' called >> \"$QSUB_LOG\"\n",
            "tmux": (
                "#!/bin/sh\n"
                "if [ \"${1:-}\" = has-session ]; then exit 1; fi\n"
                "printf '%s\\n' \"$*\" >> \"$TMUX_LOG\"\n"
            ),
        }
        for name, content in commands.items():
            path = bin_dir / name
            path.write_text(content, encoding="utf-8")
            path.chmod(0o755)

        env = {
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "PBS_JOBID": "",
            "QSUB_LOG": str(qsub_log),
            "TMUX": "",
            "TMUX_LOG": str(tmux_log),
        }
        return env, qsub_log, tmux_log

    def run_helper(
        self,
        *arguments: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        process_env = os.environ.copy()
        if env:
            process_env.update(env)
        return subprocess.run(
            ["bash", str(SCRIPT), *arguments],
            check=False,
            capture_output=True,
            text=True,
            env=process_env,
            timeout=10,
        )

    def test_help_does_not_require_pbs(self) -> None:
        result = self.run_helper("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Preview is the default and never submits", result.stdout)

    def test_unknown_project_is_rejected(self) -> None:
        result = self.run_helper("--kind", "h200", "--project", "zz99")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("project must be one of", result.stderr)

    def test_debug_walltime_over_four_hours_is_rejected(self) -> None:
        result = self.run_helper(
            "--kind",
            "h200",
            "--project",
            "wa66",
            "--walltime",
            "04:00:01",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("at most 04:00:00", result.stderr)

    def test_four_hour_debug_walltime_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env, _, _ = self.fake_gadi_env(Path(temp_dir))
            result = self.run_helper(
                "--kind",
                "h200",
                "--project",
                "wa66",
                "--walltime",
                "04:00:00",
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Walltime:     04:00:00", result.stdout)

    def test_persistent_control_host_can_be_explicitly_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env, _, _ = self.fake_gadi_env(Path(temp_dir))
            hostname = Path(temp_dir) / "bin" / "hostname"
            hostname.write_text("#!/bin/sh\nprintf '%s\\n' persistent-pod-123\n", encoding="utf-8")
            hostname.chmod(0o755)
            result = self.run_helper(
                "--kind",
                "a100",
                "--project",
                "wa66",
                "--persistent-control-host",
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_one_node_memory_limit_is_rejected(self) -> None:
        result = self.run_helper(
            "--kind",
            "v100",
            "--project",
            "wa66",
            "--mem-gb",
            "383",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("one-node limit of 382GB", result.stderr)

    def test_nested_pbs_submission_is_rejected(self) -> None:
        result = self.run_helper(
            "--kind",
            "a100",
            "--project",
            "wa66",
            env={"PBS_JOBID": "test.gadi-pbs"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("do not submit a nested debug job", result.stderr)

    def test_preview_does_not_run_qsub_or_tmux(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env, qsub_log, tmux_log = self.fake_gadi_env(Path(temp_dir))
            result = self.run_helper(
                "--kind",
                "h200",
                "--project",
                "wa66",
                "--session",
                "skill-test-preview",
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Preview only: no tmux session or PBS job", result.stdout)
            self.assertFalse(qsub_log.exists())
            self.assertFalse(tmux_log.exists())

    def test_start_sends_qsub_to_named_tmux_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env, qsub_log, tmux_log = self.fake_gadi_env(Path(temp_dir))
            result = self.run_helper(
                "--kind",
                "a100",
                "--project",
                "ey69",
                "--session",
                "skill-test-start",
                "--start",
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(qsub_log.exists())
            tmux_calls = tmux_log.read_text(encoding="utf-8")
            self.assertIn("new-session -d -s skill-test-start", tmux_calls)
            self.assertIn("send-keys -t skill-test-start:0.0 -l", tmux_calls)
            self.assertIn(f"{Path(temp_dir) / 'bin' / 'qsub'} -I", tmux_calls)


if __name__ == "__main__":
    unittest.main()
