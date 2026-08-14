# Campaign Contract

## Contents

1. Storage, mission, and approval
2. Adapter route and skill revision
3. Environment and data staging
4. Experiment registration
5. Batch and interactive execution
6. Monitoring and handoff
7. State and file-count behavior

## Storage, Mission, and Approval

`campaign.json` is the single durable control record. `campaign.lock` protects atomic updates.
`MISSION.json` is the immutable user-intent artifact. Research artifacts live beside them or in a
small, separate Git workspace below `/g/data/wa66/Xiangyu`; neither source nor artifacts may use
HOME. Codex session records remain under `.codex`, but no workload artifact may enter `.codex`.

Translate natural language into the schema in `adapter-system.md`. Use a reviewed mission file for
an extensible domain campaign:

```bash
"$PYTHON" "$CAMPAIGN" init "$ROOT" \
  --campaign-id audio-open-research \
  --mission-file /absolute/path/MISSION.json \
  --workspace /g/data/wa66/Xiangyu/WORKSPACE \
  --projects wa66,ey69,po67,iv96 \
  --max-su 5000 --max-jobs 24 --max-concurrent 2 --max-gpus 2 \
  --max-files 512 --max-agent-turns 60 \
  --deadline 2026-09-15T00:00:00Z
```

For a generic directed campaign, `--idea` remains a shorthand that creates a core-only mission.
Use `--domain-pack audio` to delegate Audio route selection. Add `--allow-diagnostic-final` only
when the user explicitly accepts application/reproduction/diagnostic work as the final output.

Initialize a draft before charged work. The proposed envelope contains:

- eligible scientific projects
- total maximum SU
- maximum submitted and concurrent jobs
- GPUs per job
- interactive and batch walltime ceilings
- persistent entry ceiling
- agent-turn ceiling and deadline
- separately granted auto-submit, storage-publish, interactive, auto-agent, and auto-cancel capabilities

`approve` may override proposed numeric fields before recording approval. Changing an approved envelope requires pausing or handing off to the user, confirming that no jobs are active, then recording a new explicit approval with `approve --replace`; never hand-edit JSON. This is also the quarterly-allocation rollover path.

Run current account/inode checks:

```bash
"$PYTHON" "$CAMPAIGN" preflight "$ROOT"
"$PYTHON" "$CAMPAIGN" status "$ROOT"
```

The four compute projects are dynamic allocations, not storage spill areas. Persistent campaign data stays in `wa66`; each experiment's charging project must scientifically cover that work.

## Adapter Route and Skill Revision

The adapter registry is data-driven. Validate and inspect it with:

```bash
"$PYTHON" "$SKILL/scripts/adapter_registry.py" validate
"$PYTHON" "$SKILL/scripts/adapter_registry.py" list --pack audio
```

When the mission delegates route selection, `route-set` is allowed only in `territory` or
`discovery`. It requires at least one task, model, lever, and evidence adapter; adds pack defaults;
checks evidence dependencies and human-evaluation policy; and stores the route plus registry hash:

```bash
"$PYTHON" "$CAMPAIGN" route-set "$ROOT" \
  --adapters audio.speech-understanding,audio.encoder-discriminative,core.systems,core.system-measurement,audio.reference-task-evaluation \
  --reason "stage-wise evidence identifies a reproducible encoder-system opportunity"
```

Changing a route invalidates portfolio and later claim artifacts. A changed adapter registry also
changes the pinned skill tree. Explicit `skill-adopt` updates the registry pin, returns the campaign
to discovery when necessary, and invalidates route-bound evidence instead of silently migrating it.

`campaign.json` pins the Git commit and tree hash of this skill. The controller pauses if the
installed revision changes. This prevents an unattended campaign from silently acquiring new
scientific or cluster permissions. To adopt a reviewed update, first confirm no jobs are active
and pause or hand off to the user (an unapproved draft is already eligible):

```bash
"$PYTHON" "$CAMPAIGN" skill-adopt "$ROOT" \
  --by USER --reason "reviewed installed skill revision and migration"
"$PYTHON" "$CAMPAIGN" resume "$ROOT" --reason "new skill revision adopted"
```

Forward phase changes advance exactly one phase. Backward pivots are allowed with a reason. The
phase order begins `territory -> discovery -> portfolio -> novelty_review -> planning`. Planning
and later phases require mission/route/portfolio-bound novelty artifacts. The author requests the
controller-only reviewer with:

