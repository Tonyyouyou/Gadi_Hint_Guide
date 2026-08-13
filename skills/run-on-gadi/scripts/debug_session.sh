#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  debug_session.sh --kind cpu|v100|a100|h200 --project PROJECT [options]

Preview is the default and never submits a job. After the user explicitly
approves the shown charge and qsub command, repeat with --start to create a
detached tmux session containing qsub -I.

Options:
  --walltime HH:MM:SS   Debug walltime, at most 04:00:00 (default 01:00:00)
  --mem-gb N            Override memory in whole GB
  --jobfs-gb N          Override jobfs in whole GB
  --session NAME        Unique tmux session name
  --persistent-control-host
                         Allow an NCI persistent-session control host whose
                         hostname does not match gadi-login-*
  --start               Start tmux and submit the interactive job
  -h, --help            Show this help
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

KIND=
PROJECT=
WALLTIME=01:00:00
MEM_GB=
JOBFS_GB=
SESSION=
START=0
PERSISTENT_CONTROL_HOST=0

while (($#)); do
  case "$1" in
    --kind) KIND=${2:?}; shift 2 ;;
    --project) PROJECT=${2:?}; shift 2 ;;
    --walltime) WALLTIME=${2:?}; shift 2 ;;
    --mem-gb) MEM_GB=${2:?}; shift 2 ;;
    --jobfs-gb) JOBFS_GB=${2:?}; shift 2 ;;
    --session) SESSION=${2:?}; shift 2 ;;
    --persistent-control-host) PERSISTENT_CONTROL_HOST=1; shift ;;
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

case "$KIND" in
  cpu)
    QUEUE=normal
    NCPUS=4
    NGPUS=0
    DEFAULT_MEM_GB=16
    DEFAULT_JOBFS_GB=50
    MAX_MEM_GB=190
    MAX_JOBFS_GB=400
    RATE=2
    MEM_PER_NODE_GB=190
    NCPUS_PER_NODE=48
    ;;
  v100)
    QUEUE=gpuvolta
    NCPUS=12
    NGPUS=1
    DEFAULT_MEM_GB=64
    DEFAULT_JOBFS_GB=100
    MAX_MEM_GB=382
    MAX_JOBFS_GB=400
    RATE=3
    MEM_PER_NODE_GB=382
    NCPUS_PER_NODE=48
    ;;
  a100)
    QUEUE=dgxa100
    NCPUS=16
    NGPUS=1
    DEFAULT_MEM_GB=128
    DEFAULT_JOBFS_GB=200
    MAX_MEM_GB=2000
    MAX_JOBFS_GB=28672
    RATE=4.5
    MEM_PER_NODE_GB=2000
    NCPUS_PER_NODE=128
    ;;
  h200)
    QUEUE=gpuhopper
    NCPUS=12
    NGPUS=1
    DEFAULT_MEM_GB=128
    DEFAULT_JOBFS_GB=200
    MAX_MEM_GB=1024
    MAX_JOBFS_GB=1741
    RATE=7.5
    MEM_PER_NODE_GB=1024
    NCPUS_PER_NODE=48
    ;;
  "") die "--kind is required" ;;
  *) die "--kind must be cpu, v100, a100, or h200" ;;
esac

MEM_GB=${MEM_GB:-$DEFAULT_MEM_GB}
JOBFS_GB=${JOBFS_GB:-$DEFAULT_JOBFS_GB}
[[ "$MEM_GB" =~ ^[1-9][0-9]*$ ]] || die "--mem-gb must be a positive integer"
[[ "$JOBFS_GB" =~ ^[1-9][0-9]*$ ]] || die "--jobfs-gb must be a positive integer"
((MEM_GB <= MAX_MEM_GB)) || die "memory exceeds $QUEUE one-node limit of ${MAX_MEM_GB}GB"
((JOBFS_GB <= MAX_JOBFS_GB)) || die "jobfs exceeds $QUEUE one-node limit of ${MAX_JOBFS_GB}GB"

if [[ ! "$WALLTIME" =~ ^([0-9]{2}):([0-9]{2}):([0-9]{2})$ ]]; then
  die "--walltime must use HH:MM:SS"
