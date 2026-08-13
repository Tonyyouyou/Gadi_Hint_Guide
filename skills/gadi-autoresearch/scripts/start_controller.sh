#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  start_controller.sh --root CAMPAIGN_ROOT --session NAME [options]

Preview is the default. --start launches the event-driven controller in one
detached tmux session on an NCI persistent-session control host.

Options:
  --codex-bin PATH          Codex executable (default: command -v codex)
  --persistent-control-host
                            Accept an internal persistent-host name that does
                            not end in .ps.gadi.nci.org.au
  --start                   Start the clean tmux controller
  -h, --help                Show this help
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

ROOT=
SESSION=
CODEX_BIN=
START=0
PERSISTENT_CONTROL_HOST=0

while (($#)); do
  case "$1" in
    --root) ROOT=${2:?}; shift 2 ;;
    --session) SESSION=${2:?}; shift 2 ;;
    --codex-bin) CODEX_BIN=${2:?}; shift 2 ;;
    --persistent-control-host) PERSISTENT_CONTROL_HOST=1; shift ;;
    --start) START=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[[ -n "$ROOT" && "$ROOT" == /* && -f "$ROOT/campaign.json" ]] || \
  die "--root must be an absolute campaign directory containing campaign.json"
[[ "$SESSION" =~ ^[A-Za-z][A-Za-z0-9_.-]{0,63}$ ]] || \
  die "--session must be a safe tmux name of at most 64 characters"
[[ -z "${PBS_JOBID:-}" ]] || die "the controller cannot run inside PBS"

CONTROLLER=/g/data/wa66/Xiangyu/.codex/skills/gadi-autoresearch/scripts/controller.py
[[ -f "$CONTROLLER" ]] || die "installed controller not found: $CONTROLLER"
PYTHON=/home/561/xz4320/miniconda3/bin/python3
[[ -x "$PYTHON" ]] || die "modern control-plane Python is unavailable: $PYTHON"
if [[ -z "$CODEX_BIN" ]]; then
  if [[ -x /g/data/wa66/Xiangyu/npm-global/bin/codex ]]; then
    CODEX_BIN=/g/data/wa66/Xiangyu/npm-global/bin/codex
  else
    CODEX_BIN=$(command -v codex || true)
  fi
fi
[[ -n "$CODEX_BIN" && -x "$CODEX_BIN" ]] || die "Codex executable is unavailable: $CODEX_BIN"
command -v node >/dev/null 2>&1 || die "node is unavailable for the installed Codex launcher"

HOST=$(hostname -f)
if ((START == 1)); then
  case "$HOST" in
    gadi-login-*.gadi.nci.org.au)
      die "start an overnight controller only after connecting to an NCI persistent session"
      ;;
    *.ps.gadi.nci.org.au) ;;
    *)
      ((PERSISTENT_CONTROL_HOST == 1)) || \
        die "pass --persistent-control-host only after verifying this is an NCI persistent session: $HOST"
      ;;
  esac
fi

COMMAND=(
  env
  -u PBS_JOBID -u PBS_JOBFS -u TMPDIR
  -u CONDA_PREFIX -u VIRTUAL_ENV -u PYTHONPATH
  -u APPTAINER_CACHEDIR -u APPTAINER_TMPDIR
  -u HF_HOME -u HF_DATASETS_CACHE -u HUGGINGFACE_HUB_CACHE
  -u TRANSFORMERS_CACHE -u TORCH_HOME -u PIP_CACHE_DIR
  -u XDG_CACHE_HOME -u XDG_CONFIG_HOME -u XDG_DATA_HOME
  PYTHONDONTWRITEBYTECODE=1
  "$PYTHON" "$CONTROLLER" "$ROOT"
  --codex-bin "$CODEX_BIN"
  --start --loop --poll-seconds 600
)
printf -v DISPLAY '%q ' "${COMMAND[@]}"
DISPLAY=${DISPLAY% }
printf -v TMUX_COMMAND '%q ' /bin/bash --noprofile --norc -c "$DISPLAY"
TMUX_COMMAND=${TMUX_COMMAND% }

echo "Gadi autoresearch controller preview"
echo "  Control host: $HOST"
echo "  Campaign:     $ROOT"
echo "  tmux session: $SESSION"
echo "  Codex:        $CODEX_BIN"
echo "  Command:      $DISPLAY"
echo
"$PYTHON" "$CONTROLLER" "$ROOT" --codex-bin "$CODEX_BIN"

if ((START == 0)); then
  echo
  echo "Preview only: no tmux session or Codex process was created."
  exit 0
fi

command -v tmux >/dev/null 2>&1 || die "tmux is unavailable"
if tmux has-session -t "$SESSION" 2>/dev/null; then
  die "tmux session already exists: $SESSION"
fi
tmux new-session -d -s "$SESSION" -n controller "$TMUX_COMMAND"
tmux set-window-option -t "$SESSION:0" remain-on-exit on

echo
echo "Controller started in clean detached tmux on $HOST."
echo "Read:   tmux capture-pane -p -t $SESSION -S -200"
echo "Attach: tmux attach -t $SESSION"