```bash
"$PYTHON" "$CAMPAIGN" handoff "$ROOT" --state needs_novelty_review \
  --reason "author audit complete; request independent adversarial search"
```

The control state `novelty_reviewer_running` cannot change phases, approval, storage, or
experiments and may record only `novelty_review`. The controller supplies the cold-review
attestation after verifying a distinct thread and unchanged audit. The reviewer returns one of
`clear_to_plan`, `conditional_probe`, or `exact_prior_reject`; a hard rejection requires checked
functional equivalence, not merely known components. A conditional decision keeps the phase at
`novelty_review`, opens only capped `novelty_probe` work, then requires a bound author rebuttal and
`needs_novelty_arbitration`. The controller launches a fresh third thread, which may record only
`novelty_arbitration`; its ID must differ from author and reviewer. A rejected, changed, or
mission-incompatible candidate returns to `portfolio` when a backup exists, otherwise `discovery`.

## Hypothesis and Learning State

After recording `CANDIDATE_PORTFOLIO.json`, initialize the bounded research graph before entering
`novelty_review`:

```bash
"$PYTHON" "$CAMPAIGN" learning-init "$ROOT" \
  --reason "seed versioned hypotheses from the candidate portfolio"
"$PYTHON" "$CAMPAIGN" claim-freeze "$ROOT" \
  --hypothesis-id CANDIDATE_ID --reason "predeclare the paper-facing mechanism"
```

This creates only `RESEARCH_GRAPH.json` and `LEARNING_LEDGER.jsonl`. Both are atomically updated
and registered as deterministic artifacts. A paused legacy campaign with already attested novelty
may instead use `learning-init --adopt-current-claim`; it records old terminal jobs as legacy,
non-confirmatory provenance and does not rewrite their meaning.

Every terminal non-external experiment must be interpreted with `learning-record` before another
adaptive experiment is registered. Technical invalidity authorizes `repair` without a hypothesis
change. Valid falsification, qualification, surprise, or proposed `refine`, `branch`, `pivot`, or
`stop` requires:

```bash
"$PYTHON" "$CAMPAIGN" handoff "$ROOT" --state needs_failure_review \
  --reason "FINDING_ID requires an independent causal assessment"
```

Only the controller's fresh `failure_reviewer_running` thread may call `learning-review`. The
controller checks a different thread ID, unchanged interpretation/result, and a clean unchanged Git
workspace before adding the independent attestation. Only then may the author use
`hypothesis-fork` or a scientifically justified `candidate-pivot`. See `research-workflow.md` for
the exact interpretation, review, and child-hypothesis schemas.

Replacing an exhausted portfolio or changing its adapter route sets `portfolio_refresh_required`
and blocks experiment registration. Run `learning-reseed --reason REASON` after recording the new
portfolio. It retains old eliminated hypotheses and ledger history while reusing the same two files.

## Environment, Data, and Model Staging

If no compatible image exists, request `allow_storage_publish` in the user-approved envelope, then copy `run-on-gadi/assets/pbs/build-env-copyq.pbs` into the research workspace, replace every placeholder, and use its jobfs builder. Set a fixed `ENV_NAME` and `ENV_TAG` so the declared success path is known before submission, and record the environment-spec SHA-256 so a queued job cannot consume changed dependencies. Preview and submit through the campaign:

```bash
"$PYTHON" "$CAMPAIGN" external-submit "$ROOT" \
  --id build-env-v1 --stage environment \
  --pbs /workspace/pbs/build-env-v1.pbs \
  --success-path /g/data/wa66/Xiangyu/enviroment_cache/project-v1.sqsh \
  --expected-files 1

"$PYTHON" "$CAMPAIGN" external-submit "$ROOT" \
  --id build-env-v1 --stage environment \
  --pbs /workspace/pbs/build-env-v1.pbs \
  --success-path /g/data/wa66/Xiangyu/enviroment_cache/project-v1.sqsh \
  --expected-files 1 --execute
```

Use the corresponding `acquire-data-copyq.pbs` template for datasets. Environment scripts must invoke the installed `build_conda_sqsh.sh`; data scripts must invoke `pack_data.sh`. Direct persistent-filesystem mutation is rejected by the PBS linter. A data success path must be under `/g/data/wa66/Xiangyu/Data` and represent an archive or controlled shard set. Standard compute jobs have no external internet.

