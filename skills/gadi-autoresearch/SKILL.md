---
name: gadi-autoresearch
description: Run a bounded, resumable, inode-safe autonomous research campaign on NCI Gadi from a broad idea through literature review, idea selection, implementation, interactive or batch experiments, adversarial review, synthesis, LaTeX paper writing, compilation, and evidence audits. Use for overnight or multi-hour ML/scientific research; ARIS-style idea-to-paper workflows; persistent-session orchestration; PBS experiment campaigns; or any request to freely explore a research direction using /g/data/wa66/Xiangyu.
---

# Gadi Autoresearch

Turn a broad research direction into an evidence-bounded paper without treating an agent session, tmux pane, GPU allocation, or quarterly project balance as permanent.

Use `$run-on-gadi` as the infrastructure authority. This skill owns the research state machine and campaign envelope; `run-on-gadi` owns Gadi paths, queues, `.sqsh` environments, data packing, PBS validation, and troubleshooting.

## Non-Negotiable Invariants

1. Reserve `/g/data/wa66/Xiangyu/.codex` for Codex configuration, skills, and skill source repositories. Never write research code, literature, datasets, environments, caches, traces, checkpoints, logs, metrics, figures, or papers there.
2. Keep research source in a small Git workspace under `/g/data/wa66/Xiangyu` and outside `.codex`; never use HOME for it. Put durable campaign artifacts under a user-approved existing `/g/data/wa66/Xiangyu/Result*` tree.
3. Store frozen environments only as `.sqsh` files in `/g/data/wa66/Xiangyu/enviroment_cache`; keep the existing spelling. Build or expand them only in `$PBS_JOBFS`.
4. Store datasets only under `/g/data/wa66/Xiangyu/Data` as archives or a controlled number of coarse shards. Download, extract, preprocess, and cache only in `$PBS_JOBFS`.
5. Treat file count as a budget. The campaign envelope covers its result tree, files added to the Git workspace, newly published environment/data objects, planned output, and controller reserve. Do not use ARIS's per-step `.aris/traces`, one-file-per-sample outputs, expanded package trees, Hugging Face caches, or one PBS job per tiny sweep cell.
6. Never compute on a login node or persistent-session host. Those hosts may edit, search, reason, compile small files, submit PBS, and monitor at most once per ten minutes.
7. Never invoke raw `qsub` or `qdel` in an autonomous campaign. Use this skill's campaign CLI. A campaign approval is bounded permission, not unlimited cluster access.
8. Never use `--dangerously-bypass-approvals-and-sandbox`, an infinite `--full-auto` loop, or a scheduler as a scientific reviewer.
9. Never treat a coined name, cross-domain transfer, component bundle, or positive pilot as method novelty. Planning and method experiments require a hash-bound audit plus a controller-attested review from a fresh thread. Same-family review remains scientifically `provisional`.

## Locate the Tools

```bash
SKILL=/g/data/wa66/Xiangyu/.codex/skills/gadi-autoresearch
CAMPAIGN="$SKILL/scripts/campaign.py"
CONTROLLER="$SKILL/scripts/controller.py"
STARTER="$SKILL/scripts/start_controller.sh"
GADI=/g/data/wa66/Xiangyu/.codex/skills/run-on-gadi
PYTHON=/home/561/xz4320/miniconda3/bin/python3
```

Use this existing modern Python only for the lightweight control CLI; do not install packages into it. Scientific dependencies remain in immutable `.sqsh` images.

Before initializing, read [references/campaign-contract.md](references/campaign-contract.md). Before each research phase, read the matching section of [references/research-workflow.md](references/research-workflow.md). Before proposing, selecting, or revising an idea, read [references/novelty-audit.md](references/novelty-audit.md).

## Start or Resume

If `campaign.json` already exists, resume it instead of creating a second campaign:

```bash
"$PYTHON" "$CAMPAIGN" status /absolute/campaign-root
```

For a new broad idea:

1. Select or create a small Git workspace below `/g/data/wa66/Xiangyu` and outside `.codex`; make an initial commit. The workspace path must be the repository root, remain separate from the campaign directory, and be clean when an experiment is registered.
2. Select an existing matching `Result*` tree; do not invent a result family when the project already has one.
3. Run `$run-on-gadi` read-only preflight and inspect all four dynamic project reports.
4. Map the research to scientifically eligible projects. The largest remaining allocation is not sufficient justification.
5. Initialize a **draft** campaign with a proposed SU, job, concurrency, GPU, deadline, Codex-turn, and persistent-file envelope.
6. Show the complete envelope and estimated pilot cost to the user. Do not approve it on the user's behalf.
7. After explicit approval, record the approver and only the capabilities actually granted.

