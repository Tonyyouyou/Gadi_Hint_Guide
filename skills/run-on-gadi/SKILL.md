---
name: run-on-gadi
description: Prepare, validate, submit, monitor, and troubleshoot NCI Gadi PBS jobs with strict inode-safe storage and environment workflows. Use for persistent-session or tmux-backed qsub -I debugging; production batch jobs; bounded autoresearch campaigns; Gadi CPU/GPU work including V100, A100, and H200; PBS scripts; dynamic project/SU selection; quota and file-count checks; copyq downloads; Singularity SquashFS environments; large datasets; packed public model assets; checkpoints; distributed PyTorch; or work using /g/data/wa66/Xiangyu.
---

# Run on Gadi

Treat persistent file count as a first-class resource alongside SU, bytes, memory, GPUs, and walltime.

## Classify the Run Mode

State one mode before acting:

- **Static inspection**: read, edit, lint, and test without PBS.
- **Interactive debug**: preserve an explicitly approved `qsub -I` terminal in control-host `tmux`, preferably on an NCI persistent session for multi-hour agent exploration, then debug only after PBS allocates a compute/GPU node. A workload failure returns to this shell; reuse the allocation for the next repaired run instead of submitting another debug batch.
- **Production batch**: submit a standalone PBS script only after a smoke test and a separate production submission approval.

Words such as "debug", "test", "try", or "interactive" never authorise a production job. Words such as "prepare", "write", or "fix the PBS script" never authorise any `qsub`. An explicitly approved `gadi-autoresearch` campaign may authorise submissions only through its validating campaign CLI and only within the recorded envelope; it never authorises raw `qsub` or `qdel`. Read [references/debugging.md](references/debugging.md) for the mandatory tmux workflow and debug-to-production gate.

## Enforce Storage Boundaries

Follow these rules before all other preferences:

1. Reserve `/g/data/wa66/Xiangyu/.codex` exclusively for Codex configuration, skills, and their source repositories. Never store datasets, models, training environments, package caches, downloads, checkpoints, logs, or experiment output there.
2. Keep HOME for small code and shell configuration only. Never let package caches, environments, datasets, model downloads, checkpoints, or unbounded PBS logs fall back there.
3. Store frozen environments as single `.sqsh` files in `/g/data/wa66/Xiangyu/enviroment_cache`. Preserve this existing spelling.
4. Store datasets and packed input assets in `/g/data/wa66/Xiangyu/Data`. A public pretrained model requires explicit user approval and may persist only as one immutable, provenance-recorded `.tar.zst` directly under `/g/data/wa66/Xiangyu/Data/models`.
5. Store results in an existing matching `/g/data/wa66/Xiangyu/Result*` tree or a user-approved task directory under `/g/data/wa66/Xiangyu`. Do not invent a destination when the repository or user already defines one.
6. Create expanded environments, dependency caches, downloads, compilation trees, and extracted datasets only in `$PBS_JOBFS`.
7. Persist environments and datasets as a single archive/image or a modest number of coarse shards. Never persist an expanded conda/venv, model repository, model shard tree, Hugging Face cache, pip cache, or millions of sample files.
8. Check inode usage as well as bytes before writing. Free capacity does not imply that another expanded environment or dataset is safe.
9. Do not use another project's gdata as a spill area. The four projects are possible compute allocations, not alternative persistent roots.

Read [references/site-profile.md](references/site-profile.md) for personal paths and projects. Read [references/storage-environments-data.md](references/storage-environments-data.md) before installing an environment or acquiring data.

## Run Read-Only Preflight

Locate this skill, then run:

```bash
python /g/data/wa66/Xiangyu/.codex/skills/run-on-gadi/scripts/probe_gadi.py
```

The probe checks Gadi identity, HOME quota, group membership, persistent-root path safety, and current `nci_account` values for `wa66`, `ey69`, `po67`, and `iv96`. Allocations are dynamic; never reuse an earlier KSU or inode observation.

Choose the PBS charging project in this order:

1. Use the project to which the research task belongs.
2. Confirm current membership and sufficient allocation with `nci_account -P <project>`.
3. If multiple projects legitimately cover the task, compare current available KSU and show the proposed choice and cost.
4. Never charge an unrelated project merely because it has more KSU.