Public pretrained models are a separate, explicitly approved packed-input class. Record
`allow_model_publish` in addition to `allow_storage_publish`, copy
`run-on-gadi/assets/pbs/acquire-model-copyq.pbs` into the workspace, pin the repository to an
immutable commit, record the license, and replace every placeholder. The copyq job downloads into
jobfs and invokes `pack_data.sh --kind model`; it may publish exactly one archive directly under
`/g/data/wa66/Xiangyu/Data/models`:

```bash
"$PYTHON" "$CAMPAIGN" external-submit "$ROOT" \
  --id acquire-model-v1 --stage model \
  --pbs /workspace/pbs/acquire-model-v1.pbs \
  --success-path /g/data/wa66/Xiangyu/Data/models/model-COMMIT.tar.zst \
  --expected-files 1

"$PYTHON" "$CAMPAIGN" external-submit "$ROOT" \
  --id acquire-model-v1 --stage model \
  --pbs /workspace/pbs/acquire-model-v1.pbs \
  --success-path /g/data/wa66/Xiangyu/Data/models/model-COMMIT.tar.zst \
  --expected-files 1 --execute
```

An external success path must not already exist. Publish a new immutable version instead of overwriting a known environment, dataset, or model. `--expected-files` counts the published file itself, or a shard directory plus all entries below it; a finished external job that exceeds this declaration fails the campaign check.

After the job succeeds, record the published storage object:

```bash
"$PYTHON" "$CAMPAIGN" storage-set "$ROOT" \
  --environment /g/data/wa66/Xiangyu/enviroment_cache/project-v1.sqsh \
  --data /g/data/wa66/Xiangyu/Data/dataset-v1.tar.zst \
  --data /g/data/wa66/Xiangyu/Data/models/model-COMMIT.tar.zst
```

Expand a packed model only below the consuming compute job's `$PBS_JOBFS`, using
`run-on-gadi/scripts/stage_archive.sh`. Never persist an expanded conda/venv, model repository,
model shard tree, pip/Hugging Face cache, extracted sample tree, or compilation directory.

The preview command is available during discovery because it has no scheduler or storage side
effect. `--execute` always requires `allow_storage_publish`; `stage=model` also requires
`allow_model_publish`. Before final novelty clearance, the CLI additionally allows only
candidate-independent discovery infrastructure: at most six environment/data/model attempts in total,
1,500 SU total, and 16 persistent entries, all dynamically reduced by the approved campaign.
Each asset type permits at most three attempts. Retry a failed attempt only with a new experiment
ID and changed PBS script; the state records its predecessor and charges all failed work. After that cap, or
after entering planning, storage publication requires a mission-compatible novelty resolution.
Do not create candidate-specific dependency/data variants merely to make an idea feel concrete.

## Experiment Registration

The workspace must be the root of a Git repository below `/g/data/wa66/Xiangyu`, with an initial commit and no submodules. It cannot contain the campaign directory or be contained by it. Commit a deliberate, clean implementation before registering a batch experiment. The CLI records that commit, the `.sqsh` size/mtime identity, and metadata identities for the campaign's packed data inputs. A queued worker revalidates them and expands the registered commit in jobfs, so later control-host edits cannot silently change the run. `interactive-run` records the latest clean commit on every debug cycle before expanding it in the current allocation.

Register a sanity experiment before submission:

```bash
"$PYTHON" "$CAMPAIGN" experiment-add "$ROOT" \
  --id sanity-001 --stage sanity --mode batch \
  --evidence-role diagnostic --hypothesis-id CANDIDATE_ID \
  --queue gpuhopper --project wa66 --walltime 00:15:00 \
  --ncpus 12 --ngpus 1 --mem-gb 64 --jobfs-gb 100 \
  --expected-files 8 --success-file metrics.json \
  --command-json '["/env/bin/python","{WORKSPACE}/train.py","--config","{WORKSPACE}/configs/sanity.json","--data","{DATA_ROOT}/dataset-v1.tar.zst","--output","{RESULT_DIR}/metrics.json"]'
```

Commands are argument vectors, not shell strings. Supported literal substitutions are:

- `{RESULT_DIR}`: `$PBS_JOBFS` staging for this attempt; the guard publishes it only after validation
- `{PBS_JOBFS}`: node-local job storage
- `{WORKSPACE}`: jobfs expansion of the exact recorded Git commit
- `{DATA_ROOT}`: `/g/data/wa66/Xiangyu/Data`

