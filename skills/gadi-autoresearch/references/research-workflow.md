# Research Workflow

## Contents

1. Intake and literature
2. Idea discovery
3. Research contract and plan
4. Implementation and sanity
5. Evidence campaign
6. Review and synthesis
7. Paper handoff

## Intake and Literature

Convert the user's broad direction into `RESEARCH_BRIEF.md` with problem, scientific context, constraints, available code/data, non-goals, target audience, compute envelope, and falsifiable success criteria. If the target venue is unknown, use `generic-preprint`; do not block research merely to guess a venue.

Search recent primary literature and official datasets/code. Record one deduplicated table in `LITERATURE.md`: citation key, claim, evidence type, dataset, metric, limitations, code/data availability, and relevance. Do not download a PDF collection by default. Keep selected papers as metadata/notes; if PDFs are essential, acquire and pack them through inode-safe storage.

Distinguish direct source evidence from inference. Never invent citations, identifiers, baseline numbers, or dataset licenses.

## Idea Discovery

Generate multiple candidates that differ in mechanism, not wording. For each candidate record:

- falsifiable hypothesis and predicted observable
- closest prior work and claimed novelty delta
- minimal pilot and expected GPU/SU/file cost
- primary failure mode and disconfirming outcome
- reuse opportunities in credible codebases
- maximum defensible claim if the pilot succeeds

Eliminate ideas that are already published, cannot be evaluated honestly, exceed the envelope, depend on unavailable data, or only promise metric fishing. Preserve eliminated ideas in a single section so resumed agents do not repeat them.

Rank by novelty evidence, feasibility, empirical signal, and information gained per SU. A positive tiny pilot is not publication evidence; it only decides which hypothesis deserves a full plan.

Output `IDEA_REPORT.md` and record it as `idea_report`. The active idea must have a backup or a recorded reason why no backup is viable.

## Research Contract and Plan

Before the main experiment, freeze `RESEARCH_CONTRACT.md`:

- primary and secondary claims
- evaluation type: `real_gt`, `synthetic_proxy`, `self_supervised_proxy`, `simulation_only`, or `human_eval`
- dataset versions, train/validation/test split, contamination controls
- primary metric and direction, secondary diagnostics
- official or independently reproduced baselines
- random seeds and statistical comparison
- ablations and stress tests
- claim ceiling for every possible evidence type
- stop, pivot, and no-progress criteria

Write `EXPERIMENT_PLAN.md` with ordered stages: environment/data witness, sanity, baseline, main method, replication, ablation, robustness, and audit. Each row must include experiment ID, question, command/config, resources, dependencies, success marker, expected persistent entries, and decision rule.

Maintain one compact `EXPERIMENT_LEDGER.jsonl` or tabular equivalent. Do not make one tracker file per run.

## Implementation and Sanity

Inspect and reuse the base repository before adding abstractions. Pin the exact Git commit for every run. Expose all scientific hyperparameters through config/arguments. Seed all stochastic components and save machine-readable metrics alongside the resolved config.

Before spending GPU SU, give a fresh reviewer the research contract, experiment plan, exact code paths/diff, configuration, and evaluator. Blocking implementation/evaluation defects must be fixed and the smallest deterministic tests rerun. A same-family code review is useful but provisional; test exits and seeded kernel witnesses are deterministic evidence.

Evaluation must compare predictions with dataset ground truth or explicitly labeled proxies, never another model output disguised as truth. Keep test/holdout data inaccessible to selection code where practical.

The sanity run proves:

- image imports and seeded device kernel work
- real input and evaluation paths resolve read-only
- one train/eval step produces finite values
- metric computation and success marker are correct
- expected GPU memory, walltime, jobfs, and persistent entries are plausible
- restart/checkpoint logic works when required

Read primary logs before changing code. Never rerun unchanged after a deterministic failure. After repeated failure, distinguish code, environment, data, and hypothesis failures; do not keep patching the same layer blindly.

## Evidence Campaign

Run the baseline before the claimed method. Use identical data splits, evaluation code, budgets, and reporting. Then run main seeds, required ablations, robustness tests, and negative controls.

For adaptive exploration, each Codex turn should answer one question, submit the minimum experiment that distinguishes the alternatives, and hand off to PBS. Do not occupy a GPU while choosing the next hypothesis.

Use rolling checkpoints and keep only the best, latest resumable, and final audited checkpoint unless the research contract requires more. Aggregate per-rank, per-sample, and per-seed data before publishing to gdata.

Stop or pivot when:

- the primary claim is falsified
- improvements disappear under matched baselines or multiple seeds
- the metric/evaluator is invalid or contaminated
- information gained per remaining SU is too low
- repeated implementation failures expose an unavailable dependency
- the campaign approaches any approved budget or inode limit

Negative findings remain in the ledger and may support an honest diagnostic paper.

## Review and Synthesis

Run a cold experiment-integrity review against source paths, configs, raw metrics, and ledger. Check fake ground truth, leakage, selective reporting, score normalization, phantom results, insufficient scope, and mismatch between tracker and files.

Then build a claim-evidence table. Every number in `RESULTS.md` must trace to a machine-readable source. Report raw values, uncertainty, sample/seed counts, baseline delta, and failed conditions before interpretation.

A fresh same-family Codex reviewer is useful but `provisional`. Different-family review or a deterministic evaluator can be `accepted`. The executor never upgrades its own semantic verdict.

Write `NARRATIVE_REPORT.md` containing problem, novelty evidence, method, experiment protocol, quantitative results, limitations, negative results, claim-evidence table, and figure/table inventory.

## Paper Handoff

Proceed directly to paper writing after synthesis. For an unspecified venue, write a generic preprint and preserve separable style configuration. A later venue adaptation must not change scientific results.

Read `paper-completion.md` before creating the paper plan. Record every canonical artifact with `campaign.py artifact`; do not rely on conversation memory.
