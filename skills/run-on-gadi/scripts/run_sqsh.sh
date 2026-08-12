#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  run_sqsh.sh [--nv] [--write-path DIR] IMAGE.sqsh COMMAND [ARG ...]

Persistent filesystems are read-only inside the container by default.
Repeat --write-path for each existing, explicitly approved result directory.
Data, environment-cache, and Codex directories can never be made writable.
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

USE_NV=0
WRITE_PATHS=()
while (($#)); do
  case "$1" in
    --nv)
      USE_NV=1
      shift
      ;;
    --write-path)
      [[ $# -ge 2 ]] || die "--write-path requires a directory"
      WRITE_PATHS+=("$2")
      shift 2
      ;;
    --)
      shift
      break
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      die "unknown option: $1"
      ;;
    *)
      break
      ;;
  esac
done

[[ $# -ge 2 ]] || { usage; exit 2; }
IMAGE=$1
shift
[[ -f "$IMAGE" ]] || die "image not found: $IMAGE"
[[ -n "${PBS_JOBFS:-}" && -d "$PBS_JOBFS" ]] || \
  die "run inside PBS with jobfs so caches cannot spill to HOME or gdata"
command -v singularity >/dev/null 2>&1 || die "load the singularity module first"

PERSISTENT_ROOT=/g/data/wa66/Xiangyu
CODEX_ROOT=$PERSISTENT_ROOT/.codex
ENV_ROOT=$PERSISTENT_ROOT/enviroment_cache
DATA_ROOT=$PERSISTENT_ROOT/Data
JOBFS_REAL=$(realpath -e "$PBS_JOBFS")
HOST_HOME_REAL=$(realpath -e "$HOME")
RUNTIME=$JOBFS_REAL/run-on-gadi-runtime

mkdir -p \
  "$RUNTIME"/{home,tmp,work,cache/apptainer,cache/xdg,cache/huggingface,cache/torch} \
  "$RUNTIME"/{cache/pip,cache/triton,cache/torch-extensions,cache/torch-inductor} \
  "$RUNTIME"/{cache/cuda,cache/jax,cache/numba,cache/matplotlib} \
  "$RUNTIME"/{cache/uv,cache/npm,cache/cargo,cache/rustup,config/xdg,data/xdg,wandb}

export APPTAINER_CACHEDIR=$RUNTIME/cache/apptainer
export APPTAINER_TMPDIR=$RUNTIME/tmp
export SINGULARITY_CACHEDIR=$RUNTIME/cache/apptainer
export SINGULARITY_TMPDIR=$RUNTIME/tmp

BIND_SPECS=()
for host_path in /usr /etc /home /g/data /scratch /apps /opt/nci /half-root; do
  if [[ -e "$host_path" ]]; then
    BIND_SPECS+=("$host_path:$host_path:ro")
  fi
done
for host_path in \
  "$HOST_HOME_REAL" \
  /g/data/wa66 /g/data/ey69 /g/data/po67 /g/data/iv96 \
  /scratch/wa66 /scratch/ey69 /scratch/po67 /scratch/iv96 \
  "$PERSISTENT_ROOT" "$CODEX_ROOT" "$ENV_ROOT" "$DATA_ROOT"; do
  if [[ -e "$host_path" ]]; then
    BIND_SPECS+=("$host_path:$host_path:ro")
  fi
done
BIND_SPECS+=(
  "$JOBFS_REAL:$JOBFS_REAL:rw"
  "$RUNTIME/tmp:/tmp:rw"
  "$RUNTIME/tmp:/var/tmp:rw"
)

for requested in "${WRITE_PATHS[@]}"; do
  [[ -d "$requested" ]] || die "write path must already exist: $requested"
  resolved=$(realpath -e "$requested")
  case "$resolved" in
    "$PERSISTENT_ROOT")
      die "refusing to make the entire persistent root writable"
      ;;
    "$CODEX_ROOT"|"$CODEX_ROOT"/*)
      die "Codex-only path can never be a workload write path: $resolved"
      ;;
    "$ENV_ROOT"|"$ENV_ROOT"/*)
      die "frozen environments are immutable: $resolved"
      ;;
    "$DATA_ROOT"|"$DATA_ROOT"/*)
      die "publish data with pack_data.sh instead of direct container writes"
      ;;
    "$PERSISTENT_ROOT"/*)
      BIND_SPECS+=("$resolved:$resolved:rw")
      ;;
    *)
      die "write paths must be approved directories under $PERSISTENT_ROOT"
      ;;
  esac
done

ARGS=(
  exec
  --cleanenv
  --home "$RUNTIME/home:$RUNTIME/home"
  --no-mount cwd
  --pwd "$RUNTIME/work"
)
if [[ "$USE_NV" == 1 ]]; then
  ARGS+=(--nv)
fi
for spec in "${BIND_SPECS[@]}"; do
  ARGS+=(--bind "$spec")
done
ARGS+=(
  --env PATH=/env/bin:/usr/local/bin:/usr/bin:/bin
  --env LD_LIBRARY_PATH=/env/lib:/.singularity.d/libs:/lib64:/usr/lib64
  --env CONDA_PREFIX=/env
  --env VIRTUAL_ENV=/env
  --env "TMPDIR=$RUNTIME/tmp"
  --env "XDG_CACHE_HOME=$RUNTIME/cache/xdg"
  --env "XDG_CONFIG_HOME=$RUNTIME/config/xdg"
  --env "XDG_DATA_HOME=$RUNTIME/data/xdg"
  --env "HF_HOME=$RUNTIME/cache/huggingface"
  --env "HUGGINGFACE_HUB_CACHE=$RUNTIME/cache/huggingface/hub"
  --env "HF_DATASETS_CACHE=$RUNTIME/cache/huggingface/datasets"
  --env "TRANSFORMERS_CACHE=$RUNTIME/cache/huggingface/transformers"
  --env "TORCH_HOME=$RUNTIME/cache/torch"
  --env "PIP_CACHE_DIR=$RUNTIME/cache/pip"
  --env "TRITON_CACHE_DIR=$RUNTIME/cache/triton"
  --env "TORCH_EXTENSIONS_DIR=$RUNTIME/cache/torch-extensions"
  --env "TORCHINDUCTOR_CACHE_DIR=$RUNTIME/cache/torch-inductor"
  --env "CUDA_CACHE_PATH=$RUNTIME/cache/cuda"
  --env "JAX_COMPILATION_CACHE_DIR=$RUNTIME/cache/jax"
  --env "NUMBA_CACHE_DIR=$RUNTIME/cache/numba"
  --env "MPLCONFIGDIR=$RUNTIME/cache/matplotlib"
  --env "WANDB_DIR=$RUNTIME/wandb"
  --env "WANDB_CACHE_DIR=$RUNTIME/cache/wandb"
  --env "UV_CACHE_DIR=$RUNTIME/cache/uv"
  --env "NPM_CONFIG_CACHE=$RUNTIME/cache/npm"
  --env "CARGO_HOME=$RUNTIME/cache/cargo"
  --env "RUSTUP_HOME=$RUNTIME/cache/rustup"
  --env PYTHONNOUSERSITE=1
  --env PYTHONDONTWRITEBYTECODE=1
)

exec singularity "${ARGS[@]}" "$IMAGE" "$@"
