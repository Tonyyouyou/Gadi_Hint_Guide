# PBS, GPUs, and Distributed Jobs

## Verified Queue Snapshot

Verified against NCI documentation and local PBS on 2026-08-12. Machine-readable values are in `queue-limits.json`.

| Queue | Hardware per node | CPU/GPU | Memory/node | Jobfs/node | Charge rate |
|---|---|---:|---:|---:|---:|
| `gpuvolta` | 4x V100 32 GB, 48 CPU | 12 | 382 GB | 400 GB | 3 SU/resource-hour |
| `dgxa100` | 8x A100 80 GB, 128 CPU | 16 | 2000 GB | 28 TB | 4.5 SU/resource-hour |
| `gpuhopper` | 4x H200 141 GB, 48 CPU | 12 | 1024 GB | 1741 GB | 7.5 SU/resource-hour |

H200 accepts `ncpus=12,24,36,48` on a partial node and multiples of 48 beyond one node. Default H200 walltime limits are 48 hours for 12-96 cores, 24 hours for 144-192, and 5 hours for 240-720.

Always re-check:

- [NCI Queue Structure](https://opus.nci.org.au/spaces/Help/pages/236880996/Queue%2BStructure%2Bon%2BGadi...)
- [NCI Queue Limits](https://opus.nci.org.au/spaces/Help/pages/236881198/Queue%2BLimits...)
- [NCI Job Submission](https://opus.nci.org.au/spaces/Help/pages/236880320/Job%2BSubmission...)

## Selection and Cost

- Select V100 for compatible workloads fitting 32 GB when lower cost matters.
- Select A100 for 80 GB memory, Ampere compatibility, or large local NVMe.
- Select H200 for 141 GB memory, Hopper features, or measured throughput gains justifying cost and delay.
- Request only GPUs the process uses. Do not override PBS-assigned `CUDA_VISIBLE_DEVICES`.
- Run a short one-GPU smoke test before scaling.

NCI approximately calculates:

```text
resource_units = max(ncpus, mem / mem_per_node * ncpus_per_node)
estimated_SU = resource_units * queue_rate * walltime_hours
```

One H200 with 12 CPUs for 10 hours is roughly 900 SU. Four H200s for 48 hours are roughly 17.28 KSU. High memory can increase the charge beyond the CPU/GPU floor.

## PBS Environment

Useful variables: `PBS_NCPUS`, `PBS_NGPUS`, `PBS_NNODES`, `PBS_NODEFILE`, `PBS_JOBFS`, `PBS_O_WORKDIR`, `PBS_O_QUEUE`, and `PROJECT`.

Avoid `qsub -V` from inside a PBS job because inherited PBS variables can be incorrect. Export only deliberate values.

## PyTorch

Single node, one process per GPU:

```bash
torchrun --standalone --nnodes=1 --nproc-per-node="$PBS_NGPUS" train.py
```

For multi-node work, launching `torchrun` once on the PBS head node does not start remote agents. Derive unique nodes from `PBS_NODEFILE`, then launch exactly one `torchrun` agent per node using `pbsdsh`, the compatible MPI module, or a framework-supported PBS integration. Assign node ranks consistently and stage node-local data independently on every node.

Do not use a generic multi-node launcher without adapting it to the installed PBS/MPI stack. Record node names, CUDA/framework/NCCL versions, and a minimal reproducer when diagnosing collective failures.
