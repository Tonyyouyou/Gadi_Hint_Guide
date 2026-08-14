# Research Workflow

## Contents

1. Mission and territory
2. Evidence-led discovery
3. Candidate portfolio
4. Novelty review and fallback
5. Research contract and plan
6. Implementation and sanity
7. Evidence campaign
8. Review and synthesis
9. Paper handoff

## Mission and Territory

Treat `MISSION.json` as immutable user intent. It defines acceptable final contributions,
exploration breadth, fallback behavior, domain packs, human-evaluation policy, and target output.
Do not reinterpret a requested method or system paper as permission to finish a diagnostic paper.

In `territory`, convert the mission into `RESEARCH_BRIEF.md` with scientific scope, non-goals,
open assets, constraints, publication audience, compute envelope, and falsifiable success criteria.
Build one deduplicated `LITERATURE.md` from current primary papers and official code/data/model
sources. Record citation, mechanism, evidence type, task/model family, dataset, metric, limitation,
asset availability, and relevance. Do not download a PDF collection by default.

Map the territory as cells rather than a list of method names:

```text
task family x model family x research lever x evidence protocol x constraint
```

Use `adapter_registry.py list` to inspect candidates. For a broad mission, compare the most
promising cells and deeply scout at most three. Do not select an active idea in this phase.

## Evidence-Led Discovery

Enter `discovery` after recording the brief and literature. Resolve an explicit adapter route
with `campaign.py route-set` before entering `portfolio`. Load only that route's references.

Create `DISCOVERY_REPORT.md` as one compact observation and opportunity ledger. Seek:

- expected-versus-observed contradictions
- stable failures under predeclared slices or perturbations
- information produced by one component but discarded at an interface
- objective, reward, representation, or evaluation mismatch
- repeated computation or measured system bottlenecks
- constraint-induced problems such as streaming, privacy, low-resource, or hardware behavior
- formal assumption mismatch or a counterexample to accepted intuition

Use current literature, code inspection, existing results, and cheap registered `discovery` or
`profile` experiments. A discovery probe is bounded hypothesis generation, not final evidence.
Predeclare the question, alternative explanations, decision rule, maximum SU/jobs/files, and
what observation would make the opportunity disappear. Do not mine many metrics and write a
story around the best one.

Preserve failures and null observations. They stop future turns from rediscovering the same
dead end and may redirect the route. If the route changes, use `route-set`; the controller
invalidates route-bound downstream artifacts.

## Candidate Portfolio

Write and register provisional `CANDIDATE_PORTFOLIO.json` schema version 1. Bind it to
`mission_sha256` and `route_sha256`. It contains exactly one `active` candidate and the required
number of viable candidates:

| Exploration mode | Minimum viable candidates |
|---|---:|
| `broad` | 3 |
| `directed` | 2 |
| `fixed_problem` | 1 |

Each candidate must record:

- observed phenomenon or precisely defined formal tension
- causal hypothesis
- functional mechanism without branding
- predicted experimental or formal signature
- decisive falsifier
- cheapest distinguishing test
- closest prior-work delta
- estimated SU, job, and persistent-entry cost
- status: `active`, `backup`, or `eliminated`

Use this exact structural shape:

```json
{
  "schema_version": 1,
  "mission_sha256": "from-campaign.json",
  "route_sha256": "from-campaign.json",
  "created_at": "2026-08-13T00:00:00Z",
  "active_candidate_id": "candidate-a",
  "candidates": [
    {
      "id": "candidate-a",
      "status": "active",
      "observation": "Reproducible measured or formal phenomenon.",
      "causal_hypothesis": "Proposed cause.",
      "mechanism": "Functional intervention without branding.",
      "predicted_signature": "Observable that follows from the hypothesis.",
      "falsifier": "Outcome that rejects it.",
      "cheap_test": "Lowest-cost distinguishing test.",
      "nearest_work_delta": "What remains after closest prior work.",
      "estimated_cost": {"su": 10, "jobs": 1, "persistent_entries": 4}
    }
  ]
}
```

Add enough backup objects to meet the mode minimum; at most eight candidates are permitted.

Generate mechanisms through different causal interventions, not name variations. Search across
interfaces when useful: data-representation, encoder-connector, objective-reward, model-runtime,
generator-evaluator, and safety-deployment. Rank candidates by importance, target-forced mechanism,
novelty evidence, falsifiability, information per SU, available assets, and evidence validity.

Do not promote a candidate merely because it is easy to implement. Preserve eliminated candidates
and reasons in the portfolio or discovery report. A positive cheap test only promotes a candidate
to formal novelty audit.

## Novelty Review and Fallback

Read `novelty-audit.md`. Write `IDEA_REPORT.md` for the active portfolio candidate, then create
schema-version-2 `NOVELTY_AUDIT.json` bound to mission, route, portfolio, and idea hashes. Enter
`novelty_review` and hand off to `needs_novelty_review`.

The controller starts a fresh non-resumed reviewer. It independently searches the mechanism,
classifies the actual contribution, and writes `NOVELTY_REVIEW.json`. The author never writes the
verdict artifact. It must distinguish three outcomes:

- `clear_to_plan` when a mission-compatible primary delta survives and no exact prior exists
- `exact_prior_reject` only with a checked functionally equivalent primary source
- `conditional_probe` when no exact prior exists but a cheap empirical comparison can distinguish
  a non-obvious interaction from a faithful naive A+B composition