The charging project and storage project are independent. A job charged to an authorised project may mount `gdata/wa66` for this user's persistent files. Add `#PBS -l storage=gdata/wa66` whenever a job uses `/g/data/wa66/Xiangyu`.

## Select Resources

Use route queue names, never names ending in `-exec`.

- Use `normal` for ordinary Cascade Lake CPU work.
- Use `normalsr` for CPU work benefiting from Sapphire Rapids or more memory per node.
- Use `copyq` for internet access, downloads, dependency resolution, and massdata. Standard compute queues have no external internet.
- Use `gpuvolta` for V100 32 GB, normally 12 CPU cores per GPU.
- Use `dgxa100` for A100 80 GB, normally 16 CPU cores per GPU.
- Use `gpuhopper` for H200 141 GB, normally 12 CPU cores per GPU. Each H200 node has 4 GPUs, 48 CPU cores, 1 TiB RAM, and roughly 1.7 TB usable jobfs.

Prefer the least expensive architecture meeting memory, compatibility, and turnaround requirements. H200 is not automatically best: compare queue pressure and estimated SU. Read [references/pbs-gpu-distributed.md](references/pbs-gpu-distributed.md) for verified queue limits and distributed patterns.

Pin module versions only after checking `module avail` and `module show`. Re-check official Queue Structure and Queue Limits pages if the dated snapshot is stale or PBS rejects a request.

## Create and Validate PBS Scripts

Start from a template in `assets/pbs/` and replace every `CHANGE_ME`. Keep all `#PBS` directives together immediately after the shebang.

Every production script should explicitly set:

- `-P`, `-q`, `walltime`, `ncpus`, `mem`, `jobfs`, and `wd`
- `ngpus` for GPU jobs
- `storage=gdata/wa66` plus only other filesystems actually referenced
- `-j oe` and an absolute `-o` path under a pre-existing result/log directory, never HOME or `.codex`
- `set -euo pipefail`
- all transient cache variables under `$PBS_JOBFS`

Validate before submission:

```bash
python /g/data/wa66/Xiangyu/.codex/skills/run-on-gadi/scripts/lint_pbs.py job.pbs
```

Resolve all errors. Review warnings for resource ratios, walltime tiers, network commands outside `copyq`, persistent extraction, inode-producing caches, and any workload write under `.codex`. Report estimated SU.

Generate and edit scripts without extra approval. Run `qsub`, `qdel`, or destructive cleanup only when the user explicitly requests that side effect. A recorded `gadi-autoresearch` envelope with `allow_auto_submit=true` counts as scoped submission approval only when `gadi-autoresearch/scripts/campaign.py` performs the live validation and submission. Present a complete interactive `qsub -I` command before executing it; an approved campaign with `allow_interactive=true` may start the previewed request through that CLI.

For interactive debugging, preview [scripts/debug_session.sh](scripts/debug_session.sh) first. Only after explicit approval may it be repeated with `--start`. Do not touch an existing tmux session unless the user identifies it as the target. For a multi-hour controller, preview [scripts/persistent_session.sh](scripts/persistent_session.sh); create the NCI persistent session only after approval and keep computation in PBS.

## Build Environments in JobFS

Use [assets/pbs/build-env-copyq.pbs](assets/pbs/build-env-copyq.pbs) with [scripts/build_conda_sqsh.sh](scripts/build_conda_sqsh.sh):

1. Submit a `copyq` job with sufficient `$PBS_JOBFS`.
2. Redirect conda, pip, XDG, Torch, and Hugging Face caches into `$PBS_JOBFS`.
3. Create the expanded environment under `$PBS_JOBFS`.
4. Pack it with `conda-pack --dest-prefix /env`.
5. Build one `.sqsh` atomically in `/g/data/wa66/Xiangyu/enviroment_cache`.
6. Validate Python inside the image before publishing.
7. For CUDA packages, run a short smoke test on the target GPU queue.

Example inside a suitable PBS job:

```bash
bash /g/data/wa66/Xiangyu/.codex/skills/run-on-gadi/scripts/build_conda_sqsh.sh \
  --name myenv \
  --environment environment.yml
```

