# Composable Research Adapters

## Contents

1. Architecture
2. Mission contract
3. Adapter contract
4. Route resolution
5. Claim compatibility
6. Human evidence
7. Extending the registry

## Architecture

Keep three responsibilities separate:

- The campaign core owns state, budgets, storage, PBS, evidence lineage, review, and recovery.
- The scientific workflow owns opportunity discovery, candidate competition, novelty, and claim gates.
- Adapter packs supply domain, task, model, research-lever, evidence, and constraint knowledge.

Do not add task names or domain branches to `campaign.py` or `controller.py`. Those programs
validate a generic adapter contract. A new domain should normally require one pack under
`adapters/`, one directly linked reference file, and tests.

## Mission Contract

Translate the user's natural-language objective into one `MISSION.json` before campaign
initialization. The user does not need to author JSON. Preserve the original wording in
`objective`; encode only decisions that affect routing or claim acceptance.

```json
{
  "schema_version": 1,
  "objective": "Discover a publishable contribution across audio AI.",
  "exploration_mode": "broad",
  "domain_packs": ["audio"],
  "acceptable_contributions": [
    "new_mechanism",
    "new_combination",
    "new_architecture",
    "new_objective",
    "new_representation",
    "new_system"
  ],
  "diagnostic_as_final": false,
  "fallback_policy": "return_to_discovery",
  "human_evaluation_policy": "pause_when_required",
  "target_output": "paper",
  "adapter_selection": {
    "task": ["agent_select"],
    "model": ["agent_select"],
    "lever": ["agent_select"],
    "evidence": ["agent_select"],
    "constraint": []
  }
}
```

`exploration_mode` controls the minimum candidate portfolio:

| Mode | Minimum candidates | Use |
|---|---:|---|
| `broad` | 3 | The agent must discover both the problem and mechanism. |
| `directed` | 2 | The user names a task, component, or contribution family. |
| `fixed_problem` | 1 | The scientific problem is already fixed; only solutions compete. |

`human_evaluation_policy` is one of:

- `pause_when_required`: prepare the study and wait for real external judgments.
- `existing_evidence_only`: use a versioned human-labelled benchmark; do not create ratings.
- `forbid`: reject a route whose minimum evidence requires human judgment.

The default fallback is `return_to_discovery`. Use `allow_diagnostic` only when the user
explicitly accepts a diagnostic, reproduction, or new-application paper as a final outcome.
Every adapter ID written explicitly in `adapter_selection` is mandatory in the resolved route;
`agent_select` delegates only that adapter kind. The agent may add dependency or supporting
adapters, but it cannot replace a user-fixed task, model, lever, evidence, or constraint.

## Adapter Contract

Each JSON pack contains a stable `pack_id`, a direct reference, optional default constraints,
and a list of adapters. Every adapter declares:

| Field | Meaning |
|---|---|
| `id` | Globally unique `<pack>.<name>` identifier. |
| `kind` | `task`, `model`, `lever`, `evidence`, or `constraint`. |
| `description` | Narrow scientific scope, not marketing text. |
| `reference` | Direct `references/...` path, optionally with a heading anchor. |
| `required_evidence` | Evidence adapters that must be selected with this adapter. |
| `discovery_questions` | Questions that produce observations rather than branded ideas. |
| `novelty_traps` | Common false-novelty or invalid-evidence patterns. |
| `human_evaluation` | `never`, `conditional`, or `required`. |

Put generic levers and evidence in `core.json`. Domain packs should define domain task/model
families, specialized evidence, and unavoidable constraints. Reuse core adapters instead of
copying generic RL, architecture, systems, safety, or theory instructions into every domain.

## Route Resolution

During `territory` and `discovery`, use the mission and primary-source landscape to select an
explicit route. A valid route contains at least one adapter of each required kind: `task`,
`model`, `lever`, and `evidence`. It also includes every required evidence dependency and each
pack's default constraints.

Inspect the registry without loading every reference:

```bash
python3 scripts/adapter_registry.py validate
python3 scripts/adapter_registry.py list --pack audio
python3 scripts/adapter_registry.py show audio.music-generation
```

