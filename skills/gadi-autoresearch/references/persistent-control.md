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
  controller    lightweight controller.py
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
pinned settings to the long-lived author thread and to fresh novelty-review threads.

The starter invokes the existing modern control-plane Python explicitly and launches a no-profile shell with stale PBS/jobfs/cache variables removed. It never edits HOME startup files.

The controller holds `controller.lock`, reads `campaign.json`, and acts only on control state:

| State | Controller action |
|---|---|
| `needs_agent` | start/resume one `codex exec` turn |
| `needs_novelty_review` | start one fresh, non-resumed adversarial reviewer thread |
| `waiting_pbs` | refresh tracked batch jobs at the permitted cadence, or wake the agent to inspect a recorded interactive tmux pane |
| `waiting_time` | sleep until recorded UTC time |
| `waiting_human` | exit and preserve state |
| `paused` | exit and preserve the safety reason |
| `complete` | exit |

Before launching Codex it verifies the pinned skill revision, reruns live
project/inode/file-envelope preflight, and changes the state to `agent_running` or
`novelty_reviewer_running`. Codex must write a handoff. A failed revision check/preflight,
nonzero exit, or missing handoff pauses the campaign, preventing a hot loop.

The controller uses Codex's `--approve-for-me` automatic command review so a deliberately approved unattended campaign can progress without an interactive prompt. It keeps the source repository as the workspace and adds only the recorded campaign root as an extra writable directory. This does not bypass the workspace sandbox, user rules, the campaign CLI, or its project/SU/job/GPU/deadline/file capabilities. Raw `qsub`/`qdel` remain forbidden.

The author uses one resumable thread ID; the controller pauses rather than creating a new
author session on every wake if the CLI returns no resumable ID. Novelty review is the narrow
exception: each requested review starts without `resume`, receives an adversarial role prompt,
and may only register the review plus handoff. The controller rejects an author/reviewer thread
ID match, audit mutation, invalid schema, non-provisional same-family assurance, or missing
handoff before attaching `cold_review` metadata. It never passes dangerous approval/sandbox
bypass flags and rotates a single log at 5 MiB.

## Failure Recovery

After login disconnect, persistent-session restart, Codex failure, or controller crash:

1. Reconnect and inspect `campaign.py status`.
2. Verify active PBS jobs with one permitted refresh.
3. Read the bounded controller and relevant PBS log.
4. Confirm `campaign.json`, workspace Git commit, `.sqsh`, data objects, and result markers still exist.
5. A stale `agent_running` or `novelty_reviewer_running` state pauses on restart to avoid launching a duplicate Codex process. Inspect the named tmux/controller process, then use `campaign.py resume` with a concrete reason only after no agent is running.
6. If authentication/session resume fails, pause and deliberately start a new Codex thread from campaign state rather than reconstructing progress from tmux text.

If the installed skill revision changed, inspect the diff and ensure no job is active before
using `campaign.py skill-adopt`. Do not edit the pinned commit/tree in `campaign.json`.

PBS jobs are the compute source of truth. The Codex conversation is useful context, not the durable experiment ledger.
