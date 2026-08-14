---
name: gadi-autoresearch
description: Run bounded, resumable, inode-safe autonomous research on NCI Gadi from an open mission through evidence-led problem discovery, composable domain adapters, competing candidates, implementation, PBS experiments, adversarial review, synthesis, and LaTeX paper writing. Use for overnight or multi-hour ML/scientific research; audio research including ASR, AudioLLMs, TTS, speech interaction, sound or music understanding/generation, signal processing, RL, architecture, and inference systems; extensible non-audio research packs; persistent-session orchestration; or any request to freely explore a research direction using /g/data/wa66/Xiangyu.
---

# Gadi Autoresearch

Turn an open or directed research mission into an evidence-bounded paper without treating an agent session, tmux pane, GPU allocation, or quarterly project balance as permanent. Discover a problem before forcing a branded solution, and preserve the user's requested contribution class across pivots.

Use `$run-on-gadi` as the infrastructure authority. This skill owns the research state machine and campaign envelope; `run-on-gadi` owns Gadi paths, queues, `.sqsh` environments, data packing, PBS validation, and troubleshooting.

## Non-Negotiable Invariants

1. Reserve `/g/data/wa66/Xiangyu/.codex` for Codex configuration, skills, and skill source repositories. Never write research code, literature, datasets, environments, caches, traces, checkpoints, logs, metrics, figures, or papers there.
2. Keep research source in a small Git workspace under `/g/data/wa66/Xiangyu` and outside `.codex`; never use HOME for it. Put durable campaign artifacts under a user-approved existing `/g/data/wa66/Xiangyu/Result*` tree.
3. Store frozen environments only as `.sqsh` files in `/g/data/wa66/Xiangyu/enviroment_cache`; keep the existing spelling. Build or expand them only in `$PBS_JOBFS`.
4. Store datasets only under `/g/data/wa66/Xiangyu/Data` as archives or a controlled number of coarse shards. A user-approved public pretrained model may persist only as one immutable, provenance-recorded `.tar.zst` directly under `/g/data/wa66/Xiangyu/Data/models`; never persist an expanded model repository or Hugging Face cache. Download, expand, preprocess, and cache all input assets only in `$PBS_JOBFS`.
5. Treat file count as a budget. The campaign envelope covers its result tree, files added to the Git workspace, newly published environment/data objects, planned output, and controller reserve. Do not use ARIS's per-step `.aris/traces`, one-file-per-sample outputs, expanded package trees, Hugging Face caches, or one PBS job per tiny sweep cell.
6. Never compute on a login node or persistent-session host. Those hosts may edit, search, reason, compile small files, submit PBS, and monitor at most once per ten minutes.
7. Never invoke raw `qsub` or `qdel` in an autonomous campaign. Use this skill's campaign CLI. A campaign approval is bounded permission, not unlimited cluster access.
8. Never use `--dangerously-bypass-approvals-and-sandbox`, an infinite `--full-auto` loop, or a scheduler as a scientific reviewer.
9. Never treat a coined name, cross-domain transfer, component bundle, or positive pilot as method novelty. A hard novelty rejection requires a checked functionally equivalent prior; individually known primitives or a hypothetical A+B composition are insufficient. Empirical uncertainty goes through a bounded `novelty_probe`, author rebuttal, and fresh third-thread arbitration. Planning and method experiments still require final hash-bound clearance. Same-family review remains scientifically `provisional`.
10. Never silently downgrade the mission. A diagnostic, reproduction, or new application may inform discovery, but it can become the final paper only when `MISSION.json` explicitly permits that contribution.
11. Never invent human judgments. When perceptual or preference evidence is required, publish one packed blinded study bundle, hand off to `waiting_human`, and continue only from real recorded evidence.

## Locate the Tools