For `conditional_probe`, stay in `novelty_review`. Run only the machine-capped `novelty_probe`
stage, answer the declared question against the naive combination, and bind completed success
markers into `NOVELTY_REBUTTAL.json`. Hand off to `needs_novelty_arbitration`; a fresh third thread
distinct from both author and reviewer writes `NOVELTY_ARBITRATION.json`. It either clears the
narrow primary claim or rejects it with functionally equivalent exact-prior evidence. No ordinary
pilot/main/ablation or full implementation starts while this dispute remains open.

Planning is allowed only when the reviewed or arbitrated claim class is in the mission's
`acceptable_contributions`. If the reviewer/arbiter hard-rejects, or a legacy verdict requests
changes or reclassifies the active candidate outside the mission, the controller returns to:

- `portfolio` when a backup candidate exists
- `discovery` when no backup remains

Retain the rejected review as evidence. Promote or generate another candidate and repeat the
audit. Only a mission with `fallback_policy: allow_diagnostic` may finish as a new application,
reproduction, or diagnostic contribution.

## Research Contract and Plan

After a compatible novelty resolution, freeze `RESEARCH_CONTRACT.md`:

- mission, adapter route, active candidate, and permitted claim class
- primary and secondary claims plus explicit non-claims
- evaluation type: real ground truth, synthetic proxy, self-supervised proxy, simulation, formal,
  system measurement, existing human benchmark, or new human study
- dataset/model/code versions, splits, content-level contamination controls, and licenses
- primary metric and direction, secondary diagnostics, and adapter-specific evidence
- official or independently reproduced baselines
- seeds, sample sizes, statistical comparisons, uncertainty, ablations, and stress tests
- claim ceiling for every evidence type
- human-evaluation protocol or `waiting_human` trigger when required
- stop, pivot, no-progress, and resource-exhaustion criteria

Write `EXPERIMENT_PLAN.md` with ordered environment/data witnesses, sanity, baselines, primary
evidence, replication, ablation, robustness, human handoff where needed, and audit. Every row must
include experiment ID, question, command/config, resources, dependencies, success marker, expected
persistent entries, and decision rule. Maintain one compact `EXPERIMENT_LEDGER.jsonl` or table.

## Implementation and Sanity

Reuse a credible base repository where possible. Pin its exact commit. Expose all scientific
hyperparameters and output paths. Seed stochastic components and save resolved configuration with
compact machine-readable metrics.

Before substantial GPU use, give a fresh reviewer the contract, plan, code paths/diff, configuration,
evaluator, and selected adapter requirements. Fix blocking implementation or evaluation defects and
rerun the smallest deterministic test.

Evaluation compares predictions with real ground truth or an explicitly labelled proxy. Keep
holdout data inaccessible to selection code where practical. For generated media, fixed prompts,
references, seeds, and blinded sample identifiers are part of the protocol.

The sanity witness proves imports, device kernels, real input/evaluation paths, finite computation,
metric and success-marker correctness, memory/walltime/jobfs/file estimates, and restart behavior
when needed. Never rerun an unchanged deterministic failure.

## Evidence Campaign

Run matched baselines before claimed improvements. Hold data splits, evaluator, budgets, and
reporting constant. Then run main evidence, multiple seeds or replications, causal ablations,
negative controls, robustness, and adapter-specific tests.

For adaptive work, each turn answers one question and submits the minimum experiment that
distinguishes alternatives. Release compute before agent reasoning. Use checkpoints sparingly and
aggregate per-rank, per-example, per-sample, and per-seed output before durable publication.

If a route requires human evaluation, the agent may generate a packed blinded study bundle and
predeclared protocol, but must hand off to `waiting_human`. It must not create ratings, raters,
consent, population descriptions, or preference results. Register `human_evaluation` with accepted
assurance only from real completed evidence matching the schema in `adapter-system.md`. Bind the
record to the current mission, route, active candidate, novelty audit, and packed evidence hash;
after acceptance, hand off to `needs_agent` so autonomous work can resume.

Stop or pivot when the primary claim is falsified, gains disappear under matched controls,
evaluation is invalid or contaminated, a required evidence source is unavailable, information per
remaining SU is too low, repeated implementation failures expose a wrong assumption, or any
approved budget/inode boundary approaches.

Changing the mission is not a pivot; create a new campaign. Changing the route or portfolio
invalidates downstream claim artifacts. Novelty searches older than 30 days must be refreshed.

## Review and Synthesis

Run a cold integrity review against exact source commits, configs, raw metrics, ledgers, media
manifests, and human-evidence provenance. Check fake ground truth, leakage, cherry-picking,
normalization, unsupported perceptual claims, phantom results, insufficient scope, and tracker/file
mismatch.

Build a claim-evidence graph. Every number in `RESULTS.md` traces to a machine-readable source and
reports uncertainty, sample/seed counts, baseline delta, failed conditions, and applicable adapter
limitations. A same-family semantic review remains provisional; only a different-family reviewer
or deterministic verifier can record accepted assurance for what it actually verifies.

Write `NARRATIVE_REPORT.md` with mission, discovered problem, candidate pivots, novelty evidence,
method, protocol, results, limitations, negative results, claim-evidence table, and figure/table
inventory. Ensure the final claim class remains permitted by the mission.

## Paper Handoff

Proceed to English LaTeX only after synthesis. For an unspecified venue, write a generic preprint
with separable style configuration. A venue adaptation must not alter scientific results.

Read `paper-completion.md`. Generate figures from canonical data, compile from a clean build tree,
and retain only final sources, bibliography, figures, and PDF. Register every canonical artifact
with `campaign.py artifact`; conversation memory is not evidence.
