# Campaign Contract

## Contents

1. Storage and approval
2. Environment and data staging
3. Experiment registration
4. Batch and interactive execution
5. Monitoring and handoff
6. State and file-count behavior

## Storage and Approval

`campaign.json` is the single durable control record. `campaign.lock` protects atomic updates. Research artifacts live beside it or in a small, separate Git workspace below `/g/data/wa66/Xiangyu`; neither source nor artifacts may use HOME. Codex session records remain under `.codex`, but no workload artifact may enter `.codex`.

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

## Environment and Data Staging

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

Use the corresponding `acquire-data-copyq.pbs` template for downloads. Environment scripts must invoke the installed `build_conda_sqsh.sh`; data scripts must invoke `pack_data.sh`. Direct persistent-filesystem mutation is rejected by the PBS linter. A data success path must be under `/g/data/wa66/Xiangyu/Data` and represent an archive or controlled shard set. Standard compute jobs have no external internet.

An external success path must not already exist. Publish a new immutable version instead of overwriting a known environment or dataset. `--expected-files` counts the published file itself, or a shard directory plus all entries below it; a finished external job that exceeds this declaration fails the campaign check.

After the job succeeds, record the published storage object:

```bash
"$PYTHON" "$CAMPAIGN" storage-set "$ROOT" \
  --environment /g/data/wa66/Xiangyu/enviroment_cache/project-v1.sqsh \
  --data /g/data/wa66/Xiangyu/Data/dataset-v1.tar.zst
```

Never persist an expanded conda/venv, pip cache, Hugging Face cache, extracted sample tree, or compilation directory.

## Experiment Registration

The workspace must be the root of a Git repository below `/g/data/wa66/Xiangyu`, with an initial commit and no submodules. It cannot contain the campaign directory or be contained by it. Commit a deliberate, clean implementation before registering a batch experiment. The CLI records that commit, the `.sqsh` size/mtime identity, and metadata identities for the campaign's packed data inputs. A queued worker revalidates them and expands the registered commit in jobfs, so later control-host edits cannot silently change the run. `interactive-run` records the latest clean commit on every debug cycle before expanding it in the current allocation.

Register a sanity experiment before submission:

```bash
"$PYTHON" "$CAMPAIGN" experiment-add "$ROOT" \
  --id sanity-001 --stage sanity --mode batch \
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

For later work, declare dependencies and an evidence stage:

```bash
"$PYTHON" "$CAMPAIGN" experiment-add "$ROOT" \
  --id main-seeds --stage main --mode batch \
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

Every agent turn ends with one handoff. `complete` runs the artifact gate and refuses active jobs, stale/empty artifacts, an invalid PDF, or missing required evidence. A safety pause can be resumed only with an explicit reason:

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
