#!/usr/bin/env python3
"""Tests for composable autoresearch adapter packs."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import adapter_registry  # noqa: E402


class AdapterRegistryTests(unittest.TestCase):
    def test_builtin_registry_is_valid(self) -> None:
        registry = adapter_registry.load_registry()
        self.assertEqual(set(registry["packs"]), {"core", "audio"})
        self.assertGreaterEqual(len(registry["adapters"]), 40)
        self.assertEqual(registry["adapters"]["audio.music-generation"]["kind"], "task")

    def test_route_requires_dependency_complete_evidence(self) -> None:
        registry = adapter_registry.load_registry()
        with self.assertRaisesRegex(adapter_registry.AdapterError, "missing required evidence"):
            adapter_registry.resolve_bundle(
                registry,
                ["audio"],
                [
                    "audio.speech-generation",
                    "audio.diffusion-flow",
                    "core.optimization-rl",
                    "core.controlled-evidence",
                    "core.optimization-dynamics",
                    "audio.reference-task-evaluation",
                    "audio.perceptual-generation-evaluation",
                ],
            )

    def test_tts_route_resolves_human_evaluation_requirement(self) -> None:
        registry = adapter_registry.load_registry()
        route = adapter_registry.resolve_bundle(
            registry,
            ["audio"],
            [
                "audio.speech-generation",
                "audio.diffusion-flow",
                "core.optimization-rl",
                "core.controlled-evidence",
                "core.optimization-dynamics",
                "audio.reference-task-evaluation",
                "audio.perceptual-generation-evaluation",
                "core.human-evaluation",
            ],
        )
        self.assertEqual(route["human_evaluation"], "required")
        self.assertIn("audio.packed-media", route["adapters"])
        self.assertIn("audio.content-leakage", route["adapters"])

    def test_new_domain_pack_needs_no_core_code_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copy2(adapter_registry.adapter_root() / "core.json", root / "core.json")
            pack = {
                "schema_version": adapter_registry.ADAPTER_SCHEMA_VERSION,
                "pack_id": "vision",
                "title": "Vision research",
                "description": "Minimal extension-pack fixture.",
                "reference": "references/adapter-system.md",
                "default_adapters": [],
                "adapters": [
                    {
                        "id": "vision.image-understanding",
                        "kind": "task",
                        "title": "Image understanding",
                        "description": "A fixture task adapter.",
                        "reference": "references/adapter-system.md",
                        "required_evidence": ["core.controlled-evidence"],
                        "discovery_questions": ["Which visual relation fails reproducibly?"],
                        "novelty_traps": ["Renaming a generic classifier."],
                        "human_evaluation": "never",
                    },
                    {
                        "id": "vision.encoder",
                        "kind": "model",
                        "title": "Vision encoder",
                        "description": "A fixture model adapter.",
                        "reference": "references/adapter-system.md",
                        "required_evidence": [],
                        "discovery_questions": ["Which representation loses task information?"],
                        "novelty_traps": ["Changing a backbone name only."],
                        "human_evaluation": "never",
                    },
                ],
            }
            (root / "vision.json").write_text(json.dumps(pack), encoding="utf-8")
            registry = adapter_registry.load_registry(root)
            route = adapter_registry.resolve_bundle(
                registry,
                ["vision"],
                [
                    "vision.image-understanding",
                    "vision.encoder",
                    "core.architecture",
                    "core.controlled-evidence",
                ],
            )
            self.assertEqual(route["by_kind"]["task"], ["vision.image-understanding"])
            self.assertEqual(route["by_kind"]["model"], ["vision.encoder"])


if __name__ == "__main__":
    unittest.main()
