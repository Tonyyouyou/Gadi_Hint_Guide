#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  persistent_session.sh --project PROJECT --name NAME [--start]

Preview is the default. --start creates one NCI persistent session after the
user approves the displayed project, name, and command. This helper does not
parse list output or terminate sessions.
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

PROJECT=
NAME=
START=0
while (($#)); do
  case "$1" in
    --project) PROJECT=${2:?}; shift 2 ;;
    --name) NAME=${2:?}; shift 2 ;;
    --start) START=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

case "$PROJECT" in
  wa66|ey69|po67|iv96) ;;
  "") die "--project is required" ;;
  *) die "project must be one of wa66, ey69, po67, iv96" ;;
esac
[[ "$NAME" =~ ^[a-z]([a-z0-9-]{0,61}[a-z0-9])?$ ]] || \
  die "name must be a DNS-safe lowercase label of at most 63 characters"
[[ -z "${PBS_JOBID:-}" ]] || die "do not manage persistent sessions from inside PBS"

HOST=$(hostname -f)
case "$HOST" in
  gadi-login-*.gadi.nci.org.au) ;;
  *) die "run this helper on a Gadi login node, got $HOST" ;;
esac

GROUPS_TEXT=" $(id -nG) "
case "$GROUPS_TEXT" in
  *" $PROJECT "*) ;;
  *) die "current account is not a member of $PROJECT" ;;
esac

BIN=$(command -v persistent-sessions || true)
[[ -n "$BIN" ]] || die "persistent-sessions is unavailable"
COMMAND=("$BIN" start -p "$PROJECT" "$NAME")
printf -v DISPLAY '%q ' "${COMMAND[@]}"
DISPLAY=${DISPLAY% }

echo "Persistent-session preview"
echo "  Login host: $HOST"
echo "  Project:    $PROJECT"
echo "  Name:       $NAME"
echo "  Expected:   $NAME.${USER}.${PROJECT}.ps.gadi.nci.org.au"
echo "  Command:    $DISPLAY"
echo
echo "The session may run only lightweight workflow-control processes."
echo "Do not compute, download data, or poll PBS more than once per ten minutes there."

if ((START == 0)); then
  echo
  echo "Preview only: no persistent session was created."
  exit 0
fi

echo
echo "Creating persistent session:"
"${COMMAND[@]}"
echo
echo "Record the returned UUID and hostname. Do not parse persistent-sessions list in automation."
