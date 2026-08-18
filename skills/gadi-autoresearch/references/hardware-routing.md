# Evidence-Aware GPU Routing

Choose hardware for the next valid piece of evidence. Do not choose a GPU family once for an
entire campaign, and do not treat H200 as the default merely because it is newer.

## Classify the Evidence

Classify each GPU experiment before registration:

- **functional or diagnostic**: imports, precision support, exactness, memory, a tiny real witness,
  or implementation debugging
- **exploratory mechanism**: a bounded pilot, falsifier, control, or ablation used to decide what
  to implement next
- **portable performance**: matched method and baselines measured on one declared deployment
  platform
- **architecture-specific**: a CUDA kernel, compiler path, datatype, interconnect, or memory
  behavior whose claim explicitly names an architecture
- **final replication**: a frozen paper configuration repeated on the target platform

Functional success on one GPU can establish portability to that GPU. It cannot establish a
speedup on another GPU. Performance comparisons must run the method and every compared baseline
on the same GPU family, precision, software image, workload, batching policy, and measurement
protocol. A cross-device table may report separate matched experiments, but never use an A100
method number against an H200 baseline number.

## Filter for Compatibility

Build the compatible queue set from hard requirements before looking at queue pressure:

| Queue | GPU | Use when |
| --- | --- | --- |
| `gpuvolta` | V100 32 GB | FP16/FP32 work fits with headroom and needs no native BF16, Ampere, or Hopper feature |
| `dgxa100` | A100 80 GB | portable native-BF16 work, ordinary CUDA development, or measured peak fits with at least 20% headroom |
| `gpuhopper` | H200 141 GB | measured A100 capacity is insufficient, the mechanism is Hopper-specific, or this is matched H200 final evidence |

Unknown memory is not evidence that H200 is required. Start with a bounded A100 memory witness
when the model can plausibly fit, then escalate only from measured peak, OOM, or an explicit
architecture requirement. V100 is incompatible with native-BF16 claims. Do not emulate a missing
architecture feature and call it equivalent evidence.

For multi-GPU work, include per-rank memory, topology, collective, and node-count requirements.
Do not request multiple GPUs until a one-GPU witness passes unless the workload is intrinsically
distributed.

## Select for Time to Evidence

After compatibility filtering:

1. Use the campaign preflight for current project/SU eligibility.
2. Observe compatible GPU queues with `nqstat_anu -a` and the campaign's own jobs with
   `campaign.py refresh`. Share the campaign's ten-minute PBS observation budget; do not add a
   second polling loop.
3. Prefer the route with the shortest credible time to valid evidence. Use lower SU cost as the
   tie-breaker. Queue counts are observations, not guaranteed start-time predictions.
4. Record one consolidated campaign policy or experiment-bound config entry containing:
   evidence class, hard requirements, compatible queues, rejected queues and reasons, observation
   time, selected queue, matched-comparison scope, and fallback.
5. Use separate immutable experiment IDs, configs, commits, and result directories when the GPU
   family changes.

Portable BF16 diagnostic and exploratory work that fits A100 should default to `dgxa100` when it
has materially lower pressure than `gpuhopper`. CPU-only reasoning, preparation, and parsing stay
off GPU queues.

## Reuse Debug Allocations

A CPU or GPU batch is not a debugging terminal. If the parser, model, container, CUDA path, kernel,
staging, or real-stack interface needs edit-run-inspect cycles, use one interactive allocation for
at most four hours. After the first interpreted technical failure from a batch, another same-cell
batch repair is blocked until an interactive diagnostic linked with `--debug-for` completes on the
successor batch's queue at the exact successor source commit. Use `normal` for CPU/parser repairs
and a single GPU for GPU repairs.

Keep the PBS shell alive after a nonzero workload exit. Commit each control-side repair, rerun
`interactive-run` in the same allocation, and let it replace only its previous jobfs staging. Do
not close the allocation until the smallest representative real witness succeeds or no concrete
next run can be prepared without a long or external wait. A scientific gate or negative result is
terminal evidence, not a technical excuse to keep tuning inside the allocation.

## Bounded Queue Rerouting

Declare the fallback before submitting. A reasonable default for a portable diagnostic or pilot
with walltime at most four hours is to reconsider after 30 queued minutes. For longer portable
jobs, reconsider after 60 queued minutes. Override those defaults when current site conditions or
reservation constraints justify it, and record why.

Reroute only when all of the following hold:

- the original attempt is still queued or held, never running or finishing
- another compatible queue has a current, rate-compliant observation indicating materially lower
  pressure
- the replacement preserves the scientific cell and has an explicit within-device claim ceiling
- the campaign grants `allow_auto_cancel`
- cancellation uses `campaign.py cancel --execute`, reaches a recorded terminal state, and the
  successor receives a new immutable experiment ID

Allow at most one queue-driven reroute per scientific cell in six hours. Do not race duplicate
copies of the same cell across queues, and do not oscillate between architectures. If cancellation
is not approved, leave the job intact and hand off rather than using raw `qdel` or submitting a
duplicate that may consume both allocations.

Never cancel a running job for queue optimization. A running attempt may be cancelled only for a
separate recorded safety or technical-invalidity reason permitted by the campaign contract.

## Escalation and Final Evidence

Move from A100 to H200 only when one of these becomes true:

- measured peak memory plus required headroom exceeds A100 capacity
- the code path uses a Hopper-only instruction, datatype, compiler path, or topology
- the deployment claim explicitly targets H200
- a frozen promising result is ready for matched H200 replication

An A100 pilot may choose or reject a hardware-portable mechanism. If it passes, rerun the selected
method and all paper-facing baselines together on the final target hardware. If it fails for a
scientific reason, do not spend H200 merely hoping the conclusion changes; first identify a
hardware-specific causal reason that predicts a different outcome.
