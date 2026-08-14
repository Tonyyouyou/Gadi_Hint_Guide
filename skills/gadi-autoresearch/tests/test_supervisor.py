#!/usr/bin/env python3
"""Unit tests for the persistent controller watchdog."""

from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import supervisor  # noqa: E402


class SupervisorTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
