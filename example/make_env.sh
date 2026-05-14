#!/usr/bin/env bash
set -euo pipefail

module load singularity
source /home/561/xz4320/miniconda3/etc/profile.d/conda.sh

ENV_NAME=${ENV_NAME:-fairseq}
TAG=${TAG:-$(date +%Y%m%d)}
CONDA_ROOT=/home/561/xz4320/miniconda3
ENV_PREFIX=$CONDA_ROOT/envs/$ENV_NAME

OUTDIR=/g/data/wa66/Xiangyu/enviroment_cache
OUT=$OUTDIR/${ENV_NAME}-${TAG}.sqsh
TMP_OUT=$OUT.tmp.$$
REUSE_ROOT=${REUSE_ROOT:-0}

if [[ -z "${PBS_JOBFS:-}" ]]; then
  echo "ERROR: PBS_JOBFS is not set. Run this inside an interactive/PBS job with jobfs=200GB." >&2
  echo "Example: bash /home/561/xz4320/interactive_cpu.sh, then bash /home/561/xz4320/make_env.sh" >&2
  exit 1
fi

BUILD=$PBS_JOBFS/conda-sqsh-build/${ENV_NAME}-${TAG}
ROOT=$BUILD/root
TAR=$BUILD/${ENV_NAME}.tar.gz
BIND_PATHS=/usr:/usr,/etc:/etc,/half-root:/half-root
SUCCESS=0

cleanup() {
  if [[ "$SUCCESS" == 1 ]]; then
    rm -rf "$BUILD" "$TMP_OUT"
  else
    echo "Build failed or was interrupted; keeping temporary files for inspection: $BUILD" >&2
    rm -f "$TMP_OUT"
  fi
}
trap cleanup EXIT

mkdir -p "$OUTDIR"

if [[ "$REUSE_ROOT" == 1 && -x "$ROOT/env/bin/python" ]]; then
  echo "Reusing existing unpacked environment under PBS_JOBFS: $ROOT/env"
else
  rm -rf "$BUILD"
  mkdir -p "$ROOT/env"
fi

mkdir -p "$ROOT"/{usr/bin,usr/lib,usr/lib64,usr/sbin,etc,tmp,var/tmp,home,g,scratch,jobfs,apps,opt/nci,proc,sys,dev,half-root}
chmod 1777 "$ROOT/tmp" "$ROOT/var/tmp"

[[ -e "$ROOT/bin" ]] || ln -s usr/bin "$ROOT/bin"
[[ -e "$ROOT/lib" ]] || ln -s usr/lib "$ROOT/lib"
[[ -e "$ROOT/lib64" ]] || ln -s usr/lib64 "$ROOT/lib64"
[[ -e "$ROOT/sbin" ]] || ln -s usr/sbin "$ROOT/sbin"

touch "$ROOT/etc/passwd" "$ROOT/etc/group" "$ROOT/etc/hosts" "$ROOT/etc/resolv.conf"

if [[ "$REUSE_ROOT" == 1 && -x "$ROOT/env/bin/python" ]]; then
  echo "Skipping conda-pack/extract because REUSE_ROOT=1"
else
  echo "Packing conda environment: $ENV_PREFIX"
  conda-pack \
    -p "$ENV_PREFIX" \
    --dest-prefix /env \
    -o "$TAR" \
    --force

  echo "Extracting packed environment under PBS_JOBFS: $ROOT/env"
  tar -xzf "$TAR" -C "$ROOT/env"
  rm -f "$TAR"
fi

echo "Creating SquashFS image: $TMP_OUT"
rm -f "$TMP_OUT" "$OUT"
mksquashfs "$ROOT" "$TMP_OUT" \
  -noappend \
  -comp xz \
  -processors "${NCPUS:-${PBS_NCPUS:-2}}" \
  -mem 8G \
  -no-xattrs \
  -no-progress

echo "Testing image"
singularity exec \
  --cleanenv \
  --bind "$BIND_PATHS" \
  --env LD_LIBRARY_PATH=/env/lib:/lib64:/usr/lib64 \
  "$TMP_OUT" \
  /env/bin/python -c 'import sys; print(sys.executable); print(sys.version)'

mv -f "$TMP_OUT" "$OUT"
ls -lh "$OUT"
SUCCESS=1
