#!/bin/bash
set -euo pipefail

echo "Running inside Singularity container"
echo "Host list from PBS_NODEFILE, if available:"
if [[ -n "${PBS_NODEFILE:-}" && -f "$PBS_NODEFILE" ]]; then
  sort -u "$PBS_NODEFILE"
fi

which python
python -V

# Single-process example. Replace this with your real command.
python -c "import sys; print('container python:', sys.executable)"

# Single-node multi-GPU example:
# torchrun \
#   --nproc_per_node="${PBS_NGPUS:-1}" \
#   /path/to/train.py \
#   --arg1 value1

# Multi-node example:
# MASTER_ADDR=$(head -n 1 "$PBS_NODEFILE")
# NNODES=$(sort -u "$PBS_NODEFILE" | wc -l)
# NPROC_PER_NODE="${PBS_NGPUS:-1}"
#
# torchrun \
#   --nnodes="$NNODES" \
#   --nproc_per_node="$NPROC_PER_NODE" \
#   --rdzv_backend=c10d \
#   --rdzv_endpoint="${MASTER_ADDR}:29500" \
#   /path/to/train.py \
#   --arg1 value1