Example draft:

```bash
"$PYTHON" "$CAMPAIGN" init /g/data/wa66/Xiangyu/Result_EXISTING/PROJECT/campaign-id \
  --campaign-id campaign-id \
  --idea "BROAD IDEA" \
  --workspace /g/data/wa66/Xiangyu/Result_EXISTING/PROJECT/source-repo \
  --projects wa66,ey69 \
  --max-su 500 --max-jobs 12 --max-concurrent 1 --max-gpus 1 \
  --max-files 512 --max-agent-turns 40 \
  --deadline 2026-09-01T00:00:00Z
```

Approval for an unattended campaign is explicit and recorded:

```bash
"$PYTHON" "$CAMPAIGN" approve /absolute/campaign-root \
  --by USER \
  --allow-auto-submit --allow-interactive --allow-auto-agent
```

Omit any capability the user did not grant. Add `--allow-storage-publish` only when the envelope explicitly permits new `.sqsh` or packed-data publication. `allow_auto_cancel` is off by default and should normally remain off.

## Select the Work Mode

Classify every action before running it:

- **Static work**: literature search, code editing, test design, linting, compact log analysis, result parsing, and paper writing. Keep login/persistent-session processes below NCI's shared-host limits.
- **Interactive exploration**: expected runtime at most four hours **and** the agent needs frequent edit-run-inspect cycles. Hold `qsub -I` in a named tmux session on an NCI persistent session; use one GPU and the smallest useful sample first.
- **Batch experiment**: command is reproducible and unattended, even if shorter than four hours; always use batch for longer work, full data, multi-GPU, or fixed training.
- **Adaptive long campaign**: submit bounded batch workers, persist results, release compute, then wake Codex to decide the next experiment. Never hold a GPU while waiting for model reasoning.

For a deterministic three-hour training run, prefer batch. For a ten-hour adaptive investigation, prefer several checkpointed jobs rather than one ten-hour agent-held allocation.

## Execute the Research Lifecycle

Use this ordered lifecycle; a pivot may return to an earlier phase only with a recorded reason:

1. `literature`: turn the broad direction into a compact `RESEARCH_BRIEF.md`; search current primary literature; build a deduplicated evidence table.
2. `ideas`: generate several falsifiable mechanisms; remove branded names, decompose primitives, search target and adjacent fields, and preserve eliminated ideas in one report.
3. `novelty_review`: record the bound `NOVELTY_AUDIT.json`, then hand off to `needs_novelty_review`. Only the controller's fresh reviewer may write `NOVELTY_REVIEW.json`.
4. `planning`: proceed only after the cold-review gate classifies the work as a method or diagnostic track; freeze datasets/splits/metrics/baselines/seeds and claim ceilings.
5. `implementation`: reuse a credible base implementation where possible; make every parameter and output path explicit; write compact machine-readable metrics.
6. `sanity`: run the smallest witness first. Verify real ground truth, imports, GPU kernels, output marker, memory, jobfs, and file count.
7. `experiments`: run baseline before main method, then replication seeds, ablations, and stress tests. Change one scientific question at a time and log negative results.
8. `review`: give experiment-integrity artifact paths to a fresh reviewer. Same-family Codex review is `provisional`; only a different-family reviewer or deterministic verifier may record `accepted`.
9. `synthesis`: audit experiment integrity, map every claim to raw results, report uncertainty and limitations, and write `NARRATIVE_REPORT.md`.
10. `paper`: plan figures/tables, write English LaTeX, compile from a clean build directory, and retain only final sources, figures, bibliography, and PDF.
11. `audit`: refresh stale novelty searches, verify numerical claims, citations, artifact freshness, and paper compilation; write a final report that states the actual assurance class.

The detailed artifact and decision contract is in [references/research-workflow.md](references/research-workflow.md). The adaptation from the local ARIS checkout is documented in [references/aris-adaptation.md](references/aris-adaptation.md).

## Register and Run Experiments

Every experiment must declare:

- stage and mode
- eligible charging project
- queue, walltime, CPU, GPU, memory, and jobfs
- immutable `.sqsh` image
- clean Git source commit; batch workers expand this exact commit in jobfs
- argument-vector command with absolute source paths
- expected maximum persistent entries
- a deterministic success file such as `metrics.json`
- completed dependencies