fi
HOURS=${BASH_REMATCH[1]}
MINUTES=${BASH_REMATCH[2]}
SECONDS=${BASH_REMATCH[3]}
((10#$MINUTES < 60 && 10#$SECONDS < 60)) || die "invalid walltime: $WALLTIME"
WALLTIME_SECONDS=$((10#$HOURS * 3600 + 10#$MINUTES * 60 + 10#$SECONDS))
((WALLTIME_SECONDS > 0 && WALLTIME_SECONDS <= 14400)) || \
  die "interactive debug walltime must be greater than zero and at most 04:00:00"

LOGIN_HOST=$(hostname -f)
case "$LOGIN_HOST" in
  gadi-login-*.gadi.nci.org.au|*.ps.gadi.nci.org.au) ;;
  *)
    ((PERSISTENT_CONTROL_HOST == 1)) || \
      die "run on a Gadi login node or pass --persistent-control-host inside an NCI persistent session; got $LOGIN_HOST"
    ;;
esac
[[ -z "${PBS_JOBID:-}" ]] || die "do not submit a nested debug job from inside PBS"

ACCOUNT_GROUPS=" $(id -nG) "
case "$ACCOUNT_GROUPS" in
  *" $PROJECT "*) ;;
  *) die "current account is not a member of $PROJECT" ;;
esac

if [[ -z "$SESSION" ]]; then
  SESSION=gadi-debug-$KIND-$(date -u +%Y%m%dT%H%M%SZ)
fi
[[ "$SESSION" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || die "unsafe tmux session name"

RESOURCE="walltime=$WALLTIME,ncpus=$NCPUS"
if ((NGPUS > 0)); then
  RESOURCE+=",ngpus=$NGPUS"
fi
RESOURCE+=",mem=${MEM_GB}GB,jobfs=${JOBFS_GB}GB,storage=gdata/wa66,wd"
QSUB_BIN=$(command -v qsub || true)
[[ -n "$QSUB_BIN" ]] || die "qsub is unavailable"
QSUB=("$QSUB_BIN" -I -P "$PROJECT" -q "$QUEUE" -N "dbg-$KIND" -l "$RESOURCE")
printf -v QSUB_DISPLAY '%q ' "${QSUB[@]}"
QSUB_DISPLAY=${QSUB_DISPLAY% }

WALLTIME_HOURS=$(awk -v seconds="$WALLTIME_SECONDS" 'BEGIN { printf "%.6f", seconds / 3600 }')
ESTIMATED_SU=$(awk \
  -v ncpus="$NCPUS" \
  -v mem="$MEM_GB" \
  -v mem_per_node="$MEM_PER_NODE_GB" \
  -v node_cpus="$NCPUS_PER_NODE" \
  -v rate="$RATE" \
  -v hours="$WALLTIME_HOURS" \
  'BEGIN {
     memory_units = mem / mem_per_node * node_cpus
     units = ncpus > memory_units ? ncpus : memory_units
     printf "%.2f", units * rate * hours
   }')

echo "Interactive debug preview"
echo "  Login host:   $LOGIN_HOST"
echo "  tmux session: $SESSION"
echo "  Project:      $PROJECT"
echo "  Queue:        $QUEUE"
echo "  Resources:    $NCPUS CPU, $NGPUS GPU, ${MEM_GB}GB mem, ${JOBFS_GB}GB jobfs"
echo "  Walltime:     $WALLTIME"
echo "  Estimated SU: $ESTIMATED_SU"
echo "  qsub command: $QSUB_DISPLAY"
echo
echo "Current project report:"
nci_account -P "$PROJECT"

if ((START == 0)); then
  echo
  echo "Preview only: no tmux session or PBS job was created."
  echo "After explicit approval, repeat this command with --start."
  exit 0
fi

command -v tmux >/dev/null 2>&1 || die "tmux is unavailable"
if tmux has-session -t "$SESSION" 2>/dev/null; then
  die "tmux session already exists: $SESSION"
fi

tmux new-session -d -s "$SESSION" -n interactive "/bin/bash --noprofile --norc"
tmux set-window-option -t "$SESSION:0" remain-on-exit on
tmux send-keys -t "$SESSION:0.0" -l "$QSUB_DISPLAY"
tmux send-keys -t "$SESSION:0.0" Enter

echo
echo "Interactive request started in detached tmux."
echo "Attach on $LOGIN_HOST: tmux attach -t $SESSION"
echo "Read without attaching:   tmux capture-pane -p -t $SESSION -S -200"
echo "End the PBS job with 'exit', then remove the finished session:"
echo "  tmux kill-session -t $SESSION"
echo "The tmux socket is control-host local and will not survive a control-host restart."