The job runs through `run_sqsh.sh`; HOME, source, data, environments, `.codex`, and the durable campaign are read-only inside the container. The command writes only to jobfs staging. After a zero exit, the worker requires the success marker, rejects symlinks/special files and an entry-count overflow, copies into a hidden campaign-side staging directory, revalidates it, and atomically renames it to the durable result path. A failed or oversized run publishes nothing. Worker success remains `finishing` until a permitted `qstat` refresh confirms the PBS terminal exit and revalidates durable output.

Stages are evidence classes, not labels chosen to bypass review:

- `discovery`, `profile`: bounded observation or feasibility probes; novelty clearance is not required
- `sanity`: infrastructure and real-path witness; novelty clearance is not required
- `novelty_probe`: only after `conditional_probe`; at most three attempts, 1,000 SU total (reduced for small envelopes), one GPU/four hours per job, and 32 persistent entries
- `baseline`, `audit`, `paper`: require a mission-compatible resolved contribution
- `pilot`, `main`, `ablation`: require a mission-accepted primary contribution cleared directly or by attested third-thread arbitration

The CLI checks the classification when the experiment is registered and again immediately
before batch or interactive submission. A stale or changed artifact therefore blocks a
previously registered experiment. Every claim-bearing experiment also stores the exact mission,
route, portfolio, active candidate, idea, novelty-audit, novelty-review, and claim-class hashes.
Conditional probes use a separate pre-clearance binding; post-arbitration claim experiments also
bind rebuttal and arbitration hashes. After any pivot, register a new experiment instead of
relabelling or resubmitting the old one.

For later work, declare dependencies and an evidence stage:

```bash
"$PYTHON" "$CAMPAIGN" experiment-add "$ROOT" \
  --id main-seeds --stage main --mode batch \
  --evidence-role confirmatory --hypothesis-id CANDIDATE_ID \
  --depends-on sanity-001 \
  --queue dgxa100 --project ey69 --walltime 08:00:00 \
  --ncpus 16 --ngpus 1 --mem-gb 128 --jobfs-gb 300 \
  --expected-files 24 --success-file aggregate_metrics.json \
  --command-json '["/env/bin/python","{WORKSPACE}/run_bundle.py","--manifest","{WORKSPACE}/configs/main-seeds.json","--output","{RESULT_DIR}/aggregate_metrics.json"]'
```

Bundle small sweep cells inside one worker and write one aggregate metrics file. Do not create one PBS job, checkpoint, or log per seed when one bounded worker can run them safely.

## Batch and Interactive Execution

Batch preview and execution:

```bash
"$PYTHON" "$CAMPAIGN" submit "$ROOT" --id sanity-001
"$PYTHON" "$CAMPAIGN" submit "$ROOT" --id sanity-001 --execute
```

Preview includes maximum SU, live project availability, inode/file budget, linter warnings, and the exact PBS script. `--execute` is rejected unless `allow_auto_submit` is recorded.

Interactive experiments use the same registration with `--mode interactive`, a walltime no greater than `04:00:00`, and a named tmux session:

```bash
"$PYTHON" "$CAMPAIGN" interactive "$ROOT" --id debug-001
"$PYTHON" "$CAMPAIGN" interactive "$ROOT" --id debug-001 --session aris-campaign-debug --execute
```

After allocation, verify compute hostname, `PBS_ENVIRONMENT=PBS_INTERACTIVE`, `PBS_JOBFS`, and GPU visibility before sending a workload command. Close and account for the allocation:

```bash
"$PYTHON" "$CAMPAIGN" interactive-run "$ROOT" --id debug-001
"$PYTHON" "$CAMPAIGN" interactive-publish "$ROOT" --id debug-001
exit
# Back on the persistent control host after the PBS shell has exited:
"$PYTHON" "$CAMPAIGN" interactive-close "$ROOT" \
  --id debug-001 --outcome completed --actual-walltime 02:17:00
```

`interactive-run` executes the registered argument vector through the frozen image and writes only below `$PBS_JOBFS/gadi-autoresearch-output/ID`. It may be rerun while debugging. `interactive-publish` is allowed only after the latest run exits zero; it enforces the declared entry limit and atomically publishes compact output. Do not mark the attempt terminal until the interactive shell has exited. A failed or cancelled allocation may be closed without publication.

