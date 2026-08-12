#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  build_conda_sqsh.sh --name NAME [--environment FILE] [--requirements FILE]
                       [--python VERSION] [--post-install SCRIPT]
                       [--tag TAG] [--conda PATH]

Run inside PBS. Expanded files and caches stay in $PBS_JOBFS. The only
persistent output is one dated .sqsh in the environment cache.
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

NAME=
ENVIRONMENT=
REQUIREMENTS=
PYTHON_VERSION=3.11
POST_INSTALL=
TAG=$(date -u +%Y%m%dT%H%M%SZ)
CONDA_BIN=${CONDA_EXE:-}

while (($#)); do
  case "$1" in
    --name) NAME=${2:?}; shift 2 ;;
    --environment) ENVIRONMENT=${2:?}; shift 2 ;;
    --requirements) REQUIREMENTS=${2:?}; shift 2 ;;
    --python) PYTHON_VERSION=${2:?}; shift 2 ;;
    --post-install) POST_INSTALL=${2:?}; shift 2 ;;
    --tag) TAG=${2:?}; shift 2 ;;
    --conda) CONDA_BIN=${2:?}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[[ -n "$NAME" ]] || die "--name is required"
[[ "$NAME" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die "unsafe environment name: $NAME"
[[ "$TAG" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die "unsafe tag: $TAG"
[[ -n "${PBS_JOBFS:-}" && -d "$PBS_JOBFS" ]] || die "run inside a PBS job with jobfs"
[[ -z "$ENVIRONMENT" || -f "$ENVIRONMENT" ]] || die "environment file not found: $ENVIRONMENT"
[[ -z "$REQUIREMENTS" || -f "$REQUIREMENTS" ]] || die "requirements file not found: $REQUIREMENTS"
[[ -z "$POST_INSTALL" || -f "$POST_INSTALL" ]] || die "post-install script not found: $POST_INSTALL"

if [[ -z "$CONDA_BIN" ]]; then
  CONDA_BIN=$(command -v conda || true)
fi
[[ -n "$CONDA_BIN" && -x "$CONDA_BIN" ]] || die "conda not found; pass --conda /path/to/conda"
command -v singularity >/dev/null 2>&1 || die "load the singularity module first"
command -v mksquashfs >/dev/null 2>&1 || die "mksquashfs is unavailable"
command -v sha256sum >/dev/null 2>&1 || die "sha256sum is unavailable"

PERSISTENT_ROOT=/g/data/wa66/Xiangyu
CODEX_ROOT=$PERSISTENT_ROOT/.codex
OUTDIR=$PERSISTENT_ROOT/enviroment_cache
OUT=$OUTDIR/${NAME}-${TAG}.sqsh
PARTIAL=$OUTDIR/.${NAME}-${TAG}.sqsh.partial.${PBS_JOBID:-nojob}.$$
BUILD=$PBS_JOBFS/run-on-gadi-env-${NAME}-${TAG}
ENV_PREFIX=$BUILD/conda-env
ROOT=$BUILD/root
PACKED=$BUILD/environment.tar.gz
LOCAL_IMAGE=$BUILD/${NAME}-${TAG}.sqsh
SUCCESS=0

case "$OUT" in
  "$CODEX_ROOT"/*) die "refusing to publish a workload artifact under $CODEX_ROOT" ;;
  "$OUTDIR"/*.sqsh) ;;
  *) die "unexpected output path: $OUT" ;;
esac
[[ ! -e "$OUT" ]] || die "output already exists: $OUT"

cleanup() {
  rm -f "$PARTIAL"
  if [[ "$SUCCESS" == 1 ]]; then
    rm -rf "$BUILD"
  else
    echo "Build files kept for inspection until PBS cleanup: $BUILD" >&2
  fi
}
trap cleanup EXIT

export HOME=$BUILD/home
export TMPDIR=$BUILD/tmp
export CONDARC=$BUILD/condarc
export CONDA_ENVS_PATH=$BUILD/conda-envs
export CONDA_PKGS_DIRS=$BUILD/cache/conda-pkgs
export PIP_CACHE_DIR=$BUILD/cache/pip
export XDG_CACHE_HOME=$BUILD/cache/xdg
export XDG_CONFIG_HOME=$BUILD/config/xdg
export XDG_DATA_HOME=$BUILD/data/xdg
export HF_HOME=$BUILD/cache/huggingface
export HUGGINGFACE_HUB_CACHE=$HF_HOME/hub
export HF_DATASETS_CACHE=$HF_HOME/datasets
export TRANSFORMERS_CACHE=$HF_HOME/transformers
export TORCH_HOME=$BUILD/cache/torch
export TORCH_EXTENSIONS_DIR=$BUILD/cache/torch-extensions
export TORCHINDUCTOR_CACHE_DIR=$BUILD/cache/torch-inductor
export TRITON_CACHE_DIR=$BUILD/cache/triton
export CUDA_CACHE_PATH=$BUILD/cache/cuda
export JAX_COMPILATION_CACHE_DIR=$BUILD/cache/jax
export NUMBA_CACHE_DIR=$BUILD/cache/numba
export MPLCONFIGDIR=$BUILD/cache/matplotlib
export WANDB_DIR=$BUILD/cache/wandb
export UV_CACHE_DIR=$BUILD/cache/uv
export NPM_CONFIG_CACHE=$BUILD/cache/npm
export CARGO_HOME=$BUILD/cache/cargo
export RUSTUP_HOME=$BUILD/cache/rustup
export APPTAINER_CACHEDIR=$BUILD/cache/apptainer
export APPTAINER_TMPDIR=$TMPDIR
export SINGULARITY_CACHEDIR=$BUILD/cache/apptainer
export SINGULARITY_TMPDIR=$TMPDIR
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PYTHONNOUSERSITE=1

mkdir -p \
  "$HOME" "$TMPDIR" "$CONDA_ENVS_PATH" "$CONDA_PKGS_DIRS" \
  "$PIP_CACHE_DIR" "$XDG_CACHE_HOME" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" \
  "$HUGGINGFACE_HUB_CACHE" "$HF_DATASETS_CACHE" "$TRANSFORMERS_CACHE" \
  "$TORCH_HOME" "$TORCH_EXTENSIONS_DIR" "$TORCHINDUCTOR_CACHE_DIR" \
  "$TRITON_CACHE_DIR" "$CUDA_CACHE_PATH" "$JAX_COMPILATION_CACHE_DIR" \
  "$NUMBA_CACHE_DIR" "$MPLCONFIGDIR" "$WANDB_DIR" "$UV_CACHE_DIR" \
  "$NPM_CONFIG_CACHE" "$CARGO_HOME" "$RUSTUP_HOME" "$APPTAINER_CACHEDIR" \
  "$ROOT/env" "$OUTDIR"

cat >"$CONDARC" <<EOF
pkgs_dirs:
  - $CONDA_PKGS_DIRS
envs_dirs:
  - $CONDA_ENVS_PATH
auto_activate_base: false
EOF

echo "Current wa66 storage and inode status:"
nci_account -P wa66 || true

if [[ -n "$ENVIRONMENT" ]]; then
  "$CONDA_BIN" env create --yes --prefix "$ENV_PREFIX" --file "$ENVIRONMENT"
else
  "$CONDA_BIN" create --yes --prefix "$ENV_PREFIX" "python=$PYTHON_VERSION" pip
fi

[[ -x "$ENV_PREFIX/bin/python" ]] || die "the environment must include Python"
if ! "$ENV_PREFIX/bin/python" -m pip --version >/dev/null 2>&1; then
  "$CONDA_BIN" install --yes --prefix "$ENV_PREFIX" pip
fi

if [[ -n "$REQUIREMENTS" ]]; then
  "$ENV_PREFIX/bin/python" -m pip install --requirement "$REQUIREMENTS"
fi

if [[ ! -x "$ENV_PREFIX/bin/conda-pack" ]]; then
  "$ENV_PREFIX/bin/python" -m pip install --no-cache-dir conda-pack
fi

if [[ -n "$POST_INSTALL" ]]; then
  export GADI_ENV_PREFIX=$ENV_PREFIX
  export PATH=$ENV_PREFIX/bin:$PATH
  bash "$POST_INSTALL"
fi

"$CONDA_BIN" list --prefix "$ENV_PREFIX" --explicit >"$BUILD/conda-explicit.txt"
"$ENV_PREFIX/bin/python" -m pip freeze --all >"$BUILD/pip-freeze.txt"

"$ENV_PREFIX/bin/conda-pack" \
  --prefix "$ENV_PREFIX" \
  --dest-prefix /env \
  --output "$PACKED" \
  --force

tar -xzf "$PACKED" -C "$ROOT/env"
rm -f "$PACKED"

mkdir -p "$ROOT"/{usr/bin,usr/lib,usr/lib64,usr/sbin,etc,tmp,var/tmp,home,g/data,scratch,jobfs,apps,opt/nci,proc,sys,dev,half-root,metadata}
chmod 1777 "$ROOT/tmp" "$ROOT/var/tmp"
ln -s usr/bin "$ROOT/bin"
ln -s usr/lib "$ROOT/lib"
ln -s usr/lib64 "$ROOT/lib64"
ln -s usr/sbin "$ROOT/sbin"
touch "$ROOT/etc/passwd" "$ROOT/etc/group" "$ROOT/etc/hosts" "$ROOT/etc/resolv.conf"
cp "$BUILD/conda-explicit.txt" "$BUILD/pip-freeze.txt" "$ROOT/metadata/"

mksquashfs "$ROOT" "$LOCAL_IMAGE" \
  -noappend \
  -comp xz \
  -processors "${PBS_NCPUS:-1}" \
  -mem 4G \
  -no-xattrs \
  -no-progress

singularity exec \
  --cleanenv \
  --home "$HOME:$HOME" \
  --no-mount cwd \
  --pwd "$BUILD" \
  --bind "$PBS_JOBFS:$PBS_JOBFS:rw" \
  --bind /usr:/usr:ro,/etc:/etc:ro,/half-root:/half-root:ro \
  --env PATH=/env/bin:/usr/local/bin:/usr/bin:/bin \
  --env LD_LIBRARY_PATH=/env/lib:/lib64:/usr/lib64 \
  --env PYTHONNOUSERSITE=1 \
  "$LOCAL_IMAGE" \
  /env/bin/python -c 'import sys; print(sys.executable); print(sys.version)'

LOCAL_SHA=$(sha256sum "$LOCAL_IMAGE" | awk '{print $1}')
cp "$LOCAL_IMAGE" "$PARTIAL"
PERSISTENT_SHA=$(sha256sum "$PARTIAL" | awk '{print $1}')
[[ "$PERSISTENT_SHA" == "$LOCAL_SHA" ]] || die "checksum changed while copying to gdata"
mv --no-clobber "$PARTIAL" "$OUT"
[[ ! -e "$PARTIAL" ]] || die "output appeared during publication; refusing to overwrite it"
printf '%s  %s\n' "$LOCAL_SHA" "$OUT"
ls -lh "$OUT"
SUCCESS=1