`sanity` and `profile` may be registered before novelty clearance when compatible frozen inputs already exist. Environment/data publication scripts may be previewed but not submitted before a resolved method or diagnostic classification. `baseline`, `audit`, and `paper` require that classification. `pilot`, `main`, and `ablation` require `plausibly_novel` plus `new_mechanism` or `new_combination`; both registration and submission recheck the gate.

Use `{RESULT_DIR}`, `{PBS_JOBFS}`, `{WORKSPACE}`, and `{DATA_ROOT}` placeholders in command arguments. The worker substitutes them without shell evaluation. `{RESULT_DIR}` is attempt-local jobfs staging during execution, not a direct gdata write path; compact output is validated and atomically published only after success.

Preview is always the default:

```bash
"$PYTHON" "$CAMPAIGN" submit /absolute/campaign-root --id sanity-001
```

Use `--execute` only when the recorded envelope grants automatic submission. The CLI reruns live project, SU, inode, and reserved-entry checks, validates dependencies and deterministic sanity evidence, renders a temporary PBS script, runs the `run-on-gadi` linter, submits it, stores the exact script and validated job ID in `campaign.json`, then deletes the temporary script. The PBS worker stages all output in `$PBS_JOBFS`, rejects excessive or unsafe trees, and only then publishes to the campaign.

Read [references/campaign-contract.md](references/campaign-contract.md) for environment/data staging, interactive commands, experiment registration, refresh, handoff, pause, and completion examples.

## Persistent Control

An NCI persistent session is the control plane, never the compute plane. Put one named tmux controller there. It may hold an interactive `qsub -I` pane or run:

```bash
bash "$STARTER" --root /absolute/campaign-root --session aris-CAMPAIGN
bash "$STARTER" --root /absolute/campaign-root --session aris-CAMPAIGN --start
```

Run the second command only after connecting to the persistent host. The helper uses a clean no-profile tmux command so stale HOME startup references cannot leak into the controller. For an attended three-to-four-hour exploration, a foreground Codex `/goal` may drive the same campaign directly and use the interactive pane; still persist every experiment and handoff through `campaign.py`. Use the event-driven controller for queued or overnight work so Codex is invoked only when a decision is needed.

The first command previews. The second is permitted only after the campaign grants `allow_auto_agent` and a live pilot verifies Codex authentication/network access in the persistent session. The controller:

- enforces a single writer
- polls PBS no more often than 600 seconds
- invokes or resumes one `codex exec` turn only when action is needed
- launches `needs_novelty_review` in a new non-resumed adversarial thread and attests that its thread ID differs from the author thread
- pauses if Codex exits without an explicit handoff
- stores one bounded rotating log under the campaign root
- resumes from `campaign.json` after controller or persistent-session failure

Read [references/persistent-control.md](references/persistent-control.md) before starting it. Do not parse `persistent-sessions list` output in automation.

Each campaign pins the skill repository commit and skill-tree hash. A changed installed skill pauses the campaign instead of silently changing its rules. After reviewing an update and confirming no jobs are active, pause the campaign and run `campaign.py skill-adopt --by USER --reason REASON`, then resume explicitly.

## Stop, Pause, and Handoff

Stop generating new work when any approved limit is reached, inode headroom becomes unsafe, allocation changes invalidate the plan, the deadline passes, repeated failures question the method/environment, evaluation integrity is uncertain, or a `STOP`/pause request is recorded.

Before every Codex turn exits, write exactly one control handoff:

```bash
"$PYTHON" "$CAMPAIGN" handoff /absolute/campaign-root \
  --state waiting_pbs \
  --reason "jobs 123 and 124 must finish before analysis"
```

Use `needs_novelty_review` only after the author records the audit and enters that phase. Use `waiting_human` for a real scientific/budget decision, `waiting_time` with `--wake-at`, `paused` for a safety problem, and `complete` only after the completion audit passes.

## Completion Standard

The goal is not complete because training ended or a PDF exists. Before `handoff --state complete`, inspect every required artifact and read [references/paper-completion.md](references/paper-completion.md). The CLI requires the research brief, idea report, novelty audit/review, research contract, experiment plan/ledger, results, experiment and claim audits, narrative report, paper source/PDF, citation audit, and final report. Novelty artifacts must still be hash-bound and no more than 30 days old.

If only same-family semantic review was available, complete the campaign with `overall_assurance: provisional` and never call the paper submission-ready. Negative or inconclusive research may still produce an honest paper, but the title, abstract, claims, and limitations must match the evidence.