Record the route before entering `portfolio`:

```bash
python3 scripts/campaign.py route-set "$ROOT" \
  --adapters audio.music-generation,audio.codec-autoregressive,core.architecture,core.controlled-evidence,audio.perceptual-generation-evaluation,audio.music-structure-evaluation,audio.safety-memorization-evaluation,core.human-evaluation,core.safety-evidence \
  --reason "long-form structure is the highest-value reproducible opportunity"
```

The command validates dependency closure, mission pack scope, required kinds, human-evidence
policy, and the registry fingerprint. It records a canonical route hash. Candidate and novelty
artifacts bind to that hash, so a later route change cannot reuse stale evidence.

Read only the route's listed references. Do not load every domain pack into the author context.

## Claim Compatibility

The mission controls what can finish, not what the agent happens to find. A cold novelty review
must return a claim class present in `acceptable_contributions`. Application, reproduction, or
diagnostic findings can remain discovery evidence, but they cannot silently replace a requested
method, architecture, objective, representation, system, data, evaluation, empirical, or theory
contribution.

On an incompatible or rejected review:

1. Preserve the observation and eliminated mechanism in the compact discovery artifacts.
2. Return to `discovery` or `portfolio` according to the recorded fallback policy.
3. Generate or promote a different candidate.
4. Request human input only when the mission says `wait_human` or no viable branch remains.

## Human Evidence

Never create ratings, listeners, consent, demographic details, or preference results. When a
selected route requires human evidence:

- generate candidate samples and evaluation materials in `$PBS_JOBFS`
- publish one packed, blinded sample bundle plus one manifest
- predeclare the protocol, comparisons, exclusions, and statistics
- hand off to `waiting_human`
- register an accepted `human_evaluation` artifact only from real returned evidence

If the mission permits only existing evidence, record the benchmark version, provenance,
population, task match, and limitations. Objective surrogates may guide discovery but cannot
support a perceptual claim beyond their validated correlation.

Import completed evidence as accepted `human_evaluation` JSON with this structural shape:

```json
{
  "schema_version": 2,
  "status": "complete",
  "mission_sha256": "<MISSION.json canonical hash>",
  "route_sha256": "<resolved route hash>",
  "candidate_id": "<active candidate id>",
  "novelty_audit_sha256": "<NOVELTY_AUDIT.json file hash>",
  "evidence_sha256": "<packed returned evidence hash>",
  "protocol": "new_study",
  "source": "User-supplied study identifier and immutable result path",
  "population": "Documented eligible listener population",
  "blinded": true,
  "rater_count": 30,
  "judgment_count": 600,
  "metrics": {"preference_rate": 0.61, "confidence_interval": [0.56, 0.66]},
  "limitations": ["Population and listening-condition limits"]
}
```

Use `protocol: existing_benchmark` for versioned external judgments. The campaign accepts this
artifact only while it is in `waiting_human`, and the hashes must bind it to the current mission,
route, active candidate, novelty audit, and packed returned evidence. Then hand off to
`needs_agent`. Do not mark agent-generated predictions or evaluator-model scores as human evidence.

## Extending the Registry

To add a domain without changing the core controller:

1. Copy `adapters/pack-template.json.example` to `adapters/<pack-id>.json`, then replace every
   example value using schema version 1 and a unique lowercase pack prefix.
2. Add one `references/<pack-id>-research.md` covering domain-specific discovery, evidence,
   validity, safety, and storage issues.
3. Define task and model adapters. Reuse core levers; add specialized evidence only when core
   evidence is insufficient.
4. Keep default adapters limited to unavoidable constraints. Defaults must not force a research
   conclusion or expensive evaluation.
5. Run `python3 scripts/adapter_registry.py validate`.
6. Add registry tests for a valid route, missing evidence, a human-evidence route, and an unknown
   adapter.
7. Forward-test one broad, one directed, one false-novelty, and one evidence-invalid request.

The registry rejects duplicate IDs, missing references, unknown dependencies, non-evidence
dependencies, adapters outside the mission packs, and incomplete routes. The campaign also pins
the skill Git tree and registry hash, so changing a pack pauses rather than silently altering a
running study.