```bash
SKILL=/g/data/wa66/Xiangyu/.codex/skills/gadi-autoresearch
CAMPAIGN="$SKILL/scripts/campaign.py"
CONTROLLER="$SKILL/scripts/controller.py"
SUPERVISOR="$SKILL/scripts/supervisor.py"
STARTER="$SKILL/scripts/start_controller.sh"
ADAPTERS="$SKILL/scripts/adapter_registry.py"
GADI=/g/data/wa66/Xiangyu/.codex/skills/run-on-gadi
PYTHON=/home/561/xz4320/miniconda3/bin/python3
```

Use this existing modern Python only for the lightweight control CLI; do not install packages into it. Scientific dependencies remain in immutable `.sqsh` images.

Before initializing, read [references/campaign-contract.md](references/campaign-contract.md) and [references/adapter-system.md](references/adapter-system.md). Before each research phase, read the matching section of [references/research-workflow.md](references/research-workflow.md). Before proposing, selecting, or revising a candidate, read [references/novelty-audit.md](references/novelty-audit.md). For audio missions, load only the selected sections of [references/audio-research.md](references/audio-research.md).

## Freeze the Mission and Route

Convert the user's natural language into `MISSION.json`; the user need not provide JSON. Freeze:

- original objective and broad/directed/fixed-problem exploration mode
- allowed domain packs and final contribution classes
- whether diagnostic/application/reproduction work may be final
- fallback behavior after novelty rejection
- human-evaluation policy and target output
- any user-fixed task, model, research lever, evidence, or constraint adapters

Use `--mission-file` for a reviewed contract. A concise open Audio example is:

```json
{
  "schema_version": 1,
  "objective": "Discover a publishable contribution across audio AI.",
  "exploration_mode": "broad",
  "domain_packs": ["audio"],
  "acceptable_contributions": ["new_mechanism", "new_architecture", "new_objective", "new_representation", "new_system"],
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

Validate available packs with `"$PYTHON" "$ADAPTERS" validate`. During discovery, select a dependency-complete task + model + lever + evidence route with `campaign.py route-set`; pack defaults add unavoidable constraints. The campaign binds mission, registry, route, portfolio, idea, and novelty artifacts by hash.

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
  --mission-file /absolute/path/MISSION.json \
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

Omit any capability the user did not grant. Add `--allow-storage-publish` only when the envelope explicitly permits new `.sqsh` or packed-data publication. Add `--allow-model-publish` only after the user separately approves an immutable packed public model; it never permits expanded snapshots or caches. `allow_auto_cancel` is off by default and should normally remain off.

## Select the Work Mode

Classify every action before running it:

- **Static work**: literature search, code editing, test design, linting, compact log analysis, result parsing, and paper writing. Keep login/persistent-session processes below NCI's shared-host limits.
- **Interactive exploration**: expected runtime at most four hours **and** the agent needs frequent edit-run-inspect cycles. Hold `qsub -I` in a named tmux session on an NCI persistent session; use one GPU and the smallest useful sample first.
- **Batch experiment**: command is reproducible and unattended, even if shorter than four hours; always use batch for longer work, full data, multi-GPU, or fixed training.
- **Adaptive long campaign**: submit bounded batch workers, persist results, release compute, then wake Codex to decide the next experiment. Never hold a GPU while waiting for model reasoning.

For a deterministic three-hour training run, prefer batch. For a ten-hour adaptive investigation, prefer several checkpointed jobs rather than one ten-hour agent-held allocation.

## Execute the Research Lifecycle

Use this ordered lifecycle; a pivot may return to an earlier phase only with a recorded reason:

1. `territory`: read the mission; map current primary literature, open code/data/models, research cells, and hard constraints in `RESEARCH_BRIEF.md` and `LITERATURE.md`. Do not choose an active idea yet.
2. `discovery`: resolve at most a few promising adapter routes; use literature, formal tensions, and bounded `discovery`/`profile` probes to produce `DISCOVERY_REPORT.md` with reproducible observations and opportunity hypotheses.
3. `portfolio`: write `CANDIDATE_PORTFOLIO.json`. Keep at least 3 viable candidates for broad exploration, 2 for directed exploration, or 1 for a fixed problem. Each needs a causal hypothesis, mechanism, predicted signature, falsifier, cheap distinguishing test, prior-work delta, and cost.
4. `novelty_review`: promote one active candidate, write the bound `IDEA_REPORT.md` and `NOVELTY_AUDIT.json`, then hand off to `needs_novelty_review`. Only the controller's fresh reviewer writes `NOVELTY_REVIEW.json`. `clear_to_plan` opens planning; `exact_prior_reject` returns to portfolio/discovery; `conditional_probe` opens only a bounded distinguishing probe followed by `NOVELTY_REBUTTAL.json` and a fresh third-thread `NOVELTY_ARBITRATION.json`. Incompatible fallback claims cannot enter planning.
5. `planning`: freeze datasets/splits/metrics/baselines/seeds, adapter-specific evidence, claim ceilings, human-study requirements, and stop/pivot rules.
6. `implementation`: reuse credible bases, expose parameters, and keep source commits and compact outputs reproducible.
7. `sanity`: run the smallest real witness for ground truth, imports, kernels, output marker, memory, jobfs, and file count.
8. `experiments`: run matched baselines, main evidence, replication, ablations, negative controls, robustness, and adapter-specific audits.
9. `review`: use fresh integrity review over exact code/config/raw paths; same-family semantic review remains provisional.
10. `synthesis`: map every claim to machine-readable evidence; report uncertainty, failed branches, and limitations.
11. `paper`: write English LaTeX, compile cleanly, and retain only final sources, figures, bibliography, and PDF.
12. `audit`: refresh novelty, verify mission compatibility, numerical claims, human-evidence provenance, citations, artifact freshness, and compilation.

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

`discovery`, `sanity`, and `profile` may be registered before novelty clearance with compatible frozen inputs. They gather observations or verify feasibility and cannot support the final novelty claim by themselves. Before final clearance, candidate-independent input preparation is limited to six total environment/data/model attempts, 1,500 SU total, and 16 persistent entries, dynamically reduced by the campaign envelope. Each asset type permits at most three attempts. A failed attempt may use a new immutable experiment ID only after its PBS script changes; every failed attempt remains charged to the job, SU, and file budgets, and retry lineage is recorded. Input preparation requires `allow_storage_publish`; model acquisition additionally requires the separately recorded `allow_model_publish`. Use the audited jobfs helper, smoke-test the shell, Python/framework imports, and container execution, then publish only one immutable `.sqsh` under `/g/data/wa66/Xiangyu/enviroment_cache`, packed data under `/g/data/wa66/Xiangyu/Data`, or one provenance-recorded public model archive under `/g/data/wa66/Xiangyu/Data/models`. A `conditional_probe` review opens only `novelty_probe`: at most three attempts, 1,000 SU total (dynamically reduced for smaller campaigns), one GPU and four hours per job, and 32 persistent entries. `baseline`, `audit`, and `paper` require final resolution. `pilot`, `main`, and `ablation` require a cold-reviewed primary contribution accepted directly or by attested arbitration; both registration and submission recheck every hash-bound gate.

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

To make a campaign's model choice reproducible instead of inheriting a mutable global
configuration, pass the same explicit settings to preview and start:

```bash
bash "$STARTER" --root /absolute/campaign-root --session aris-CAMPAIGN \
  --model gpt-5.6-sol --reasoning-effort ultra
bash "$STARTER" --root /absolute/campaign-root --session aris-CAMPAIGN \
  --model gpt-5.6-sol --reasoning-effort ultra --start
