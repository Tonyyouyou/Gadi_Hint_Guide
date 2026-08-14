#!/usr/bin/env python3
"""Unit tests for the persistent controller watchdog."""

from __future__ import annotations

import argparse
import signal
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import supervisor  # noqa: E402


class SupervisorTests(unittest.TestCase):
    def tearDown(self) -> None:
        supervisor._child = None
        supervisor._stop = False

    def test_controller_command_preserves_unattended_model_settings(self) -> None:
        args = argparse.Namespace(
            python="/usr/bin/python3",
            controller="/skill/controller.py",
            root=Path("/campaign"),
            codex_bin="/opt/codex",
            poll_seconds=60,
            model="gpt-5.6-sol",
            reasoning_effort="ultra",
        )
        command = supervisor.controller_command(args)
        self.assertEqual(command[:3], ["/usr/bin/python3", "/skill/controller.py", "/campaign"])
        self.assertIn("--start", command)
        self.assertIn("--loop", command)
        self.assertEqual(command[command.index("--poll-seconds") + 1], "60")
        self.assertEqual(command[command.index("--model") + 1], "gpt-5.6-sol")
        self.assertEqual(command[command.index("--reasoning-effort") + 1], "ultra")

    def test_hangup_stops_the_controller_process_group(self) -> None:
        child = mock.Mock()
        child.pid = 12345
        child.poll.return_value = None
        supervisor._child = child
        with mock.patch.object(supervisor.os, "killpg") as killpg:
            supervisor.stop_handler(signal.SIGHUP, None)
        self.assertTrue(supervisor._stop)
        killpg.assert_called_once_with(12345, signal.SIGHUP)


if __name__ == "__main__":
    unittest.main()
