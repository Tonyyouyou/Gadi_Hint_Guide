#!/usr/bin/env python3
"""Safety tests for the event-driven Codex controller."""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import campaign  # noqa: E402
import controller  # noqa: E402


class ControllerTests(unittest.TestCase):
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
        (self.workspace / "README.md").write_text("controller test\n", encoding="utf-8")
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
        self.root = self.result / "controller-campaign"
        self.old_env = os.environ.copy()
        os.environ.update(
            {
                "GADI_AUTORESEARCH_TESTING": "1",
                "GADI_AUTORESEARCH_TEST_ROOT": str(self.persistent),
            }
        )
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            init_code = campaign.main(
                [
                    "init",
                    str(self.root),
                    "--campaign-id",
                    "controller-test",
                    "--idea",
                    "test controller",
                    "--workspace",
                    str(self.workspace),
                    "--deadline",
                    "2099-01-01T00:00:00Z",
                ]
            )
            approve_code = campaign.main(
                [
                    "approve",
                    str(self.root),
                    "--by",
                    "unit-test",
                    "--allow-auto-agent",
                ]
            )
        self.assertEqual(init_code, 0)
        self.assertEqual(approve_code, 0)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.old_env)
        self.temp.cleanup()

    def call(self, *args: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = controller.main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_preview_does_not_launch_agent(self) -> None:
        code, output, error = self.call(str(self.root))
        self.assertEqual(code, 0, error)
        self.assertIn("invoke or resume one Codex turn", output)
        self.assertEqual(campaign.load_state(self.root)["control"]["agent_turns"], 0)

    def test_poll_interval_below_nci_limit_is_rejected(self) -> None:
        code, _, error = self.call(str(self.root), "--poll-seconds", "60")
        self.assertNotEqual(code, 0)
        self.assertIn("at least 600", error)

    def test_codex_command_uses_safe_automatic_review(self) -> None:
        state = campaign.load_state(self.root)
        command = controller.codex_command("codex", self.workspace, state, self.root)
        self.assertIn("--approve-for-me", command)
        self.assertEqual(command[command.index("--add-dir") + 1], str(self.root))
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
        self.assertNotIn("--full-auto", command)
        state["control"]["thread_id"] = "thread-test"
        resumed = controller.codex_command("codex", self.workspace, state, self.root)
        self.assertLess(resumed.index("--approve-for-me"), resumed.index("resume"))
        self.assertEqual(resumed[resumed.index("--add-dir") + 1], str(self.root))

    def test_missing_agent_handoff_pauses_instead_of_spinning(self) -> None:
        fake_codex = self.base / "fake-codex"
        fake_codex.write_text(
            "#!/bin/sh\nprintf '%s\\n' '{\"type\":\"thread.started\",\"thread_id\":\"thread-test\"}'\n",
            encoding="utf-8",
        )
        fake_codex.chmod(0o755)
        with mock.patch.object(controller.campaign, "live_preflight", return_value={}):
            code, _, error = self.call(str(self.root), "--codex-bin", str(fake_codex), "--start")
        self.assertEqual(code, 0, error)
        state = campaign.load_state(self.root)
        self.assertEqual(state["status"], "paused")
        self.assertEqual(state["control"]["state"], "paused")
        self.assertEqual(state["control"]["agent_turns"], 1)
        self.assertEqual(state["control"]["thread_id"], "thread-test")
        self.assertIn("without the required campaign handoff", state["control"]["reason"])

    def test_stale_agent_state_pauses_instead_of_launching_duplicate(self) -> None:
        with campaign.locked_state(self.root) as state:
            state["control"].update({"state": "agent_running", "reason": "simulated controller loss"})
        code, _, error = self.call(str(self.root), "--start")
        self.assertEqual(code, 0, error)
        state = campaign.load_state(self.root)
        self.assertEqual(state["status"], "paused")
        self.assertEqual(state["control"]["state"], "paused")
        self.assertEqual(state["control"]["agent_turns"], 0)
        self.assertIn("avoid duplicate agents", state["control"]["reason"])

    def test_agent_turn_budget_sets_consistent_paused_status(self) -> None:
        with campaign.locked_state(self.root) as state:
            state["control"]["agent_turns"] = state["approval"]["max_agent_turns"]
        with mock.patch.object(controller.campaign, "live_preflight", return_value={}):
            code, _, error = self.call(str(self.root), "--start")
        self.assertEqual(code, 0, error)
        state = campaign.load_state(self.root)
        self.assertEqual(state["status"], "paused")
        self.assertEqual(state["control"]["state"], "paused")
        self.assertIn("turn budget exhausted", state["control"]["reason"])


if __name__ == "__main__":
    unittest.main()
