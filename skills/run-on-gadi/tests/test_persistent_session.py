#!/usr/bin/env python3
"""CLI guard tests for the NCI persistent-session helper."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "persistent_session.sh"


class PersistentSessionTests(unittest.TestCase):
    def fake_env(self, root: Path) -> tuple[dict[str, str], Path]:
        bin_dir = root / "bin"
        bin_dir.mkdir()
        call_log = root / "persistent.log"
        commands = {
            "hostname": "#!/bin/sh\nprintf '%s\\n' gadi-login-99.gadi.nci.org.au\n",
            "id": "#!/bin/sh\nprintf '%s\\n' 'wa66 ey69 po67 iv96'\n",
            "persistent-sessions": "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$CALL_LOG\"\nprintf '%s\\n' 'session fake-uuid running'\n",
        }
        for name, content in commands.items():
            path = bin_dir / name
            path.write_text(content, encoding="utf-8")
            path.chmod(0o755)
        env = os.environ.copy()
        env.update({"PATH": f"{bin_dir}{os.pathsep}{env['PATH']}", "PBS_JOBID": "", "CALL_LOG": str(call_log), "USER": "testuser"})
        return env, call_log

    def run_helper(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(SCRIPT), *args], check=False, capture_output=True, text=True, env=env, timeout=10)

    def test_preview_has_no_side_effect(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env, call_log = self.fake_env(Path(temp_dir))
            result = self.run_helper("--project", "wa66", "--name", "arisctl", env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Preview only", result.stdout)
            self.assertFalse(call_log.exists())

    def test_start_calls_named_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env, call_log = self.fake_env(Path(temp_dir))
            result = self.run_helper("--project", "ey69", "--name", "arisctl", "--start", env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(call_log.read_text(encoding="utf-8").strip(), "start -p ey69 arisctl")

    def test_unsafe_name_is_rejected(self) -> None:
        result = self.run_helper("--project", "wa66", "--name", "ARIS_bad")
        self.assertNotEqual(result.returncode, 0)

    def test_trailing_hyphen_name_is_rejected(self) -> None:
        result = self.run_helper("--project", "wa66", "--name", "arisctl-")
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