```

The controller applies these settings to the resumable author and every fresh novelty reviewer
and arbiter thread. Record the exact launcher under the campaign root so a persistent-session
restart cannot silently fall back to different defaults.

Run the second command only after connecting to the persistent host. The helper first executes a real ephemeral Codex `apply_patch` canary, then starts a watchdog around the controller in a clean no-profile tmux command. This cluster cannot create the Linux user namespaces required by Codex's workspace sandbox, so unattended turns explicitly use `sandbox=danger-full-access` with `approval_policy=never`; the approved campaign contract, CLI gates, clean control-host environment, bounded state, and real canary are therefore mandatory. Do not launch the raw controller outside the starter. For an attended three-to-four-hour exploration, a foreground Codex `/goal` may drive the same campaign directly and use the interactive pane; still persist every experiment and handoff through `campaign.py`. Use the event-driven controller for queued or overnight work so Codex is invoked only when a decision is needed.

The first command previews. The second is permitted only after the campaign grants `allow_auto_agent` and a live pilot verifies Codex authentication/network access in the persistent session. The controller:

- enforces a single writer
- polls PBS no more often than 600 seconds
- invokes or resumes one `codex exec` turn only when action is needed
- launches `needs_novelty_review` in a new non-resumed adversarial thread and attests that its thread ID differs from the author thread
- preserves `conditional_probe` in `novelty_review`, enforces its job/SU/GPU/time/file caps, and launches `needs_novelty_arbitration` in a third non-resumed thread distinct from author and reviewer
- atomically promotes the next ranked backup after rejection, or returns to `discovery` when the portfolio is exhausted, without silently changing the paper type
- retries Codex exits, missing handoffs, stale leases, transient preflight failures, and PBS refresh failures with bounded backoff; a repeatedly broken author thread is rotated from durable campaign state
- stores one bounded rotating log under the campaign root
- uses a watchdog to restart an unexpectedly exited controller while the campaign remains active
- resumes from `campaign.json` after controller or persistent-session failure; tmux text is not research state

Read [references/persistent-control.md](references/persistent-control.md) before starting it. Do not parse `persistent-sessions list` output in automation.

Each campaign pins the skill repository commit and skill-tree hash. A changed installed skill pauses the campaign instead of silently changing its rules. After reviewing an update and confirming no jobs are active, pause the campaign and run `campaign.py skill-adopt --by USER --reason REASON`, then resume explicitly.

## Stop, Pause, and Handoff

Stop generating new work when an approved limit is reached, inode headroom becomes unsafe, the deadline passes, the pinned skill or artifact lineage fails integrity checks, evaluation would require fabricated evidence, or a `STOP`/pause request is recorded. Technical failures use automatic diagnosis and bounded-backoff retries. Scientific failure eliminates or revises a candidate, promotes a ranked backup, or returns to discovery; it is not by itself a controller stop.

Before every Codex turn exits, write exactly one control handoff:

```bash
"$PYTHON" "$CAMPAIGN" handoff /absolute/campaign-root \
  --state waiting_pbs \
  --reason "jobs 123 and 124 must finish before analysis"
```

Use `needs_novelty_review` only after the author records the audit and enters that phase. Use `needs_novelty_arbitration` only after a conditional review, completed bound probes, and a registered `NOVELTY_REBUTTAL.json`; the author must never write the arbitration. Use `waiting_human` only when the immutable mission requires external human evidence or authorization and no autonomous branch remains, `waiting_time` with `--wake-at` for scheduled work or automatic recovery, `paused` for a hard safety/integrity boundary, and `complete` only after the completion audit passes.

## Completion Standard

The goal is not complete because training ended or a PDF exists. Before `handoff --state complete`, inspect every required artifact and read [references/paper-completion.md](references/paper-completion.md). The CLI requires the mission, research brief, discovery report, candidate portfolio, idea report, novelty audit/review, research contract, experiment plan/ledger, results, experiment and claim audits, narrative report, paper source/PDF, citation audit, and final report. A conditional path additionally requires the bound rebuttal and attested arbitration. A route that requires human judgments also requires accepted `human_evaluation` evidence. Novelty artifacts must remain hash-bound and no more than 30 days old.

If only same-family semantic review was available, complete the campaign with `overall_assurance: provisional` and never call the paper submission-ready. Negative or inconclusive research may still produce an honest paper, but the title, abstract, claims, and limitations must match the evidence.
