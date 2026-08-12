#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  pack_data.sh --name NAME --source PATH [--tag TAG] [--level 1..19] [--dry-run]

PATH must resolve beneath $PBS_JOBFS. The script validates one local
.tar.zst and atomically publishes it to /g/data/wa66/Xiangyu/Data.
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

NAME=
SOURCE=
TAG=$(date -u +%Y%m%dT%H%M%SZ)
LEVEL=10
DRY_RUN=0
while (($#)); do
  case "$1" in
    --name) NAME=${2:?}; shift 2 ;;
    --source) SOURCE=${2:?}; shift 2 ;;
    --tag) TAG=${2:?}; shift 2 ;;
    --level) LEVEL=${2:?}; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[[ "$NAME" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die "unsafe or missing dataset name"
[[ "$TAG" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die "unsafe tag"
[[ "$LEVEL" =~ ^[0-9]+$ ]] && ((LEVEL >= 1 && LEVEL <= 19)) || die "--level must be 1..19"
[[ -n "$SOURCE" && -e "$SOURCE" ]] || die "source not found: $SOURCE"
[[ -n "${PBS_JOBFS:-}" && -d "$PBS_JOBFS" ]] || die "run inside a PBS job with jobfs"
command -v realpath >/dev/null 2>&1 || die "realpath is unavailable"
command -v sha256sum >/dev/null 2>&1 || die "sha256sum is unavailable"
command -v tar >/dev/null 2>&1 || die "tar is unavailable"
command -v zstd >/dev/null 2>&1 || die "zstd is unavailable"

JOBFS_REAL=$(realpath -e "$PBS_JOBFS")
SOURCE_REAL=$(realpath -e "$SOURCE")
case "$SOURCE_REAL" in
  "$JOBFS_REAL"/*) ;;
  *) die "source must resolve beneath $JOBFS_REAL, got $SOURCE_REAL" ;;
esac

PERSISTENT_ROOT=/g/data/wa66/Xiangyu
CODEX_ROOT=$PERSISTENT_ROOT/.codex
OUTDIR=$PERSISTENT_ROOT/Data
OUT=$OUTDIR/${NAME}-${TAG}.tar.zst
PARTIAL=$OUTDIR/.${NAME}-${TAG}.tar.zst.partial.${PBS_JOBID:-nojob}.$$
BUILD=$JOBFS_REAL/run-on-gadi-pack-${NAME}-${TAG}
META_DIR=$BUILD/metadata
LOCAL=$BUILD/${NAME}-${TAG}.tar.zst

case "$OUT" in
  "$CODEX_ROOT"/*) die "refusing to publish beneath the Codex-only root" ;;
  "$OUTDIR"/*.tar.zst) ;;
  *) die "unexpected output path: $OUT" ;;
esac
[[ ! -e "$OUT" ]] || die "output already exists: $OUT"
trap 'rm -f "$PARTIAL"' EXIT

mkdir -p "$META_DIR" "$OUTDIR"
FILES=$(find "$SOURCE_REAL" -xdev -type f -printf x | wc -c)
DIRS=$(find "$SOURCE_REAL" -xdev -type d -printf x | wc -c)
SYMLINKS=$(find "$SOURCE_REAL" -xdev -type l -printf x | wc -c)
BYTES=$(du -sb "$SOURCE_REAL" | awk '{print $1}')
FILES=${FILES//[[:space:]]/}
DIRS=${DIRS//[[:space:]]/}
SYMLINKS=${SYMLINKS//[[:space:]]/}
CREATED=$(date -u +%Y-%m-%dT%H:%M:%SZ)

printf \
  '{"format":"run-on-gadi-data-v1","name":"%s","tag":"%s","created_utc":"%s","pbs_job_id":"%s","bytes":%s,"files":%s,"directories":%s,"symlinks":%s}\n' \
  "$NAME" "$TAG" "$CREATED" "${PBS_JOBID:-unknown}" \
  "$BYTES" "$FILES" "$DIRS" "$SYMLINKS" \
  >"$META_DIR/RUN_ON_GADI_MANIFEST.json"

echo "Current wa66 storage and inode status:"
nci_account -P wa66 || true
echo "Packing $FILES files, $DIRS directories, $BYTES bytes from jobfs"

PARENT=$(dirname "$SOURCE_REAL")
BASE=$(basename "$SOURCE_REAL")
THREADS=${PBS_NCPUS:-1}
tar --create --file=- --numeric-owner --owner=0 --group=0 \
  -C "$META_DIR" RUN_ON_GADI_MANIFEST.json \
  -C "$PARENT" "./$BASE" |
  zstd --quiet "-T$THREADS" "-$LEVEL" -o "$LOCAL"

zstd --quiet --test "$LOCAL"
zstd --quiet --decompress --stdout "$LOCAL" | tar --list --file=- >/dev/null
LOCAL_SHA=$(sha256sum "$LOCAL" | awk '{print $1}')

if [[ "$DRY_RUN" == 1 ]]; then
  echo "Dry run: validated local archive; no persistent file was written"
  printf '%s  %s\n' "$LOCAL_SHA" "$LOCAL"
  ls -lh "$LOCAL"
  exit 0
fi

cp "$LOCAL" "$PARTIAL"
PERSISTENT_SHA=$(sha256sum "$PARTIAL" | awk '{print $1}')
[[ "$PERSISTENT_SHA" == "$LOCAL_SHA" ]] || die "checksum changed while copying to gdata"
mv --no-clobber "$PARTIAL" "$OUT"
[[ ! -e "$PARTIAL" ]] || die "output appeared during publication; refusing to overwrite it"
printf '%s  %s\n' "$LOCAL_SHA" "$OUT"
ls -lh "$OUT"
