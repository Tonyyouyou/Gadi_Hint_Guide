# Gadi Site Profile

Verified locally on 2026-08-12.

## Persistent Paths

| Purpose | Path |
|---|---|
| Persistent root | `/g/data/wa66/Xiangyu` |
| Frozen environments | `/g/data/wa66/Xiangyu/enviroment_cache` |
| Data and packed datasets | `/g/data/wa66/Xiangyu/Data` |
| Approved packed public models | `/g/data/wa66/Xiangyu/Data/models` |
| Existing general cache root | `/g/data/wa66/Xiangyu/cache` |
| Codex-only root | `/g/data/wa66/Xiangyu/.codex` |

The spelling `enviroment_cache` is intentional and matches the existing directory. Do not create a second `environment_cache` tree.

`/g/data/wa66/Xiangyu/.codex` is not a general persistent root. It is reserved for Codex configuration, installed skills, and skill source repositories. Workload data, models, environments, caches, checkpoints, logs, and results must never be placed there.

Do not use the persistent cache root for expanded package or model caches. Point `HF_HOME`, `XDG_CACHE_HOME`, `TORCH_HOME`, `PIP_CACHE_DIR`, and `CONDA_PKGS_DIRS` to `$PBS_JOBFS` while jobs run. Persist only deliberate packed artifacts.

## Authorised Projects

The account currently belongs to these four compute projects:

- `wa66`
- `ey69`
- `po67`
- `iv96`

Membership, quarterly KSU, block quota, and inode quota are dynamic. Query them at the start of each task:

```bash
id -nG
nci_account -P wa66
nci_account -P ey69
nci_account -P po67
nci_account -P iv96
```

Use `scripts/probe_gadi.py` for a combined report. Do not store observed balances in generated PBS scripts or documentation.

The charging project and storage project serve different purposes. A job may legitimately use `#PBS -P po67` while mounting `#PBS -l storage=gdata/wa66`. Use another project's compute allocation only when the task belongs to that project or the user confirms that it is an eligible allocation.

## File-Count Constraint

NCI reports both byte and inode usage. Treat either limit as capable of stopping the project. In particular:

- Conda environments commonly contain tens of thousands of files.
- Hugging Face, pip, Torch, npm, and compiler caches can grow silently.
- Audio and vision datasets can consume an inode per sample.
- Repeated checkpoints and per-sample logs can exhaust quota even when byte usage is modest.

The safe default is one persistent file per environment, one archive or a modest number of coarse shards per dataset, one archive per approved public model, and bounded checkpoint retention.

## Local Software Snapshot

Observed on `gadi-login-08` on 2026-08-12:

- CUDA modules were available through 12.9.
- `pytorch/2.12.0` loaded Python 3.11.7, CUDA 12.8, cuDNN 9.5, NCCL 2.27.5, and Open MPI 5.0.5.
- Singularity was available as the unversioned `singularity` module.
- `mksquashfs` 4.3 supported the options used by the environment builder.
- The `gpuhopper` route and execution queues were active.

This is a dated observation, not a version pin. Run `module avail` and `module show` again for each new environment or compatibility decision.
