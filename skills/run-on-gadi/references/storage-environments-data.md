# Storage, Environments, and Data

## Storage Roles

### `$HOME`

Keep small source trees and shell configuration here. HOME has a 10 GiB quota. Do not add conda environments or large caches without checking `quota -s`.

### `/g/data/wa66/Xiangyu/.codex`

Use only for Codex configuration, skills, and their source repositories. Never use it for scientific/ML workloads or generated artifacts.

### `/g/data/wa66/Xiangyu`

Use designated subdirectories for durable compact artifacts:

- `enviroment_cache/*.sqsh` for frozen environments
- `Data/` for packed datasets and manifests
- Existing `Result*` directories or a user-approved task directory for results

Gdata has both byte and inode quotas. Persist final forms, not build trees.

### `/scratch/<project>`

Scratch is temporary and inode-limited. Do not use it as an expanded conda or dataset workaround. Use it only for a small number of large intermediates requiring cross-job persistence.

### `$PBS_JOBFS`

Use for expanded environments, package caches, builds, downloads, dataset extraction, and runtime caches. It is node-local and deleted after the job.

For multi-node jobs, PBS distributes requested jobfs across nodes. Do not assume one node can see another node's local files.

## Environment Build Workflow

Use a `copyq` job for dependency resolution and downloads. Redirect all transient paths:

```bash
export CONDA_PKGS_DIRS="$PBS_JOBFS/cache/conda-pkgs"
export PIP_CACHE_DIR="$PBS_JOBFS/cache/pip"
export XDG_CACHE_HOME="$PBS_JOBFS/cache/xdg"
export HF_HOME="$PBS_JOBFS/cache/huggingface"
export TORCH_HOME="$PBS_JOBFS/cache/torch"
export TMPDIR="$PBS_JOBFS/tmp"
```

Run `scripts/build_conda_sqsh.sh`. It creates the conda prefix in jobfs, applies `conda-pack --dest-prefix /env`, includes package manifests, builds a minimal Singularity-compatible root, tests it, then atomically publishes:

```text
/g/data/wa66/Xiangyu/enviroment_cache/<name>-<timestamp>.sqsh
```

Examples:

```bash
build_conda_sqsh.sh --name speech --environment environment.yml
build_conda_sqsh.sh --name inference --python 3.11 --requirements requirements.txt
```

An optional `--post-install script.sh` runs after environment creation with `GADI_ENV_PREFIX` set. The script must keep build output and caches in jobfs.

`copyq` currently allows one CPU and 200 GB jobfs. For a CPU-heavy offline build, first download a small number of package/source archives on `copyq`, then build them from jobfs in a compute job.

## Container Runtime

Use `scripts/run_sqsh.sh`. It selects `/env`, disables user site packages, redirects runtime caches to jobfs, disables the automatic writable working-directory mount, and mounts HOME, gdata, and scratch read-only by default. Only an existing result directory named with `--write-path` becomes writable:

```bash
run_sqsh.sh image.sqsh /env/bin/python /absolute/path/script.py
run_sqsh.sh --nv --write-path "$RESULT_DIR" image.sqsh \
  /env/bin/python /absolute/path/train.py --output-dir "$RESULT_DIR"
```

Images are read-only. Build a dated replacement to add packages. Keep the previous working image until a real workload succeeds with the replacement.

The runner refuses to make `.codex`, `Data`, or `enviroment_cache` writable. Publish datasets with `pack_data.sh`; this prevents a training process or later agent from silently expanding files into those protected trees.

Gadi's Singularity configuration injects project-specific filesystem mounts. A read-only bind of only the parent `/g/data` or `/scratch` is therefore insufficient. The runner explicitly overlays the four authorised project roots and the account's real HOME as read-only, then overlays only each approved `--write-path` as writable. This behavior was smoke-tested locally with the existing `fairseq-20260514.sqsh` image.

For CUDA environments, use a short target-queue job to import the framework, report its CUDA build, allocate a GPU tensor, and execute a small operation.

## Data Acquisition Workflow

Never point a downloader directly at gdata if it creates an expanded tree.

1. Use `assets/pbs/acquire-data-copyq.pbs`.
2. Download into `$PBS_JOBFS/download/<dataset>`.
3. Verify checksum, source version, license, sample count, and expected size.
4. Convert excessive small files to a streamable format where practical.
5. Use `scripts/pack_data.sh` to publish one `.tar.zst` or a controlled shard set in `/g/data/wa66/Xiangyu/Data`.
6. Test the archive before jobfs disappears.

Use `pack_data.sh --dry-run` to exercise counting, compression, archive validation, and hashing without creating a persistent file.

At runtime, stream archive/shard formats when supported. Otherwise use:

```bash
stage_archive.sh dataset.tar.zst "$PBS_JOBFS/datasets/dataset"
```

Update manifests and TSV roots to point at jobfs.

## Oversized Datasets

When expanded data exceeds node-local jobfs:

- Partition deterministically.
- Process one partition at a time in jobfs.
- Publish coarse shards atomically, normally several GiB each.
- Keep one manifest containing shard names, checksums, sample counts, and source version.
- Resume only from completed shards.

Do not extract the whole dataset to scratch or gdata. If a consumer requires millions of files, stage only its current working subset or change the data pipeline.

## Results and Checkpoints

Write checkpoints to a user-approved result directory outside `.codex`, because jobfs disappears. Bound file count:

- Keep `last`, a small recent window, and selected best checkpoints.
- Consolidate per-rank and per-sample logs.
- Archive completed runs containing many small files.
- Never delete an earlier image/checkpoint without explicit approval and a validated replacement.
