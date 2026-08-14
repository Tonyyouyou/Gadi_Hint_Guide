# Persistent Control

## Control Plane

NCI Persistent Sessions are intended for low-CPU, low-memory workflow managers that submit and monitor PBS jobs:

https://opus.nci.org.au/display/Help/Persistent+Sessions

They are explicitly not compute, download, or preprocessing hosts. NCI also asks workflow managers to query PBS at most once every ten minutes.

Create a session only after showing the command and obtaining approval:

```bash
persistent-sessions start -p PROJECT arisctl
```

The returned UUID and hostname are canonical. Store them in the campaign notes; do not parse `persistent-sessions list`, whose output is documented as unstable. Connect from a Gadi login/ARE host:

```bash
ssh arisctl.USER.PROJECT.ps.gadi.nci.org.au
```

Confirm the current documented/installed termination behavior before relying on automated cleanup because the NCI page and client help may differ.

## tmux Layout

Use a campaign-specific tmux session, for example:

```text
aris-CAMPAIGN
  controller    supervisor.py watchdog plus lightweight controller.py
  interactive   optional qsub -I terminal
  notes         optional shell for static inspection only
```

Never attach to, send keys to, or kill a generic/pre-existing tmux session. Keep no continuous tmux transcript on persistent storage.

An interactive request remains best-effort: PBS connects it to the requesting terminal, it is non-rerunnable, and a persistent-session restart can still break it. Save compact evidence after each atomic debug step and exit promptly when interactive work is complete.

## Controller Lifecycle

Preview first:

```bash
bash "$STARTER" --root "$ROOT" --session aris-CAMPAIGN
```

Start in the campaign tmux only after verifying `codex exec` authentication and network access in the persistent session:

```bash
bash "$STARTER" --root "$ROOT" --session aris-CAMPAIGN --start
```

When the user requests a specific model or reasoning tier, pin both in the preview and start
commands rather than relying on the global Codex configuration:

```bash
bash "$STARTER" --root "$ROOT" --session aris-CAMPAIGN \
  --model gpt-5.6-sol --reasoning-effort ultra
bash "$STARTER" --root "$ROOT" --session aris-CAMPAIGN \
  --model gpt-5.6-sol --reasoning-effort ultra --start
```

Keep an exact launcher in the campaign root for failure recovery. The controller forwards the
pinned settings to the long-lived author thread and to fresh novelty-review and arbitration threads.

The starter invokes the existing modern control-plane Python explicitly, removes stale PBS/jobfs/cache and ambient model/publishing token variables, and launches a no-profile shell. It never edits HOME startup files. Before creating tmux it runs a real ephemeral Codex canary that must use `apply_patch` to create and verify an exact marker in `/tmp`. A failed canary aborts startup.

The tmux process is `supervisor.py`, not the controller directly. The supervisor restarts an unexpectedly exited active controller with 15, 60, 300, then 900 second backoff. It stays idle when a campaign is deliberately paused, allowing an inspected `skill-adopt`/resume to reuse the same tmux session. The persistent-session host and tmux remain a single control-plane failure domain; if NCI restarts that host, rerun the exact recorded launcher.

The controller holds `controller.lock`, reads `campaign.json`, and acts only on control state:

| State | Controller action |
|---|---|
| `needs_agent` | start/resume one `codex exec` turn |
| `needs_novelty_review` | start one fresh, non-resumed adversarial reviewer thread |
| `needs_novelty_arbitration` | start one fresh, non-resumed arbiter thread distinct from author and reviewer |
| `waiting_pbs` | refresh tracked batch jobs at the permitted cadence, or wake the agent to inspect a recorded interactive tmux pane |
| `waiting_time` | sleep until recorded UTC time |
| `waiting_human` | remain idle until genuine external evidence or authorization is recorded |
| `paused` | supervisor remains idle and preserves the hard safety reason |
| `complete` | exit |

Before launching Codex it verifies the pinned skill revision, reruns live
project/inode/file-envelope preflight, and changes the state to `agent_running` or
`novelty_reviewer_running`/`novelty_arbiter_running`. Every launch records a host/PID/role lease and Codex must write a handoff. Transient preflight failures, nonzero exits, missing IDs/handoffs, PBS refresh errors, and stale leases schedule durable `waiting_time` recovery with 60, 300, 900, then 3,600 second delays. A repeatedly failing author thread is discarded after the fifth identical failure and reconstructed from `campaign.json`. Successful progress clears the failure counter.

ARIS persistent hosts currently disable the Linux user namespaces required by Codex's workspace sandbox. The controller therefore uses `codex exec --sandbox danger-full-access --config approval_policy="never"` only after the explicit campaign approval and successful real canary. This is an acknowledged reduction in OS-level containment: safety comes from the immutable mission, campaign capability checks, CLI-only submission/cancellation contract, clean environment, pinned skill, exact job ledger, and live budget/inode checks. Raw `qsub`/`qdel`, direct workload writes, and research data under `.codex` remain forbidden. Do not run the controller outside `start_controller.sh`.

The author normally uses one resumable thread ID. Missing IDs or handoffs retry with backoff; after repeated identical failure the controller deliberately rotates the author thread and rebuilds context from durable state instead of looping on a corrupt session. Novelty review is the narrow
exception: each requested review starts without `resume`, receives an adversarial role prompt,
and may only register the review plus handoff. The controller rejects an author/reviewer thread
ID match, audit mutation, invalid schema, non-provisional same-family assurance, or missing
handoff before attaching `cold_review` metadata. Conditional review opens only bounded probes;
after a bound rebuttal, arbitration is another fresh non-resumed thread that may only register the
arbitration and handoff. The controller rejects any reused author/reviewer/arbiter ID or changed
audit/review/rebuttal before attaching `cold_arbitration` metadata. A valid rejection atomically promotes the next ranked portfolio backup; an exhausted portfolio returns to discovery. It never passes the `--dangerously-bypass-approvals-and-sandbox` convenience flag and rotates a single log at 5 MiB.

## Failure Recovery

Login disconnect, Codex failure, and an ordinary controller crash need no human recovery: tmux survives the SSH disconnect, durable controller recovery handles Codex failures, and the supervisor restarts the controller. After a persistent-host restart or hard safety pause:

1. Reconnect and inspect `campaign.py status`.
2. Verify active PBS jobs with one permitted refresh.
3. Read the bounded controller and relevant PBS log.
4. Confirm `campaign.json`, workspace Git commit, `.sqsh`, data objects, and result markers still exist.
5. A stale `agent_running`, `novelty_reviewer_running`, or `novelty_arbiter_running` lease automatically returns to its role-specific queue after backoff; a matching live local PID prevents duplicate launch.
6. If authentication/session resume repeatedly fails, the controller rotates the author thread from campaign state. Reviewer and arbiter turns always restart in fresh independent contexts.

If the installed skill revision changed, inspect the diff and ensure no job is active before
using `campaign.py skill-adopt`. Do not edit the pinned commit/tree in `campaign.json`.

PBS jobs are the compute source of truth. The Codex conversation is useful context, not the durable experiment ledger.
