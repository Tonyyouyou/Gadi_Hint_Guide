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
        self.model_root = self.data_root / "models"
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

    def init(
        self,
        *,
        max_files: int = 64,
        max_su: int = 500,
        allow_diagnostic_final: bool = False,
    ) -> None:
        arguments = [
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
        ]
        if allow_diagnostic_final:
            arguments.append("--allow-diagnostic-final")
        code, _, error = self.call(*arguments)
        self.assertEqual(code, 0, error)

    def approve(
        self,
        *,
        allow_cancel: bool = False,
        allow_storage: bool = False,
        allow_model: bool = False,
    ) -> None:
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
        if allow_model:
            arguments.append("--allow-model-publish")
        code, _, error = self.call(*arguments)
        self.assertEqual(code, 0, error)

    def init_audio(self, *, human_policy: str = "pause_when_required") -> None:
        code, _, error = self.call(
            "init",
            str(self.root),
            "--campaign-id",
            "audio-campaign",
            "--idea",
            "discover a publishable contribution across audio AI",
            "--domain-pack",
            "audio",
            "--human-evaluation-policy",
            human_policy,
            "--workspace",
            str(self.workspace),
            "--projects",
            "wa66,ey69",
            "--deadline",
            "2099-01-01T00:00:00Z",
            "--environment",
            str(self.image),
            "--data",
            str(self.data),
        )
        self.assertEqual(code, 0, error)

    def add_batch(
        self,
        experiment_id: str,
        stage: str,
        *,
        expected_files: int = 8,
    ) -> tuple[int, str, str]:
        return self.call(
            "experiment-add",
            str(self.root),
            "--id",
            experiment_id,
            "--stage",
            stage,
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

    def add_sanity(self, *, expected_files: int = 8) -> tuple[int, str, str]:
        return self.add_batch("sanity-001", "sanity", expected_files=expected_files)

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

    def record_artifact(self, name: str, path: Path, assurance: str) -> None:
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

    def write_idea_report(self) -> Path:
        path = self.root / "IDEA_REPORT.md"
        path.write_text(
            "# Candidate\n\nUse an adaptive replay decision to preserve stable outputs.\n",
            encoding="utf-8",
        )
        self.record_artifact("idea_report", path, "provisional")
        return path

    def write_candidate_portfolio(self, *, candidate_id: str = "adaptive-replay") -> Path:
        state = CAMPAIGN.load_state(self.root)
        existing = state["artifacts"].get("candidate_portfolio")
        if existing:
            return Path(existing["path"])
        candidates = []
        for index, (item_id, status) in enumerate(
            ((candidate_id, "active"), ("backup-one", "backup"), ("backup-two", "backup"))
        ):
            candidates.append(
                {
                    "id": item_id,
                    "status": status,
                    "observation": f"Observed reproducible behavior {index}.",
                    "causal_hypothesis": f"Mechanism hypothesis {index}.",
                    "mechanism": f"Candidate intervention {index}.",
                    "predicted_signature": f"Predicted signature {index}.",
                    "falsifier": f"Disconfirming outcome {index}.",
                    "cheap_test": f"Small distinguishing test {index}.",
                    "nearest_work_delta": f"Remaining novelty delta {index}.",
                    "estimated_cost": {"su": 1, "jobs": 1, "persistent_entries": 2},
                }
            )
        path = self.root / "CANDIDATE_PORTFOLIO.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": CAMPAIGN.PORTFOLIO_SCHEMA_VERSION,
                    "mission_sha256": state["mission_sha256"],
                    "route_sha256": state["route"]["sha256"],
                    "created_at": CAMPAIGN.utc_now(),
                    "active_candidate_id": candidate_id,
                    "candidates": candidates,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        self.record_artifact("candidate_portfolio", path, "provisional")
        return path

    def novelty_audit_payload(
        self,
        idea_report: Path,
        *,
        candidate_id: str = "adaptive-replay",
    ) -> dict[str, object]:
        portfolio = self.write_candidate_portfolio(candidate_id=candidate_id)
        state = CAMPAIGN.load_state(self.root)
        searches = {
            category: [f"{category} adaptive replay"]
            for category in CAMPAIGN.NOVELTY_SEARCH_CATEGORIES
        }
        sources = [
            {
                "id": f"a{index}",
                "title": f"Primary paper {index}",
                "url": f"https://example.org/paper-{index}",
                "year": 2024,
                "checked_locator": f"Section {index}",
                "mechanism_evidence": "The full text specifies the compared replay mechanism.",
                "primary_source": True,
                "full_text_checked": True,
            }
            for index in range(1, 4)
        ]
        payload = {
            "schema_version": CAMPAIGN.NOVELTY_SCHEMA_VERSION,
            "candidate_id": candidate_id,
            "idea_report_sha256": CAMPAIGN.sha256_file(idea_report),
            "mission_sha256": state["mission_sha256"],
            "route_sha256": state["route"]["sha256"],
            "candidate_portfolio_sha256": CAMPAIGN.sha256_file(portfolio),
            "searched_at": CAMPAIGN.utc_now(),
            "mechanism_without_brand": "Replay only outputs whose stability score exceeds an adaptive threshold.",
            "claim_class": "new_mechanism",
            "verdict": "plausibly_novel",
            "primitives": [
                {"id": "stability-score", "description": "Estimate whether an emitted prefix is stable."},
                {"id": "selective-replay", "description": "Replay only unstable output regions."},
            ],
            "searches": searches,
            "sources": sources,
            "nearest_neighbors": [
                {
                    "source_id": source["id"],
                    "mechanism_overlap": "Shares one replay or stability primitive.",
                    "remaining_delta": "Does not couple adaptive stability with selective replay.",
                }
                for source in sources
            ],
            "brand_substitution_test": {
                "outcome": "materially_changed",
                "explanation": "Removing the task label still leaves an adaptive replay mechanism.",
            },
            "combination_test": {
                "existing_combination": False,
                "decomposition": "stability scoring plus selective replay",
                "non_obvious_interaction": "The score controls replay boundaries rather than only confidence reporting.",
            },
            "strongest_rejection": "Confidence-triggered recomputation may already implement the same mechanism.",
            "author_rebuttal": "The checked work uses confidence for stopping, not replay-boundary selection.",
        }
        return payload

    def write_novelty_audit(
        self,
        idea_report: Path,
        *,
        payload: dict[str, object] | None = None,
    ) -> Path:
        path = self.root / "NOVELTY_AUDIT.json"
        path.write_text(
            json.dumps(payload or self.novelty_audit_payload(idea_report), indent=2) + "\n",
            encoding="utf-8",
        )
        self.record_artifact("novelty_audit", path, "provisional")
        return path

    def novelty_review_payload(
        self,
        audit: Path,
        *,
        decision: str = "clear_to_plan",
        claim_class: str = "new_mechanism",
    ) -> dict[str, object]:
        audit_payload = json.loads(audit.read_text(encoding="utf-8"))
        sources = [
            {
                "id": f"r{index}",
                "title": f"Independent primary paper {index}",
                "url": f"https://review.example.org/paper-{index}",
                "year": 2025,
                "checked_locator": f"Methods section {index}",
                "mechanism_evidence": "The methods expose the independently compared primitive.",
                "primary_source": True,
                "full_text_checked": True,
            }
            for index in range(1, 4)
        ]
        payload = {
            "schema_version": CAMPAIGN.NOVELTY_SCHEMA_VERSION,
            "candidate_id": audit_payload["candidate_id"],
            "audit_sha256": CAMPAIGN.sha256_file(audit),
            "reviewed_at": CAMPAIGN.utc_now(),
            "independent_context": True,
            "decision": decision,
            "claim_class": claim_class,
            "reviewer_searches": {
                category: [f"independent {category} replay"]
                for category in CAMPAIGN.NOVELTY_SEARCH_CATEGORIES
            },
            "sources": sources,
            "prior_checks": {
                "earliest": {"source_id": "r1", "conclusion": "Earliest primitive precedent."},
                "closest": {"source_id": "r2", "conclusion": "Closest system lacks the interaction."},
                "newest": {"source_id": "r3", "conclusion": "Newest checked work remains distinct."},
                "exact_combination": {"source_id": None, "conclusion": "No exact combination was found."},
            },
            "primitive_overlap": [
                {
                    "primitive_id": "stability-score",
                    "source_ids": ["r1", "r2"],
                    "assessment": "Known alone, but not as the replay-boundary controller.",
                },
                {
                    "primitive_id": "selective-replay",
                    "source_ids": ["r2", "r3"],
                    "assessment": "Known alone, but the adaptive coupling was not found.",
                },
            ],
            "strongest_rejection": "The proposal could be ordinary confidence-triggered recomputation.",
            "author_rebuttal_assessment": "The rebuttal survives only for the coupled boundary rule.",
            "blocking_overlaps": [],
            "required_changes": [],
        }
        if decision == "conditional_probe":
            payload["probe_plan"] = {
                "question": "Does the coupled rule outperform a naive serial composition?",
                "naive_combination_baseline": "Apply stability scoring, then selective replay independently.",
                "distinguishing_outcome": "The coupled boundary rule improves latency at matched error.",
                "falsifier": "No improvement over the naive composition at matched error.",
            }
        if decision == "exact_prior_reject":
            payload["prior_checks"]["exact_combination"] = {
                "source_id": "r2",
                "conclusion": "The closest paper implements the same boundary rule.",
                "functionally_equivalent": True,
                "equivalence_evidence": "Methods section 2 uses the same score, trigger, and replay scope.",
            }
        return payload

    def record_cold_review(
        self,
        audit: Path,
        *,
        decision: str = "clear_to_plan",
        claim_class: str = "new_mechanism",
    ) -> Path:
        review = self.root / "NOVELTY_REVIEW.json"
        review.write_text(
            json.dumps(
                self.novelty_review_payload(audit, decision=decision, claim_class=claim_class),
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        with CAMPAIGN.locked_state(self.root) as state:
            state["control"]["state"] = "novelty_reviewer_running"
        self.record_artifact("novelty_review", review, "provisional")
        with CAMPAIGN.locked_state(self.root) as state:
            state["artifacts"]["novelty_review"].update(
                {
                    "cold_review": True,
                    "review_thread_id": "review-thread-test",
                    "author_thread_id": "author-thread-test",
                    "reviewed_audit_sha256": CAMPAIGN.sha256_file(audit),
                }
            )
            state["control"].update(
                {"state": "needs_agent", "novelty_review_thread_id": "review-thread-test"}
            )
        return review

    def record_method_clearance(self) -> tuple[Path, Path, Path]:
        idea = self.write_idea_report()
        audit = self.write_novelty_audit(idea)
        review = self.record_cold_review(audit)
        return idea, audit, review

    def record_conditional_review(self) -> tuple[Path, Path, Path]:
        idea = self.write_idea_report()
        audit = self.write_novelty_audit(idea)
        with CAMPAIGN.locked_state(self.root) as state:
            state["phase"] = "novelty_review"
        review = self.record_cold_review(
            audit,
            decision="conditional_probe",
            claim_class="new_mechanism",
        )
        return idea, audit, review

    def complete_probe(self, experiment_id: str) -> Path:
        with CAMPAIGN.locked_state(self.root) as state:
            experiment = state["experiments"][experiment_id]
            success_file = Path(experiment["success_file"])
            success_file.parent.mkdir(parents=True, exist_ok=True)
            success_file.write_text('{"status":"ok"}\n', encoding="utf-8")
            experiment["status"] = "completed"
        return success_file

    def record_novelty_rebuttal(
        self,
        audit: Path,
        review: Path,
        experiment_ids: list[str],
    ) -> Path:
        results = []
        for experiment_id in experiment_ids:
            state = CAMPAIGN.load_state(self.root)
            success_file = Path(state["experiments"][experiment_id]["success_file"])
            results.append(
                {
                    "experiment_id": experiment_id,
                    "success_file_sha256": CAMPAIGN.sha256_file(success_file),
                    "finding": "The coupled rule beats the naive composition at matched error.",
                }
            )
        payload = {
            "schema_version": CAMPAIGN.NOVELTY_SCHEMA_VERSION,
            "candidate_id": "adaptive-replay",
            "audit_sha256": CAMPAIGN.sha256_file(audit),
            "review_sha256": CAMPAIGN.sha256_file(review),
            "written_at": CAMPAIGN.utc_now(),
            "probe_experiment_ids": experiment_ids,
            "probe_results": results,
            "reviewer_objections": [
                {
                    "objection": "The mechanism may be a naive serial composition.",
                    "response": "The controlled probe isolates a coupled boundary effect.",
                    "evidence_experiment_ids": experiment_ids,
                }
            ],
            "naive_combination_baseline": "Independent stability scoring followed by replay.",
            "distinguishing_result": "Coupling improves latency at matched error.",
            "author_position": "advance",
            "remaining_risks": ["The effect may vary by model family."],
        }
        path = self.root / "NOVELTY_REBUTTAL.json"
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        self.record_artifact("novelty_rebuttal", path, "provisional")
        return path

    def record_novelty_arbitration(
        self,
        audit: Path,
        review: Path,
        rebuttal: Path,
        *,
        decision: str = "clear_to_plan",
    ) -> Path:
        payload = {
            "schema_version": CAMPAIGN.NOVELTY_SCHEMA_VERSION,
            "candidate_id": "adaptive-replay",
            "audit_sha256": CAMPAIGN.sha256_file(audit),
            "review_sha256": CAMPAIGN.sha256_file(review),
            "rebuttal_sha256": CAMPAIGN.sha256_file(rebuttal),
            "arbitrated_at": CAMPAIGN.utc_now(),
            "independent_context": True,
            "decision": decision,
            "claim_class": "new_mechanism",
            "probe_validity_assessment": "The controlled comparison isolates the coupling.",
            "naive_combination_assessment": "The baseline faithfully composes the known primitives.",
            "non_obvious_interaction_assessment": "The measured boundary effect is not additive tuning.",
            "paper_contribution_assessment": "The mechanism supports a primary method claim.",
            "blocking_issues": [],
            "required_changes": [],
            "exact_prior": None,
        }
        path = self.root / "NOVELTY_ARBITRATION.json"
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        with CAMPAIGN.locked_state(self.root) as state:
            state["control"]["state"] = "novelty_arbiter_running"
        self.record_artifact("novelty_arbitration", path, "provisional")
        with CAMPAIGN.locked_state(self.root) as state:
            state["artifacts"]["novelty_arbitration"].update(
                {
                    "cold_arbitration": True,
                    "arbiter_thread_id": "arbiter-thread-test",
                    "author_thread_id": "author-thread-test",
                    "review_thread_id": "review-thread-test",
                    "reviewed_rebuttal_sha256": CAMPAIGN.sha256_file(rebuttal),
                }
            )
            state["control"].update(
                {
                    "state": "needs_agent",
                    "novelty_arbitration_thread_id": "arbiter-thread-test",
                }
            )
        return path

    def test_init_creates_compact_draft_state(self) -> None:
        self.init()
        state = CAMPAIGN.load_state(self.root)
        self.assertEqual(state["status"], "draft")
        self.assertEqual(state["control"]["state"], "waiting_human")
        self.assertEqual(state["schema_version"], CAMPAIGN.SCHEMA_VERSION)
        self.assertEqual(state["route"]["status"], "resolved")
        self.assertEqual(CAMPAIGN.count_entries(self.root), 3)

    def test_audio_mission_starts_with_unresolved_composable_route(self) -> None:
        self.init_audio()
        state = CAMPAIGN.load_state(self.root)
        self.assertEqual(state["mission"]["domain_packs"], ["audio"])
        self.assertEqual(state["route"]["status"], "unresolved")
        self.assertIn("audio", state["adapter_registry"]["packs"])

    def test_route_cannot_omit_a_mission_fixed_adapter(self) -> None:
        registry = CAMPAIGN.adapter_registry.load_registry()
        mission = {
            "schema_version": CAMPAIGN.MISSION_SCHEMA_VERSION,
            "objective": "Optimize TTS inference without changing the task.",
            "exploration_mode": "directed",
            "domain_packs": ["audio"],
            "acceptable_contributions": ["new_system"],
            "diagnostic_as_final": False,
            "fallback_policy": "return_to_discovery",
            "human_evaluation_policy": "pause_when_required",
            "target_output": "paper",
            "adapter_selection": {
                "task": ["audio.speech-generation"],
                "model": ["agent_select"],
                "lever": ["core.systems"],
                "evidence": ["agent_select"],
                "constraint": [],
            },
        }
        CAMPAIGN.validate_mission(mission, registry)
        with self.assertRaisesRegex(CAMPAIGN.CampaignError, "mission-fixed task"):
            CAMPAIGN.build_route(
                mission,
                CAMPAIGN.sha256_json(mission),
                registry,
                [
                    "audio.speech-understanding",
                    "audio.encoder-discriminative",
                    "core.systems",
                    "core.system-measurement",
                    "audio.reference-task-evaluation",
                ],
                reason="incorrectly switched from TTS to ASR",
            )

    def test_embedded_mission_cannot_diverge_from_mission_artifact(self) -> None:
        self.init()
        self.approve()
        with CAMPAIGN.locked_state(self.root) as state:
            state["mission"]["objective"] = "silently changed objective"
        with self.assertRaisesRegex(CAMPAIGN.CampaignError, "immutable MISSION.json"):
            CAMPAIGN.validate_route(CAMPAIGN.load_state(self.root))

    def test_route_set_resolves_audio_systems_dependencies(self) -> None:
        self.init_audio()
        self.approve()
        code, output, error = self.call(
            "route-set",
            str(self.root),
            "--adapters",
            ",".join(
                (
                    "audio.speech-understanding",
                    "audio.encoder-discriminative",
                    "core.systems",
                    "core.system-measurement",
                    "audio.reference-task-evaluation",
                )
            ),
            "--reason",
            "measured encoder opportunity",
        )
        self.assertEqual(code, 0, error)
        self.assertIn("audio.encoder-discriminative", output)
        state = CAMPAIGN.load_state(self.root)
        self.assertEqual(state["route"]["status"], "resolved")
        self.assertIn("audio.packed-media", state["route"]["adapters"])

    def test_route_set_rejects_missing_evidence_dependency(self) -> None:
        self.init_audio()
        self.approve()
        code, _, error = self.call(
            "route-set",
            str(self.root),
            "--adapters",
            "audio.speech-understanding,audio.encoder-discriminative,core.systems,core.system-measurement",
            "--reason",
            "incomplete route",
        )
        self.assertNotEqual(code, 0)
        self.assertIn("missing required evidence", error)

    def test_human_evaluation_policy_forbid_rejects_tts_route(self) -> None:
        self.init_audio(human_policy="forbid")
        self.approve()
        code, _, error = self.call(
            "route-set",
            str(self.root),
            "--adapters",
            ",".join(
                (
                    "audio.speech-generation",
                    "audio.diffusion-flow",
                    "core.optimization-rl",
                    "core.controlled-evidence",
                    "core.optimization-dynamics",
                    "audio.reference-task-evaluation",
                    "audio.perceptual-generation-evaluation",
                    "core.human-evaluation",
                )
            ),
            "--reason",
            "TTS preference optimization",
        )
        self.assertNotEqual(code, 0)
        self.assertIn("requires human evaluation", error)

    def test_perceptual_tts_route_requires_human_artifact_and_detects_tampering(self) -> None:
        self.init_audio()
        self.approve()
        adapters = ",".join(
            (
                "audio.speech-generation",
                "audio.diffusion-flow",
                "audio.generative-quality-control",
                "core.controlled-evidence",
                "audio.reference-task-evaluation",
                "audio.perceptual-generation-evaluation",
                "core.human-evaluation",
            )
        )
        code, _, error = self.call(
            "route-set",
            str(self.root),
            "--adapters",
            adapters,
            "--reason",
            "TTS perceptual quality mechanism",
        )
        self.assertEqual(code, 0, error)
        state = CAMPAIGN.load_state(self.root)
        self.assertIn("human_evaluation", CAMPAIGN.required_completion_artifacts(state))
        with CAMPAIGN.locked_state(self.root) as mutable:
            mutable["route"]["human_evaluation"] = "never"
        with self.assertRaisesRegex(CAMPAIGN.CampaignError, "changed after resolution"):
            CAMPAIGN.required_completion_artifacts(CAMPAIGN.load_state(self.root))

    def test_human_evaluation_is_bound_to_current_claim_lineage(self) -> None:
        self.init()
        self.approve()
        _, audit, _ = self.record_method_clearance()
        state = CAMPAIGN.load_state(self.root)
        portfolio = json.loads(
            CAMPAIGN.artifact_file(state, "candidate_portfolio").read_text(encoding="utf-8")
        )
        evidence = {
            "schema_version": CAMPAIGN.HUMAN_EVALUATION_SCHEMA_VERSION,
            "status": "complete",
            "mission_sha256": state["mission_sha256"],
            "route_sha256": state["route"]["sha256"],
            "candidate_id": portfolio["active_candidate_id"],
            "novelty_audit_sha256": CAMPAIGN.sha256_file(audit),
            "evidence_sha256": "a" * 64,
            "protocol": "new_study",
            "source": "packed blinded ratings fixture",
            "population": "documented eligible listeners",
            "blinded": True,
            "rater_count": 20,
            "judgment_count": 200,
            "metrics": {"preference_rate": 0.6},
            "limitations": ["unit-test fixture"],
        }
        path = self.root / "HUMAN_EVALUATION.json"
        path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        CAMPAIGN.validate_human_evaluation(state, path)

        bad = dict(evidence)
        bad["candidate_id"] = "backup-one"
        bad_path = self.root / "BAD_HUMAN_EVALUATION.json"
        bad_path.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(CAMPAIGN.CampaignError, "active candidate"):
            CAMPAIGN.validate_human_evaluation(state, bad_path)

        with CAMPAIGN.locked_state(self.root) as mutable:
            mutable["control"]["state"] = "waiting_human"
        self.record_artifact("human_evaluation", path, "accepted")

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
        self.record_method_clearance()
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

    def test_method_experiment_is_blocked_but_profile_is_allowed_before_novelty_review(self) -> None:
        self.init()
        self.approve()
        code, _, error = self.add_batch("main-before-review", "main")
        self.assertNotEqual(code, 0)
        self.assertIn("novelty_audit", error)
        code, _, error = self.add_batch("profile-before-review", "profile")
        self.assertEqual(code, 0, error)

    def test_novelty_audit_requires_every_search_route(self) -> None:
        self.init()
        self.approve()
        idea = self.write_idea_report()
        payload = self.novelty_audit_payload(idea)
        searches = payload["searches"]
        assert isinstance(searches, dict)
        del searches["adjacent_fields"]
        audit = self.root / "NOVELTY_AUDIT.json"
        audit.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        code, _, error = self.call(
            "artifact",
            str(self.root),
            "--name",
            "novelty_audit",
            "--path",
            str(audit),
            "--assurance",
            "provisional",
        )
        self.assertNotEqual(code, 0)
        self.assertIn("adjacent_fields", error)

    def test_author_thread_cannot_register_its_own_novelty_review(self) -> None:
        self.init()
        self.approve()
        idea = self.write_idea_report()
        audit = self.write_novelty_audit(idea)
        review = self.root / "NOVELTY_REVIEW.json"
        review.write_text(
            json.dumps(self.novelty_review_payload(audit), indent=2) + "\n",
            encoding="utf-8",
        )
        code, _, error = self.call(
            "artifact",
            str(self.root),
            "--name",
            "novelty_review",
            "--path",
            str(review),
            "--assurance",
            "provisional",
        )
        self.assertNotEqual(code, 0)
        self.assertIn("fresh reviewer", error)

    def test_new_review_request_invalidates_previous_verdict(self) -> None:
        self.init()
        self.approve()
        self.record_method_clearance()
        with CAMPAIGN.locked_state(self.root) as state:
            state["phase"] = "novelty_review"
        code, _, error = self.call(
            "handoff",
            str(self.root),
            "--state",
            "needs_novelty_review",
            "--reason",
            "refresh the independent search",
        )
        self.assertEqual(code, 0, error)
        state = CAMPAIGN.load_state(self.root)
        self.assertNotIn("novelty_review", state["artifacts"])
        self.assertIsNotNone(state["control"]["novelty_review_requested_at"])
        code, _, error = self.add_batch("main-after-review-request", "main")
        self.assertNotEqual(code, 0)
        self.assertIn("novelty_review", error)

    def test_planning_phase_requires_attested_cold_review(self) -> None:
        self.init()
        self.approve()
        for name in ("research_brief", "literature"):
            path = self.root / f"{name}.md"
            path.write_text(f"# {name}\n", encoding="utf-8")
            self.record_artifact(name, path, "provisional")
        self.assertEqual(
            self.call("phase", str(self.root), "discovery", "--reason", "brief and literature complete")[0],
            0,
        )
        discovery = self.root / "DISCOVERY_REPORT.md"
        discovery.write_text("# Observations and opportunities\n", encoding="utf-8")
        self.record_artifact("discovery_report", discovery, "provisional")
        self.assertEqual(
            self.call("phase", str(self.root), "portfolio", "--reason", "route and observations fixed")[0],
            0,
        )
        idea = self.write_idea_report()
        audit = self.write_novelty_audit(idea)
        self.assertEqual(
            self.call("phase", str(self.root), "novelty_review", "--reason", "candidate audited")[0],
            0,
        )
        code, _, error = self.call(
            "phase",
            str(self.root),
            "planning",
            "--reason",
            "attempt before cold review",
        )
        self.assertNotEqual(code, 0)
        self.assertIn("novelty_review", error)
        self.record_cold_review(audit)
        code, _, error = self.call(
            "phase",
            str(self.root),
            "planning",
            "--reason",
            "cold review passed",
        )
        self.assertEqual(code, 0, error)

    def test_conditional_probe_requires_rebuttal_and_independent_arbitration(self) -> None:
        self.init(max_su=100_000)
        self.approve()
        _, audit, review = self.record_conditional_review()

        code, _, error = self.add_batch("main-before-arbitration", "main")
        self.assertNotEqual(code, 0)
        self.assertIn("novelty_rebuttal", error)

        code, _, error = self.add_batch("probe-coupling", "novelty_probe")
        self.assertEqual(code, 0, error)
        success_file = self.complete_probe("probe-coupling")
        self.assertTrue(success_file.is_file())
        rebuttal = self.record_novelty_rebuttal(audit, review, ["probe-coupling"])
        code, _, error = self.call(
            "handoff",
            str(self.root),
            "--state",
            "needs_novelty_arbitration",
            "--reason",
            "bounded probe and rebuttal complete",
        )
        self.assertEqual(code, 0, error)
        arbitration = self.record_novelty_arbitration(audit, review, rebuttal)
        self.assertTrue(arbitration.is_file())

        code, _, error = self.add_batch("main-after-arbitration", "main")
        self.assertEqual(code, 0, error)
        state = CAMPAIGN.load_state(self.root)
        binding = state["experiments"]["main-after-arbitration"]["claim_binding"]
        self.assertEqual(binding["novelty_rebuttal_sha256"], CAMPAIGN.sha256_file(rebuttal))
        self.assertEqual(binding["novelty_arbitration_sha256"], CAMPAIGN.sha256_file(arbitration))

    def test_conditional_probe_registration_obeys_hard_job_cap(self) -> None:
        self.init(max_files=128, max_su=100_000)
        self.approve()
        self.record_conditional_review()
        for index in range(3):
            code, _, error = self.add_batch(f"probe-{index}", "novelty_probe", expected_files=2)
            self.assertEqual(code, 0, error)
        code, _, error = self.add_batch("probe-four", "novelty_probe", expected_files=2)
        self.assertNotEqual(code, 0)
        self.assertIn("at most three", error)

    def test_exact_prior_reject_requires_functional_equivalence_evidence(self) -> None:
        self.init()
        self.approve()
        idea = self.write_idea_report()
        audit = self.write_novelty_audit(idea)
        payload = self.novelty_review_payload(
            audit,
            decision="exact_prior_reject",
            claim_class="new_mechanism",
        )
        exact = payload["prior_checks"]["exact_combination"]
        assert isinstance(exact, dict)
        exact.pop("equivalence_evidence")
        review = self.root / "NOVELTY_REVIEW.json"
        review.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        with CAMPAIGN.locked_state(self.root) as state:
            state["control"]["state"] = "novelty_reviewer_running"
        code, _, error = self.call(
            "artifact",
            str(self.root),
            "--name",
            "novelty_review",
            "--path",
            str(review),
            "--assurance",
            "provisional",
        )
        self.assertNotEqual(code, 0)
        self.assertIn("equivalence_evidence", error)

        legacy = self.novelty_review_payload(
            audit,
            decision="derivative",
            claim_class="new_application",
        )
        review.write_text(json.dumps(legacy, indent=2) + "\n", encoding="utf-8")
        code, _, error = self.call(
            "artifact",
            str(self.root),
            "--name",
            "novelty_review",
            "--path",
            str(review),
            "--assurance",
            "provisional",
        )
        self.assertNotEqual(code, 0)
        self.assertIn("clear_to_plan, conditional_probe, or exact_prior_reject", error)

    def test_forward_phase_skip_is_rejected(self) -> None:
        self.init()
        self.approve()
        code, _, error = self.call(
            "phase",
            str(self.root),
            "planning",
            "--reason",
            "attempted shortcut",
        )
        self.assertNotEqual(code, 0)
        self.assertIn("exactly one phase", error)

    def test_derivative_idea_returns_to_discovery_when_mission_forbids_fallback(self) -> None:
        self.init()
        self.approve()
        idea = self.write_idea_report()
        audit = self.write_novelty_audit(idea)
        self.record_cold_review(audit, decision="clear_to_plan", claim_class="new_application")
        code, _, error = self.add_batch("diagnostic-baseline", "baseline")
        self.assertNotEqual(code, 0)
        self.assertIn("requires returning to discovery", error)
        code, _, error = self.add_batch("derivative-main", "main")
        self.assertNotEqual(code, 0)
        self.assertIn("requires returning to discovery", error)

    def test_explicit_diagnostic_mission_allows_baseline_but_not_primary_stage(self) -> None:
        self.init(allow_diagnostic_final=True)
        self.approve()
        idea = self.write_idea_report()
        audit = self.write_novelty_audit(idea)
        self.record_cold_review(audit, decision="clear_to_plan", claim_class="new_application")
        code, _, error = self.add_batch("diagnostic-baseline", "baseline")
        self.assertEqual(code, 0, error)
        code, _, error = self.add_batch("derivative-main", "main")
        self.assertNotEqual(code, 0)
        self.assertIn("requires returning to discovery", error)

    def test_changing_idea_report_invalidates_novelty_clearance(self) -> None:
        self.init()
        self.approve()
        idea, _, _ = self.record_method_clearance()
        idea.write_text("# Changed candidate\n", encoding="utf-8")
        code, _, error = self.add_batch("stale-clearance-main", "main")
        self.assertNotEqual(code, 0)
        self.assertIn("changed after registration", error)

    def test_claim_experiment_cannot_cross_candidate_lineage(self) -> None:
        self.init()
        self.approve()
        self.record_method_clearance()
        code, _, error = self.add_batch("old-candidate-main", "main")
        self.assertEqual(code, 0, error)

        state = CAMPAIGN.load_state(self.root)
        portfolio_path = CAMPAIGN.artifact_file(state, "candidate_portfolio")
        portfolio = json.loads(portfolio_path.read_text(encoding="utf-8"))
        portfolio["active_candidate_id"] = "backup-one"
        portfolio["created_at"] = CAMPAIGN.utc_now()
        for candidate in portfolio["candidates"]:
            if candidate["id"] == "adaptive-replay":
                candidate["status"] = "backup"
            elif candidate["id"] == "backup-one":
                candidate["status"] = "active"
        portfolio_path.write_text(json.dumps(portfolio, indent=2) + "\n", encoding="utf-8")
        self.record_artifact("candidate_portfolio", portfolio_path, "provisional")

        idea = self.write_idea_report()
        audit = self.write_novelty_audit(
            idea,
            payload=self.novelty_audit_payload(idea, candidate_id="backup-one"),
        )
        self.record_cold_review(audit)
        code, _, error = self.call("submit", str(self.root), "--id", "old-candidate-main")
        self.assertNotEqual(code, 0)
        self.assertIn("different candidate or novelty lineage", error)

    def test_skill_revision_change_requires_explicit_paused_adoption(self) -> None:
        self.init()
        self.approve()
        with CAMPAIGN.locked_state(self.root) as state:
            state["skill_reference"]["commit"] = "0" * 40
        code, _, error = self.add_sanity()
        self.assertNotEqual(code, 0)
        self.assertIn("differs from the campaign pin", error)
        self.assertEqual(
            self.call("handoff", str(self.root), "--state", "paused", "--reason", "review skill update")[0],
            0,
        )
        code, _, error = self.call(
            "skill-adopt",
            str(self.root),
            "--by",
            "unit-test",
            "--reason",
            "reviewed novelty-gate update",
        )
        self.assertEqual(code, 0, error)
        self.assertEqual(
            self.call("resume", str(self.root), "--reason", "skill revision adopted")[0],
            0,
        )
        self.assertEqual(self.add_sanity()[0], 0)

    def test_unapproved_draft_can_adopt_reviewed_skill_revision(self) -> None:
        self.init()
        with CAMPAIGN.locked_state(self.root) as state:
            state["skill_reference"]["commit"] = "0" * 40
        code, _, error = self.call(
            "skill-adopt",
            str(self.root),
            "--by",
            "unit-test",
            "--reason",
            "reviewed revision before campaign approval",
        )
        self.assertEqual(code, 0, error)
        state = CAMPAIGN.load_state(self.root)
        self.assertNotEqual(state["skill_reference"]["commit"], "0" * 40)
        self.assertEqual(state["status"], "draft")

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
        self.assertEqual(
            state["experiments"]["build-env-v2"]["clearance"],
            "discovery_infrastructure",
        )
        self.assertEqual(state["experiments"]["build-env-v2"]["status"], "queued")

    def test_external_model_job_requires_typed_single_archive_and_capability(self) -> None:
        self.init()
        self.approve(allow_storage=True, allow_model=True)
        self.model_root.mkdir()
        pbs = self.workspace / "acquire-model.pbs"
        success = self.model_root / "public-model-deadbeef.tar.zst"
        pbs.write_text(
            "#!/usr/bin/env bash\n"
            "#PBS -P wa66\n#PBS -q copyq\n#PBS -N model\n"
            "#PBS -l ncpus=1\n#PBS -l mem=8GB\n#PBS -l jobfs=100GB\n"
            "#PBS -l walltime=01:00:00\n#PBS -l storage=gdata/wa66\n#PBS -l wd\n"
            f"#PBS -j oe\n#PBS -o {self.root}/acquire-model.log\n"
            "set -euo pipefail\nexport TMPDIR=\"$PBS_JOBFS/tmp\"\nmkdir -p \"$TMPDIR\"\n"
            "PACKER=/g/data/wa66/Xiangyu/.codex/skills/run-on-gadi/scripts/pack_data.sh\n"
            "bash \"$PACKER\" --kind model --help\n",
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
            "acquire-model-v1",
            "--stage",
            "model",
            "--pbs",
            str(pbs),
            "--success-path",
            str(success),
            "--expected-files",
            "1",
        )
        with mock.patch.object(CAMPAIGN, "lint_script", return_value=lint_report):
            code, output, error = self.call(*arguments)
        self.assertEqual(code, 0, error)
        self.assertIn(str(success), output)
        with mock.patch.object(CAMPAIGN, "lint_script", return_value=lint_report):
            code, output, error = self.call(*arguments, "--execute")
        self.assertEqual(code, 0, error)
        self.assertIn("12345.gadi-pbs", output)
        experiment = CAMPAIGN.load_state(self.root)["experiments"]["acquire-model-v1"]
        self.assertEqual(experiment["stage"], "model")
        self.assertEqual(experiment["expected_files"], 1)

    def test_external_model_job_rejects_unpacked_or_multi_entry_targets(self) -> None:
        self.init()
        self.approve(allow_storage=True, allow_model=True)
        self.model_root.mkdir()
        pbs = self.workspace / "acquire-model-invalid.pbs"
        pbs.write_text(
            "#!/usr/bin/env bash\n"
            "#PBS -P wa66\n#PBS -q copyq\n#PBS -N model\n"
            "#PBS -l ncpus=1\n#PBS -l mem=8GB\n#PBS -l jobfs=100GB\n"
            "#PBS -l walltime=01:00:00\n#PBS -l storage=gdata/wa66\n#PBS -l wd\n"
            f"#PBS -j oe\n#PBS -o {self.root}/acquire-model-invalid.log\n"
            "set -euo pipefail\nPACKER=/g/data/wa66/Xiangyu/.codex/skills/run-on-gadi/scripts/pack_data.sh\n"
            "bash \"$PACKER\" --kind model --help\n",
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
        with mock.patch.object(CAMPAIGN, "lint_script", return_value=lint_report):
            code, _, error = self.call(
                "external-submit",
                str(self.root),
                "--id",
                "bad-model-v1",
                "--stage",
                "model",
                "--pbs",
                str(pbs),
                "--success-path",
                str(self.data_root / "loose-model"),
                "--expected-files",
                "2",
            )
        self.assertNotEqual(code, 0)
        self.assertIn("exactly one .tar.zst", error)

        with CAMPAIGN.locked_state(self.root) as state:
            state["approval"]["allow_model_publish"] = False
        with mock.patch.object(CAMPAIGN, "lint_script", return_value=lint_report):
            code, _, error = self.call(
                "external-submit",
                str(self.root),
                "--id",
                "unapproved-model-v1",
                "--stage",
                "model",
                "--pbs",
                str(pbs),
                "--success-path",
                str(self.model_root / "public-model-deadbeef.tar.zst"),
                "--expected-files",
                "1",
                "--execute",
            )
        self.assertNotEqual(code, 0)
        self.assertIn("allow_model_publish", error)

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
        idea, audit, review = self.record_method_clearance()
        state = CAMPAIGN.load_state(self.root)
        paths: dict[str, Path] = {
            "mission": Path(state["artifacts"]["mission"]["path"]),
            "candidate_portfolio": Path(state["artifacts"]["candidate_portfolio"]["path"]),
            "idea_report": idea,
            "novelty_audit": audit,
            "novelty_review": review,
        }
        paper_output = self.root / "paper"
        paper_output.mkdir(exist_ok=True)
        paper_source_dir = self.workspace / "paper"
        paper_source_dir.mkdir(exist_ok=True)
        for name in CAMPAIGN.REQUIRED_COMPLETION_ARTIFACTS:
            if name in paths:
                continue
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
            if name in {"mission", "candidate_portfolio", "idea_report", "novelty_audit", "novelty_review"}:
                continue
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