The existing `/home/561/xz4320/miniconda3/bin/conda` may be used as a read-only bootstrap executable, but the new prefix and all package caches must stay in jobfs. Do not create another expanded environment in HOME.

Use [scripts/run_sqsh.sh](scripts/run_sqsh.sh) to execute the image. It mounts HOME, gdata, and scratch read-only by default and only exposes explicitly approved result directories as writable:

```bash
RESULT_DIR=/g/data/wa66/Xiangyu/Result_CHANGE_ME/run-id
mkdir -p "$RESULT_DIR"
bash /g/data/wa66/Xiangyu/.codex/skills/run-on-gadi/scripts/run_sqsh.sh \
  --nv \
  --write-path "$RESULT_DIR" \
  /g/data/wa66/Xiangyu/enviroment_cache/myenv-TAG.sqsh \
  /env/bin/python /absolute/path/train.py --output-dir "$RESULT_DIR"
```

Build a new dated image to change packages; do not mutate an existing image. Keep the previous working image until a real workload succeeds.

## Acquire and Stage Data

Use [assets/pbs/acquire-data-copyq.pbs](assets/pbs/acquire-data-copyq.pbs) and [scripts/pack_data.sh](scripts/pack_data.sh):

1. Download into `$PBS_JOBFS/download` on `copyq`.
2. Verify checksums and expected content there.
3. Convert excessive small files to a streamable format when practical.
4. Publish one archive or controlled coarse shards in `/g/data/wa66/Xiangyu/Data`.
5. Test the archive before the PBS job discards staging.

For data larger than one node's jobfs, process deterministic partitions sequentially into multi-GB shards. Never work around jobfs size by persistently expanding into scratch or gdata. At runtime, stream compatible shards or use [scripts/stage_archive.sh](scripts/stage_archive.sh) to extract only the working set into jobfs.

For an explicitly approved public pretrained model, use
[assets/pbs/acquire-model-copyq.pbs](assets/pbs/acquire-model-copyq.pbs). Pin an immutable source
commit and license, download only on `copyq`, remove transient client metadata in jobfs, and invoke
`pack_data.sh --kind model`. Publish exactly one archive in `Data/models`; expand it only into the
consumer job's `$PBS_JOBFS`. Never use a branch/tag revision or publish an expanded Hugging Face
snapshot.

## Run and Monitor

Inside jobs, keep transient caches local:

```bash
export TMPDIR="$PBS_JOBFS/tmp"
export XDG_CACHE_HOME="$PBS_JOBFS/cache/xdg"
export HF_HOME="$PBS_JOBFS/cache/huggingface"
export TORCH_HOME="$PBS_JOBFS/cache/torch"
export PIP_CACHE_DIR="$PBS_JOBFS/cache/pip"
mkdir -p "$TMPDIR" "$XDG_CACHE_HOME" "$HF_HOME" "$TORCH_HOME" "$PIP_CACHE_DIR"
```

Write durable checkpoints and final output outside `.codex`, under a user-approved result directory passed explicitly to `run_sqsh.sh --write-path`. Use rolling checkpoint retention and consolidate per-sample/per-rank logs to bound inode growth.

Use `qstat -swx`, `qstat -fx`, `nqstat_anu`, `qps_gpu`, `qcat`, `qls`, and `qcp` for diagnosis. Poll PBS no more frequently than about once every ten minutes. Read [references/operations-troubleshooting.md](references/operations-troubleshooting.md) for held jobs, mount failures, OOM/jobfs failures, CUDA checks, and checkpoint chains.

## Final Safety Check

Before a write-heavy or charged operation, confirm:

- Current block and inode usage for `wa66`
- Current available KSU for the eligible compute project
- Expanded environments, caches, and extracted data resolve inside `$PBS_JOBFS`
- No workload output resolves under `/g/data/wa66/Xiangyu/.codex`
- Persistent data, environment images, and results use their designated roots
- PBS stdout/stderr is joined and sent to a pre-existing result/log directory, not HOME
- `storage=` covers every referenced project filesystem
- Network work runs on `copyq`
- The PBS script passes `lint_pbs.py`
- Submission cost and destructive actions are visible to the user
