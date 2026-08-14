#!/usr/bin/env python3
"""Safety tests for the event-driven Codex controller."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shlex
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

    def prepare_novelty_review(
        self,
        *,
        decision: str = "clear_to_plan",
        claim_class: str = "new_mechanism",
    ) -> Path:
        idea = self.root / "IDEA_REPORT.md"
        idea.write_text("# Candidate\n\nAdaptive stability controls selective replay.\n", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(
                campaign.main(
                    [
                        "artifact",
                        str(self.root),
                        "--name",
                        "idea_report",
                        "--path",
                        str(idea),
                        "--assurance",
                        "provisional",
                    ]
                ),
                0,
            )
        state = campaign.load_state(self.root)
        portfolio = self.root / "CANDIDATE_PORTFOLIO.json"
        portfolio.write_text(
            json.dumps(
                {
                    "schema_version": campaign.PORTFOLIO_SCHEMA_VERSION,
                    "mission_sha256": state["mission_sha256"],
                    "route_sha256": state["route"]["sha256"],
                    "created_at": campaign.utc_now(),
                    "active_candidate_id": "candidate-one",
                    "candidates": [
                        {
                            "id": f"candidate-{name}",
                            "status": status,
                            "observation": f"Observed behavior {name}.",
                            "causal_hypothesis": f"Causal hypothesis {name}.",
                            "mechanism": f"Mechanism {name}.",
                            "predicted_signature": f"Prediction {name}.",
                            "falsifier": f"Falsifier {name}.",
                            "cheap_test": f"Cheap test {name}.",
                            "nearest_work_delta": f"Prior-work delta {name}.",
                            "estimated_cost": {"su": 1, "jobs": 1, "persistent_entries": 2},
                        }
                        for name, status in (
                            ("one", "active"),
                            ("two", "backup"),
                            ("three", "backup"),
                            ("four", "backup"),
                        )
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(
                campaign.main(
                    [
                        "artifact",
                        str(self.root),
                        "--name",
                        "candidate_portfolio",
                        "--path",
                        str(portfolio),
                        "--assurance",
                        "provisional",
                    ]
                ),
                0,
            )
        searches = {
            category: [f"author {category} query"]
            for category in campaign.NOVELTY_SEARCH_CATEGORIES
        }
        sources = [
            {
                "id": f"a{index}",
                "title": f"Author source {index}",
                "url": f"https://example.org/a{index}",
                "year": 2024,
                "checked_locator": f"Section {index}",
                "mechanism_evidence": "The full text describes the relevant replay primitive.",
                "primary_source": True,
                "full_text_checked": True,
            }
            for index in range(1, 4)
        ]
        audit = self.root / "NOVELTY_AUDIT.json"
        audit.write_text(
            json.dumps(
                {
                    "schema_version": campaign.NOVELTY_SCHEMA_VERSION,
                    "candidate_id": "candidate-one",
                    "idea_report_sha256": campaign.sha256_file(idea),
                    "mission_sha256": state["mission_sha256"],
                    "route_sha256": state["route"]["sha256"],
                    "candidate_portfolio_sha256": campaign.sha256_file(portfolio),
                    "searched_at": campaign.utc_now(),
                    "mechanism_without_brand": "Adaptive stability controls selective replay.",
                    "claim_class": "new_mechanism",
                    "verdict": "plausibly_novel",
                    "primitives": [{"id": "adaptive-replay", "description": "Replay selected unstable regions."}],
                    "searches": searches,
                    "sources": sources,
                    "nearest_neighbors": [
                        {
                            "source_id": source["id"],
                            "mechanism_overlap": "Replay primitive.",
                            "remaining_delta": "No adaptive boundary control.",
                        }
                        for source in sources
                    ],
                    "brand_substitution_test": {
                        "outcome": "materially_changed",
                        "explanation": "The mechanism survives removal of the application name.",
                    },
                    "combination_test": {
                        "existing_combination": False,
                        "decomposition": "stability plus selective replay",
                        "non_obvious_interaction": "Stability selects boundaries.",
                    },
                    "strongest_rejection": "This may be confidence-triggered recomputation.",
                    "author_rebuttal": "Checked systems do not select replay boundaries.",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(
                campaign.main(
                    [
                        "artifact",
                        str(self.root),
                        "--name",
                        "novelty_audit",
                        "--path",
                        str(audit),
                        "--assurance",
                        "provisional",
                    ]
                ),
                0,
            )
        review_sources = [
            {
                "id": f"r{index}",
                "title": f"Reviewer source {index}",
                "url": f"https://review.example.org/r{index}",
                "year": 2025,
                "checked_locator": f"Methods {index}",
                "mechanism_evidence": "The methods provide independent mechanism evidence.",
                "primary_source": True,
                "full_text_checked": True,
            }
            for index in range(1, 4)
        ]
        review = self.root / "NOVELTY_REVIEW.json"
        review_payload = {
            "schema_version": campaign.NOVELTY_SCHEMA_VERSION,
            "candidate_id": "candidate-one",
            "audit_sha256": campaign.sha256_file(audit),
            "reviewed_at": campaign.utc_now(),
            "independent_context": True,
            "decision": decision,
            "claim_class": claim_class,
            "reviewer_searches": {
                category: [f"reviewer {category} query"]
                for category in campaign.NOVELTY_SEARCH_CATEGORIES
            },
            "sources": review_sources,
            "prior_checks": {
                "earliest": {"source_id": "r1", "conclusion": "Earliest primitive."},
                "closest": {"source_id": "r2", "conclusion": "Closest lacks coupling."},
                "newest": {"source_id": "r3", "conclusion": "Newest remains distinct."},
                "exact_combination": {"source_id": None, "conclusion": "No exact combination."},
            },
            "primitive_overlap": [
                {
                    "primitive_id": "adaptive-replay",
                    "source_ids": ["r1", "r2", "r3"],
                    "assessment": "Primitive is known but the proposed control interaction was not found.",
                }
            ],
            "strongest_rejection": "Could reduce to confidence-triggered recomputation.",
            "author_rebuttal_assessment": "Rebuttal survives for boundary selection only.",
            "blocking_overlaps": [],
            "required_changes": [],
        }
        if decision == "conditional_probe":
            review_payload["probe_plan"] = {
                "question": "Does coupling beat a naive serial composition?",
                "naive_combination_baseline": "Independent stability scoring then replay.",
                "distinguishing_outcome": "Lower latency at matched error.",
                "falsifier": "No gain over the serial baseline.",
            }
        if decision == "exact_prior_reject":
            review_payload["prior_checks"]["exact_combination"] = {
                "source_id": "r2",
                "conclusion": "The closest source implements the same control interaction.",
                "functionally_equivalent": True,
                "equivalence_evidence": "Methods 2 uses the same trigger, boundary, and replay effect.",
            }
        review.write_text(
            json.dumps(review_payload, indent=2)
            + "\n",
            encoding="utf-8",
        )
        with campaign.locked_state(self.root) as state:
            state["phase"] = "novelty_review"
            state["control"].update({"state": "agent_running", "thread_id": "author-thread"})
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(
                campaign.main(
                    [
                        "handoff",
                        str(self.root),
                        "--state",
                        "needs_novelty_review",
                        "--reason",
                        "unit-test review request",
                    ]
                ),
                0,
            )
        return review

    def test_preview_does_not_launch_agent(self) -> None:
        code, output, error = self.call(str(self.root))
        self.assertEqual(code, 0, error)
        self.assertIn("invoke or resume one Codex turn", output)
        self.assertEqual(campaign.load_state(self.root)["control"]["agent_turns"], 0)

    def test_poll_interval_below_nci_limit_is_rejected(self) -> None:
        code, _, error = self.call(str(self.root), "--poll-seconds", "30")
        self.assertNotEqual(code, 0)
        self.assertIn("at least 60", error)

    def test_codex_command_uses_unattended_full_access_policy(self) -> None:
        state = campaign.load_state(self.root)
        command = controller.codex_command("codex", self.workspace, state, self.root)
        self.assertNotIn("--approve-for-me", command)
        self.assertEqual(command[command.index("--sandbox") + 1], "danger-full-access")
        self.assertIn('approval_policy="never"', command)
        self.assertEqual(command[command.index("--add-dir") + 1], str(self.root))
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
        self.assertNotIn("--full-auto", command)
        self.assertIn("MISSION.json", command[-1])
        self.assertIn("Current adapter packet", command[-1])
        self.assertIn("Never silently downgrade", command[-1])
        self.assertIn("Never invent ratings", command[-1])
        state["control"]["thread_id"] = "thread-test"
        resumed = controller.codex_command("codex", self.workspace, state, self.root)
        self.assertLess(resumed.index("--sandbox"), resumed.index("resume"))
        self.assertLess(resumed.index('approval_policy="never"'), resumed.index("resume"))
        self.assertEqual(resumed[resumed.index("--add-dir") + 1], str(self.root))

    def test_codex_command_pins_model_and_ultra_effort(self) -> None:
        state = campaign.load_state(self.root)
        command = controller.codex_command(
            "codex",
            self.workspace,
            state,
            self.root,
            "gpt-5.6-sol",
            "ultra",
        )
        self.assertEqual(command[1:5], [
            "--model",
            "gpt-5.6-sol",
            "--config",
            'model_reasoning_effort="ultra"',
        ])
        self.assertLess(command.index("--config"), command.index("exec"))

    def test_codex_canary_requires_the_expected_filesystem_marker(self) -> None:
        fake_codex = self.base / "fake-canary-codex"
        fake_codex.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "workspace=\n"
            "while [ \"$#\" -gt 0 ]; do\n"
            "  if [ \"$1\" = -C ]; then shift; workspace=$1; fi\n"
            "  shift\n"
            "done\n"
            "test -n \"$workspace\"\n"
            "printf '%s\\n' gadi-autoresearch-controller-canary-v2 > \"$workspace/canary.txt\"\n",
            encoding="utf-8",
        )
        fake_codex.chmod(0o755)
        result = controller.run_codex_canary(str(fake_codex), "gpt-5.6-sol", "ultra")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["sandbox_mode"], "danger-full-access")
        self.assertEqual(result["approval_policy"], "never")

    def test_novelty_reviewer_command_always_starts_a_fresh_thread(self) -> None:
        state = campaign.load_state(self.root)
        state["control"]["thread_id"] = "author-thread"
        audit = {
            "candidate_id": "blind-candidate",
            "mechanism_without_brand": "Blind mechanism description.",
            "primitives": [{"id": "p1", "description": "Primitive one."}],
        }
        command = controller.novelty_codex_command("codex", self.workspace, self.root, audit)
        self.assertNotIn("resume", command)
        self.assertIn("--json", command)
        self.assertIn("cold, adversarial novelty reviewer", command[-1])
        self.assertIn("blind-candidate", command[-1])
        self.assertIn("do not open IDEA_REPORT.md", command[-1])

        pinned = controller.novelty_codex_command(
            "codex",
            self.workspace,
            self.root,
            audit,
            "gpt-5.6-sol",
            "ultra",
        )
        self.assertIn("gpt-5.6-sol", pinned)
        self.assertIn('model_reasoning_effort="ultra"', pinned)

    def test_controller_attests_valid_review_from_distinct_thread(self) -> None:
        review = self.prepare_novelty_review()
        fake_codex = self.base / "fake-reviewer-codex"
        cli = SCRIPTS / "campaign.py"
        fake_codex.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            f"{shlex.quote(sys.executable)} {shlex.quote(str(cli))} artifact {shlex.quote(str(self.root))} "
            f"--name novelty_review --path {shlex.quote(str(review))} --assurance provisional\n"
            f"{shlex.quote(sys.executable)} {shlex.quote(str(cli))} handoff {shlex.quote(str(self.root))} "
            "--state needs_agent --reason 'independent novelty review complete'\n"
            "printf '%s\\n' '{\"type\":\"thread.started\",\"thread_id\":\"reviewer-thread\"}'\n",
            encoding="utf-8",
        )
        fake_codex.chmod(0o755)
        with mock.patch.object(controller.campaign, "live_preflight", return_value={}):
            controller.run_novelty_reviewer(self.root, str(fake_codex))
        state = campaign.load_state(self.root)
        record = state["artifacts"]["novelty_review"]
        self.assertTrue(record["cold_review"])
        self.assertEqual(record["review_thread_id"], "reviewer-thread")
        self.assertEqual(record["author_thread_id"], "author-thread")
        self.assertEqual(state["control"]["thread_id"], "author-thread")
        self.assertEqual(state["control"]["novelty_review_thread_id"], "reviewer-thread")
        self.assertEqual(state["control"]["state"], "needs_agent")
        self.assertEqual(state["control"]["agent_turns"], 1)

    def test_controller_attests_fresh_failure_critic_before_adaptation(self) -> None:
        review = self.prepare_novelty_review()
        with campaign.locked_state(self.root) as current:
            campaign.record_file_artifact(
                current, "novelty_review", review, assurance="provisional"
            )
            audit = campaign.artifact_file(current, "novelty_audit")
            current["artifacts"]["novelty_review"].update(
                {
                    "cold_review": True,
                    "review_thread_id": "novelty-review-thread",
                    "author_thread_id": "author-thread",
                    "reviewed_audit_sha256": campaign.sha256_file(audit),
                }
            )
            current["control"].update(
                {"state": "needs_agent", "novelty_review_thread_id": "novelty-review-thread"}
            )
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(
                campaign.main(
                    [
                        "learning-init",
                        str(self.root),
                        "--adopt-current-claim",
                        "--reason",
                        "unit-test migration",
                    ]
                ),
                0,
            )
        state = campaign.load_state(self.root)
        binding = campaign.experiment_hypothesis_binding(
            state,
            evidence_role="diagnostic",
            hypothesis_id="candidate-one",
        )
        success = self.root / "runs" / "diagnostic-one" / "metrics.json"
        success.parent.mkdir(parents=True)
        success.write_text('{"latency":1.0}\n', encoding="utf-8")
        source_commit = campaign.git_workspace_info(self.workspace)["commit"]
        with campaign.locked_state(self.root) as current:
            current["experiments"]["diagnostic-one"] = {
                "id": "diagnostic-one",
                "stage": "sanity",
                "mode": "batch",
                "status": "completed",
                "command": ["python", "probe.py"],
                "source_commit": source_commit,
                "success_file": str(success),
                "evidence_role": "diagnostic",
                "hypothesis_binding": binding,
                "attempts": [],
            }
        interpretation = self.base / "interpretation.json"
        interpretation.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "finding_id": "surprising-diagnostic",
                    "experiment_id": "diagnostic-one",
                    "hypothesis_id": "candidate-one",
                    "evidence_role": "diagnostic",
                    "validity": "valid",
                    "outcome": "unexpected",
                    "expected": "One stable latency regime.",
                    "observed": "Two reproducible latency regimes.",
                    "surprise": "The workload boundary changes the mechanism signature.",
                    "alternative_explanations": ["Measurement mode switching."],
                    "assumption_updates": [],
                    "information_gain": "high",
                    "proposed_delta": "Branch a workload-conditioned mechanism.",
                    "next_action": "branch",
                    "discriminating_test": "Repeat with a predeclared workload split.",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(
                campaign.main(
                    ["learning-record", str(self.root), "--file", str(interpretation)]
                ),
                0,
            )
        with campaign.locked_state(self.root) as current:
            current["control"].update({"state": "agent_running", "thread_id": "author-thread"})
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(
                campaign.main(
                    [
                        "handoff",
                        str(self.root),
                        "--state",
                        "needs_failure_review",
                        "--reason",
                        "valid surprise needs a fresh critic",
                    ]
                ),
                0,
            )

        review = self.base / "failure-review.json"
        review.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "finding_id": "surprising-diagnostic",
                    "decision": "accept",
                    "failure_class": "anomaly",
                    "allowed_action": "branch",
                    "material_change": True,
                    "validity_assessment": "The registered output supports a valid anomaly.",
                    "rationale": "The parent remains viable while a parallel mechanism is tested.",
                    "required_test": "Use an independent workload split.",
                    "alternative_explanations": ["A measurement regime could still explain the modes."],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        fake_codex = self.base / "fake-failure-critic"
        cli = SCRIPTS / "campaign.py"
        fake_codex.write_text(
            "#!/bin/sh\nset -eu\n"
            f"{shlex.quote(sys.executable)} {shlex.quote(str(cli))} learning-review {shlex.quote(str(self.root))} "
            f"--file {shlex.quote(str(review))}\n"
            f"{shlex.quote(sys.executable)} {shlex.quote(str(cli))} handoff {shlex.quote(str(self.root))} "
            "--state needs_agent --reason 'fresh failure review complete'\n"
            "printf '%s\\n' '{\"type\":\"thread.started\",\"thread_id\":\"failure-critic-thread\"}'\n",
            encoding="utf-8",
        )
        fake_codex.chmod(0o755)
        with mock.patch.object(controller.campaign, "live_preflight", return_value={}):
            controller.run_failure_reviewer(self.root, str(fake_codex))
        state = campaign.load_state(self.root)
        attestation = state["learning"]["reviews"]["surprising-diagnostic"]
        self.assertTrue(attestation["independent"])
        self.assertEqual(attestation["reviewer_thread_id"], "failure-critic-thread")
        self.assertEqual(attestation["author_thread_id"], "author-thread")
        self.assertIsNone(state["learning"]["pending_failure_review"])
        self.assertEqual(state["control"]["state"], "needs_agent")
        review_entry = campaign.learning_failure_review_by_finding(
            state, "surprising-diagnostic"
        )
        self.assertTrue(review_entry["independent"])

    def test_conditional_review_stays_in_novelty_review_for_bounded_probes(self) -> None:
        review = self.prepare_novelty_review(decision="conditional_probe")
        fake_codex = self.base / "fake-conditional-reviewer-codex"
        cli = SCRIPTS / "campaign.py"
        fake_codex.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            f"{shlex.quote(sys.executable)} {shlex.quote(str(cli))} artifact {shlex.quote(str(self.root))} "
            f"--name novelty_review --path {shlex.quote(str(review))} --assurance provisional\n"
            f"{shlex.quote(sys.executable)} {shlex.quote(str(cli))} handoff {shlex.quote(str(self.root))} "
            "--state needs_agent --reason 'conditional novelty probe required'\n"
            "printf '%s\\n' '{\"type\":\"thread.started\",\"thread_id\":\"conditional-reviewer-thread\"}'\n",
            encoding="utf-8",
        )
        fake_codex.chmod(0o755)
        with mock.patch.object(controller.campaign, "live_preflight", return_value={}):
            controller.run_novelty_reviewer(self.root, str(fake_codex))
        state = campaign.load_state(self.root)
        self.assertEqual(state["phase"], "novelty_review")
        self.assertEqual(state["control"]["state"], "needs_agent")
        self.assertIn("bounded novelty probes", state["control"]["reason"])
        self.assertNotIn("research_track", state)
        self.assertEqual(campaign.current_probe_binding(state)["clearance"], "conditional_probe")

    def test_controller_attests_third_thread_arbitration(self) -> None:
        review = self.prepare_novelty_review(decision="conditional_probe")
        cli = SCRIPTS / "campaign.py"
        fake_reviewer = self.base / "fake-conditional-reviewer"
        fake_reviewer.write_text(
            "#!/bin/sh\nset -eu\n"
            f"{shlex.quote(sys.executable)} {shlex.quote(str(cli))} artifact {shlex.quote(str(self.root))} "
            f"--name novelty_review --path {shlex.quote(str(review))} --assurance provisional\n"
            f"{shlex.quote(sys.executable)} {shlex.quote(str(cli))} handoff {shlex.quote(str(self.root))} "
            "--state needs_agent --reason 'conditional review complete'\n"
            "printf '%s\\n' '{\"type\":\"thread.started\",\"thread_id\":\"reviewer-thread\"}'\n",
            encoding="utf-8",
        )
        fake_reviewer.chmod(0o755)
        with mock.patch.object(controller.campaign, "live_preflight", return_value={}):
            controller.run_novelty_reviewer(self.root, str(fake_reviewer))

        state = campaign.load_state(self.root)
        binding = campaign.current_probe_binding(state)
        success_file = self.root / "runs" / "probe-one" / "metrics.json"
        success_file.parent.mkdir(parents=True)
        success_file.write_text('{"status":"ok"}\n', encoding="utf-8")
        with campaign.locked_state(self.root) as current:
            current["experiments"]["probe-one"] = {
                "id": "probe-one",
                "stage": campaign.NOVELTY_PROBE_STAGE,
                "mode": "batch",
                "status": "completed",
                "max_su": 1.0,
                "expected_files": 1,
                "success_file": str(success_file),
                "claim_binding": binding,
                "attempts": [],
            }
        audit = self.root / "NOVELTY_AUDIT.json"
        rebuttal = self.root / "NOVELTY_REBUTTAL.json"
        rebuttal.write_text(
            json.dumps(
                {
                    "schema_version": campaign.NOVELTY_SCHEMA_VERSION,
                    "candidate_id": "candidate-one",
                    "audit_sha256": campaign.sha256_file(audit),
                    "review_sha256": campaign.sha256_file(review),
                    "written_at": campaign.utc_now(),
                    "probe_experiment_ids": ["probe-one"],
                    "probe_results": [
                        {
                            "experiment_id": "probe-one",
                            "success_file_sha256": campaign.sha256_file(success_file),
                            "finding": "Coupling beats the naive baseline at matched error.",
                        }
                    ],
                    "reviewer_objections": [
                        {
                            "objection": "This may be a naive A+B composition.",
                            "response": "The controlled probe isolates a coupled boundary effect.",
                            "evidence_experiment_ids": ["probe-one"],
                        }
                    ],
                    "naive_combination_baseline": "Independent stability scoring then replay.",
                    "distinguishing_result": "Lower latency at matched error.",
                    "author_position": "advance",
                    "remaining_risks": [],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(
                campaign.main(
                    [
                        "artifact",
                        str(self.root),
                        "--name",
                        "novelty_rebuttal",
                        "--path",
                        str(rebuttal),
                        "--assurance",
                        "provisional",
                    ]
                ),
                0,
            )
            self.assertEqual(
                campaign.main(
                    [
                        "handoff",
                        str(self.root),
                        "--state",
                        "needs_novelty_arbitration",
                        "--reason",
                        "probe and rebuttal complete",
                    ]
                ),
                0,
            )

        arbitration = self.root / "NOVELTY_ARBITRATION.json"
        arbitration.write_text(
            json.dumps(
                {
                    "schema_version": campaign.NOVELTY_SCHEMA_VERSION,
                    "candidate_id": "candidate-one",
                    "audit_sha256": campaign.sha256_file(audit),
                    "review_sha256": campaign.sha256_file(review),
                    "rebuttal_sha256": campaign.sha256_file(rebuttal),
                    "arbitrated_at": campaign.utc_now(),
                    "independent_context": True,
                    "decision": "clear_to_plan",
                    "claim_class": "new_mechanism",
                    "probe_validity_assessment": "The probe isolates the coupling.",
                    "naive_combination_assessment": "The baseline is faithful and competitive.",
                    "non_obvious_interaction_assessment": "The effect exceeds independent composition.",
                    "paper_contribution_assessment": "The evidence supports a primary mechanism claim.",
                    "blocking_issues": [],
                    "required_changes": [],
                    "exact_prior": None,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        fake_arbiter = self.base / "fake-arbiter-codex"
        fake_arbiter.write_text(
            "#!/bin/sh\nset -eu\n"
            f"{shlex.quote(sys.executable)} {shlex.quote(str(cli))} artifact {shlex.quote(str(self.root))} "
            f"--name novelty_arbitration --path {shlex.quote(str(arbitration))} --assurance provisional\n"
            f"{shlex.quote(sys.executable)} {shlex.quote(str(cli))} handoff {shlex.quote(str(self.root))} "
            "--state needs_agent --reason 'independent arbitration complete'\n"
            "printf '%s\\n' '{\"type\":\"thread.started\",\"thread_id\":\"arbiter-thread\"}'\n",
            encoding="utf-8",
        )
        fake_arbiter.chmod(0o755)
        with mock.patch.object(controller.campaign, "live_preflight", return_value={}):
            controller.run_novelty_arbiter(self.root, str(fake_arbiter))
        state = campaign.load_state(self.root)
        record = state["artifacts"]["novelty_arbitration"]
        self.assertTrue(record["cold_arbitration"])
        self.assertEqual(record["arbiter_thread_id"], "arbiter-thread")
        self.assertEqual(record["review_thread_id"], "reviewer-thread")
        self.assertEqual(state["research_track"], "new_mechanism")
        self.assertEqual(state["control"]["state"], "needs_agent")

    def test_rejected_review_automatically_returns_to_portfolio(self) -> None:
        review = self.prepare_novelty_review(
            decision="exact_prior_reject",
            claim_class="new_mechanism",
        )
        fake_codex = self.base / "fake-rejecting-reviewer-codex"
        cli = SCRIPTS / "campaign.py"
        fake_codex.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            f"{shlex.quote(sys.executable)} {shlex.quote(str(cli))} artifact {shlex.quote(str(self.root))} "
            f"--name novelty_review --path {shlex.quote(str(review))} --assurance provisional\n"
            f"{shlex.quote(sys.executable)} {shlex.quote(str(cli))} handoff {shlex.quote(str(self.root))} "
            "--state needs_agent --reason 'independent novelty review rejected candidate'\n"
            "printf '%s\\n' '{\"type\":\"thread.started\",\"thread_id\":\"rejecting-reviewer-thread\"}'\n",
            encoding="utf-8",
        )
        fake_codex.chmod(0o755)
        with mock.patch.object(controller.campaign, "live_preflight", return_value={}):
            controller.run_novelty_reviewer(self.root, str(fake_codex))
        state = campaign.load_state(self.root)
        self.assertEqual(state["phase"], "portfolio")
        self.assertEqual(state["control"]["state"], "needs_agent")
        self.assertIn("automatically promoted backup candidate candidate-two", state["control"]["reason"])
        self.assertNotIn("research_track", state)
        portfolio = json.loads((self.root / "CANDIDATE_PORTFOLIO.json").read_text(encoding="utf-8"))
        self.assertEqual(portfolio["active_candidate_id"], "candidate-two")
        self.assertEqual(portfolio["candidates"][0]["status"], "eliminated")
        self.assertNotIn("idea_report", state["artifacts"])
        self.assertNotIn("novelty_audit", state["artifacts"])
        self.assertNotIn("novelty_review", state["artifacts"])

    def test_missing_agent_handoff_schedules_bounded_recovery(self) -> None:
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
        self.assertEqual(state["status"], "active")
        self.assertEqual(state["control"]["state"], "waiting_time")
        self.assertEqual(state["control"]["agent_turns"], 1)
        self.assertEqual(state["control"]["thread_id"], "thread-test")
        self.assertIn("automatic recovery 1", state["control"]["reason"])
        self.assertEqual(state["control"]["recovery"]["category"], "missing_handoff")
        self.assertEqual(state["control"]["recovery"]["target_state"], "needs_agent")

    def test_agent_prompt_requires_approved_packed_model_assets(self) -> None:
        prompt = controller.agent_prompt(self.root, campaign.load_state(self.root))
        self.assertIn("approval.allow_model_publish=true", prompt)
        self.assertIn("/g/data/wa66/Xiangyu/Data/models", prompt)
        self.assertIn("exactly one .tar.zst", prompt)
        self.assertIn("compute job's PBS jobfs", prompt)

    def test_stale_agent_state_schedules_recovery(self) -> None:
        with campaign.locked_state(self.root) as state:
            state["control"].update({"state": "agent_running", "reason": "simulated controller loss"})
        code, _, error = self.call(str(self.root), "--start")
        self.assertEqual(code, 0, error)
        state = campaign.load_state(self.root)
        self.assertEqual(state["status"], "active")
        self.assertEqual(state["control"]["state"], "waiting_time")
        self.assertEqual(state["control"]["agent_turns"], 0)
        self.assertEqual(state["control"]["recovery"]["category"], "stale_author")

    def test_stale_novelty_reviewer_state_schedules_recovery(self) -> None:
        with campaign.locked_state(self.root) as state:
            state["control"].update(
                {"state": "novelty_reviewer_running", "reason": "simulated controller loss"}
            )
        code, _, error = self.call(str(self.root), "--start")
        self.assertEqual(code, 0, error)
        state = campaign.load_state(self.root)
        self.assertEqual(state["status"], "active")
        self.assertEqual(state["control"]["state"], "waiting_time")
        self.assertEqual(
            state["control"]["recovery"]["category"],
            "stale_novelty_reviewer",
        )

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
