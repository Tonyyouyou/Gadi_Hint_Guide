# Interactive Debugging

## Choose the Mode First

Classify every request before using PBS:

1. **Static inspection**: read code and logs, run syntax checks and the PBS linter, and prepare commands. Do not request compute resources.
2. **Interactive debug**: use a detached `tmux` session on a login node to hold one explicitly approved `qsub -I` connection. Perform compute, GPU, and jobfs work only after PBS provides a compute-node shell.
3. **Production batch**: submit a standalone PBS script only after the interactive or short batch smoke test passes. A debug request is never production-submission permission.

## Why tmux

Gadi currently provides `/bin/tmux` 2.7 and `/bin/screen` 4.06.02. Prefer `tmux`. PBS connects an interactive job's stdin, stdout, and stderr to the terminal running `qsub -I`, so keeping that terminal inside tmux allows an SSH disconnect without immediately losing the terminal connection.

NCI's [Job Submission guide](https://opus.nci.org.au/spaces/Help/pages/236880320/Job%2BSubmission...) explicitly recommends interactive jobs for testing and debugging before running the full job. It also warns that login-node work exceeding roughly 30 minutes or 4 GiB can be terminated; tmux does not exempt a process from those limits.

Start tmux on the login node **before** `qsub -I`. Do not start it on the allocated compute node and do not use `nohup qsub -I`.

The default tmux socket is in the login node's local `/tmp`. This is inode-safe for persistent storage, but it has two consequences:

- Reattach on the same login host shown by `hostname -f`.
- A login-node restart destroys the tmux server and may break the interactive connection.

Tmux does not extend PBS walltime and does not make an interactive job suitable for production.

## Preview and Start

Preview a one-GPU H200 request:

```bash
bash /g/data/wa66/Xiangyu/.codex/skills/run-on-gadi/scripts/debug_session.sh \
  --kind h200 \
  --project CHANGE_ME \
  --walltime 01:00:00
```

The helper defaults to preview-only. It shows the login host, unique session name, current project report, exact `qsub` command, and estimated SU. It accepts `cpu`, `v100`, `a100`, and `h200` and refuses interactive walltimes over two hours.

Use the least expensive GPU that reproduces the target behavior. Select H200 only when Hopper compatibility, H200 memory, or the production target actually requires it.

Only after the user explicitly approves that displayed request, repeat it with `--start`. This creates a detached tmux session and submits `qsub -I`. Starting tmux alone is not submission approval.

The helper starts a clean `bash --noprofile --norc` pane so stale HOME startup entries cannot redirect the login-side command into an expired `/jobfs/...` path. It does not edit HOME configuration.

Useful commands on the same login node:

```bash
tmux list-sessions
tmux attach -t SESSION
tmux capture-pane -p -t SESSION -S -200
```

Do not inspect, reuse, send keys to, or kill a pre-existing tmux session unless the user identifies it as the target.

## Agent Control

For detached operation, use `tmux capture-pane` to read the named pane and `tmux send-keys -l` followed by a separate `Enter` to issue one reviewed command at a time. Capturing a local tmux pane is preferable to repeatedly querying PBS while the interactive request waits in the queue.

Keep the login host and exact unique session name in the task context. Before every `send-keys`, verify that the target session name matches the one created for this task. Do not attach to or automate a generic name such as `debug` or `idebug` that may belong to the user.

Do not save a continuous tmux transcript to HOME, `.codex`, gdata, or scratch. Preserve only compact diagnostics in an approved result directory when necessary.

## Confirm Allocation

The `qsub -I` pane initially remains on the login node while queued. Do not run the workload yet. When PBS starts the job, verify:

```bash
hostname -f
echo "$PBS_JOBID"
echo "$PBS_ENVIRONMENT"
echo "$PBS_JOBFS"
echo "$CUDA_VISIBLE_DEVICES"
nvidia-smi
```

Require a compute-node hostname, `PBS_ENVIRONMENT=PBS_INTERACTIVE`, a real `PBS_JOBFS`, and the expected GPU count before debugging.

## Debug Inside the Allocation

Use the same frozen `.sqsh` intended for production. Enter it through `run_sqsh.sh` so HOME and persistent filesystems remain read-only and caches go to jobfs:

```bash
RUNNER=/g/data/wa66/Xiangyu/.codex/skills/run-on-gadi/scripts/run_sqsh.sh
IMAGE=/g/data/wa66/Xiangyu/enviroment_cache/CHANGE_ME.sqsh

bash "$RUNNER" --nv "$IMAGE" /bin/bash
```

Use a tiny representative sample, one process, and one GPU first. Keep temporary downloads, extracted data, traces, profiler output, and caches in `$PBS_JOBFS`. Use a user-approved result directory with `--write-path` only when a compact diagnostic or checkpoint must survive.

Edit small source files from a separate login-node tmux window or the normal Codex workspace, then rerun them on the allocated node. Never perform computation in that login-node window.

## Finish and Promote

Exit the container, then exit the PBS interactive shell promptly to release charged resources. A finished tmux pane may remain for diagnostics because the helper enables `remain-on-exit`; capture needed text and remove only that known session.

Before production:

- Record the working image, command, modules, data sample, and observed memory/jobfs/GPU behavior.
- Convert the command to a standalone batch PBS script with a durable result/log path and checkpoint policy.
- Re-run the live project and inode preflight.
- Run `lint_pbs.py` and show the new production SU estimate.
- Obtain separate explicit approval for the batch `qsub`.

Do not run a full dataset, multi-GPU job, checkpoint chain, or long walltime merely because interactive debugging was approved.
