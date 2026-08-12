# Operations and Troubleshooting

## Submission Gates

Before `qsub`, show the selected project, queue, GPUs/CPUs, memory, jobfs, walltime, storage mounts, estimated SU, script path, and linter result. Submission is charged; a request to edit a script is not permission to submit it.

Interactive-debug approval and production-batch approval are separate. Keep `qsub -I` inside a detached login-node tmux session as described in [debugging.md](debugging.md). Do not interpret access to an interactive shell as permission to submit a later batch job.

Create the parent of the absolute `#PBS -o` path before submission and use `#PBS -j oe` to keep one bounded log per job. Never accept PBS defaults that can place stdout/stderr in HOME.

Before `qdel`, cleanup, replacement, or deletion, identify exact jobs/files and obtain explicit approval.

## Monitoring

Use `qstat -swx`, `qstat -fx`, `nqstat_anu`, `qps_gpu`, `qcat`, `qls`, and `qcp`. NCI recommends polling no more often than about once every ten minutes.

Official reference: [NCI Job monitoring](https://opus.nci.org.au/spaces/Help/pages/236880322/Job%2Bmonitoring...)

## Held or Queued Jobs

Inspect `qstat -fx` comments. Common causes include invalid resource combinations, allocation/queue caps, missing membership, unavailable storage projects, unsatisfied dependencies, or requests fitting very few nodes. Fix and lint instead of repeatedly resubmitting.

## Storage Failures

`No such file or directory` for a valid login-node path often means `storage=` omitted its filesystem. Jobs automatically receive scratch for the charging project; declare needed gdata and other-project scratch explicitly.

For quota errors, inspect both block and inode values with `nci_account -P <project>`. Removing one large file helps bytes, while consolidating/removing many small files helps inodes. Never mass-delete without explicit approval.

The linter rejects workload destinations under `/g/data/wa66/Xiangyu/.codex`; move them to `Data`, `enviroment_cache`, or an approved result tree.

`$PBS_JOBFS` disappears with its job. Never persist a `/jobfs/...` activation or executable path in `.bashrc`, `.bash_profile`, `.profile`, a symlink, or a generated launcher. `probe_gadi.py` reports stale shell-startup references without editing them.

## Memory and Jobfs Failures

PBS terminates jobs exceeding requested memory or local disk. Inspect full status, stderr, `nqstat_anu`, and jobfs usage. Size future requests from measured peaks. Multi-node memory and jobfs totals are divided across nodes.

## GPU Smoke Test

```bash
nvidia-smi
echo "$CUDA_VISIBLE_DEVICES"
module list
python - <<'PY'
import torch
print(torch.__version__, torch.version.cuda)
print(torch.cuda.is_available(), torch.cuda.device_count())
if torch.cuda.is_available():
    x = torch.ones(1024, device="cuda")
    print((x * 2).sum().item(), torch.cuda.get_device_name(0))
PY
```

Do not install an NVIDIA driver in the environment or image.

## Checkpoint Chains

Long work must checkpoint and resume. Prefer success-dependent chaining when appropriate; `afterany` can continue from a failed or corrupt state. A safe chain atomically writes and validates checkpoints outside `.codex`, bounds its sequence count, stops on application error, supports a stop marker, and limits checkpoint count.

Only submit a chain when the user requested it and understands cumulative cost.
