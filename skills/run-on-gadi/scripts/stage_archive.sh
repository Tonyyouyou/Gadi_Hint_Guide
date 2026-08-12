#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  stage_archive.sh [--strip-components N] [--member-list FILE] ARCHIVE DEST

DEST must be an empty directory beneath $PBS_JOBFS. Supported inputs are
.tar, .tar.gz/.tgz, and .tar.zst/.tzst.
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

STRIP=0
MEMBER_LIST=
while (($#)); do
  case "$1" in
    --strip-components) STRIP=${2:?}; shift 2 ;;
    --member-list) MEMBER_LIST=${2:?}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    --) shift; break ;;
    -*) die "unknown option: $1" ;;
    *) break ;;
  esac
done

[[ $# -eq 2 ]] || { usage; exit 2; }
ARCHIVE=$1
DEST=$2
[[ "$STRIP" =~ ^[0-9]+$ ]] || die "--strip-components must be a non-negative integer"
[[ -f "$ARCHIVE" ]] || die "archive not found: $ARCHIVE"
[[ -z "$MEMBER_LIST" || -f "$MEMBER_LIST" ]] || die "member list not found: $MEMBER_LIST"
[[ -n "${PBS_JOBFS:-}" && -d "$PBS_JOBFS" ]] || die "run inside a PBS job with jobfs"

case "$ARCHIVE" in
  *.tar.zst|*.tzst) command -v zstd >/dev/null 2>&1 || die "zstd is unavailable" ;;
  *.tar.gz|*.tgz) command -v gzip >/dev/null 2>&1 || die "gzip is unavailable" ;;
  *.tar) ;;
  *) die "unsupported archive extension: $ARCHIVE" ;;
esac

stream_archive() {
  case "$ARCHIVE" in
    *.tar.zst|*.tzst) zstd --quiet --decompress --stdout -- "$ARCHIVE" ;;
    *.tar.gz|*.tgz) gzip --decompress --stdout -- "$ARCHIVE" ;;
    *.tar) command cat -- "$ARCHIVE" ;;
  esac
}

JOBFS_REAL=$(realpath -e "$PBS_JOBFS")
DEST_CANDIDATE=$(realpath -m "$DEST")
case "$DEST_CANDIDATE" in
  "$JOBFS_REAL"/*) ;;
  *) die "destination must be beneath $JOBFS_REAL, got $DEST_CANDIDATE" ;;
esac
mkdir -p "$DEST_CANDIDATE"
DEST_REAL=$(realpath -e "$DEST")
case "$DEST_REAL" in
  "$JOBFS_REAL"/*) ;;
  *) die "destination must resolve beneath $JOBFS_REAL, got $DEST_REAL" ;;
esac
if find "$DEST_REAL" -mindepth 1 -print -quit | grep -q .; then
  die "destination must be empty: $DEST_REAL"
fi

LIST=$JOBFS_REAL/.run-on-gadi-archive-list.$$
trap 'rm -f "$LIST"' EXIT
stream_archive | tar --list --file=- >"$LIST"

if awk '$0 ~ /^\// || $0 ~ /(^|\/)\.\.($|\/)/ { bad=1 } END { exit bad ? 0 : 1 }' "$LIST"; then
  die "archive contains an absolute or parent-traversal path"
fi
if [[ -n "$MEMBER_LIST" ]] &&
   awk '$0 ~ /^\// || $0 ~ /(^|\/)\.\.($|\/)/ { bad=1 } END { exit bad ? 0 : 1 }' "$MEMBER_LIST"; then
  die "member list contains an absolute or parent-traversal path"
fi

TAR_ARGS=(--extract --file=- --directory="$DEST_REAL" --no-same-owner --no-same-permissions)
if ((STRIP > 0)); then
  TAR_ARGS+=(--strip-components="$STRIP")
fi
if [[ -n "$MEMBER_LIST" ]]; then
  TAR_ARGS+=(--files-from="$MEMBER_LIST")
fi
stream_archive | tar "${TAR_ARGS[@]}"

FILES=$(find "$DEST_REAL" -xdev -type f -printf x | wc -c)
BYTES=$(du -sb "$DEST_REAL" | awk '{print $1}')
echo "Staged $FILES files and $BYTES bytes into $DEST_REAL"