`interactive-close --actual-walltime` records a useful manual estimate, but it is not scheduler evidence. The campaign therefore keeps the full requested SU reserved for that attempt. Only `resources_used.walltime` obtained by the rate-limited PBS refresh can reduce committed SU below the job's maximum charge.

An interactive result becomes sanity evidence only after recording a compact deterministic JSON artifact with `status`, source commit, exact `image`, argument-vector `command`, device, PBS job/session evidence, result marker, and produced-entry count:

```json
{
  "status": "pass",
  "source_commit": "0123456789abcdef0123456789abcdef01234567",
  "image": "/g/data/wa66/Xiangyu/enviroment_cache/project-v1.sqsh",
  "command": ["/env/bin/python", "/absolute/smoke.py"],
  "device": "NVIDIA H200",
  "pbs_evidence": {"job_id": "123.gadi-pbs", "environment": "PBS_INTERACTIVE"},
  "result_marker": "/g/data/wa66/Xiangyu/Result/project/campaign/sanity-summary.json",
  "produced_entries": 1
}
```

Then record it:

```bash
"$PYTHON" "$CAMPAIGN" artifact "$ROOT" \
  --name sanity --path "$ROOT/sanity-summary.json" --assurance deterministic
```

## Monitoring and Handoff

Refresh at most once every ten minutes:

```bash
"$PYTHON" "$CAMPAIGN" refresh "$ROOT"
```

There is no rate-limit bypass. The CLI asks `qstat` once for all active batch job IDs and estimates actual SU from used walltime when available. It never polls an interactive request just to discover its job ID; inspect the recorded tmux pane instead.

Cancellation is preview-only unless the original campaign approval explicitly included `allow_auto_cancel`. It can target only the latest active job ID already recorded for that experiment:

```bash
"$PYTHON" "$CAMPAIGN" cancel "$ROOT" --id main-seeds
"$PYTHON" "$CAMPAIGN" cancel "$ROOT" --id main-seeds --execute
```

A successful `qdel` records `cancel_requested`; the attempt remains in the active/concurrency budget until a rate-limited PBS refresh confirms the terminal state.

For an interactive pane without a recorded job ID, exit the known PBS shell; never guess a `qdel` target.

Record phase changes and canonical artifacts:

```bash
"$PYTHON" "$CAMPAIGN" phase "$ROOT" experiments --reason "sanity passed"
"$PYTHON" "$CAMPAIGN" artifact "$ROOT" --name results \
  --path "$ROOT/RESULTS.md" --assurance deterministic
```

Every agent turn ends with one handoff. In `novelty_review`, the author must use
`needs_novelty_review` until an attested verdict exists; the reviewer hands back to
`needs_agent`. After a conditional verdict, the author uses `waiting_pbs` for probes and then
`needs_novelty_arbitration` only after registering the bound rebuttal; the arbiter hands back to
`needs_agent`. After a terminal experiment, record its learning interpretation. When that record
requires independent causal review, the author uses `needs_failure_review`; only the fresh critic
returns to `needs_agent`. `complete` runs the artifact gate and refuses active jobs, stale/empty or
expired novelty artifacts, an invalid PDF, or missing required evidence. A safety pause can be
resumed only with an explicit reason:

```bash
"$PYTHON" "$CAMPAIGN" resume "$ROOT" --reason "inode issue resolved and live preflight is green"
```

## State and File-Count Behavior

- State updates use `flock`, a same-directory temporary file, `fsync`, and atomic replace.
- History is capped at 200 events inside `campaign.json`.
- Exact rendered PBS scripts and job IDs are stored in the JSON; generated submission files exist only temporarily in `/tmp`.
- Each PBS attempt has one combined log. Consolidate completed logs by phase after extracting failure evidence.
- Each experiment declares an expected output-entry ceiling. Batch and interactive commands stage under jobfs; an overflow is never published and pauses the campaign.
- The file budget also reserves result objects/directories, combined PBS logs, and bounded controller state rather than counting only scientific output files.
- The campaign compares current campaign entries, new files added to the Git workspace since initialization, published environment/data objects, planned outputs, and control-file reserve against the approved persistent-file ceiling and live `wa66` inode headroom.
- The controller keeps at most `controller.log` and `controller.previous.log`.
- Mission, route, portfolio, and novelty state use a fixed number of compact records, not per-query traces.
- Hypothesis evolution adds exactly one bounded graph and one bounded JSONL ledger, never one file per finding or review.
