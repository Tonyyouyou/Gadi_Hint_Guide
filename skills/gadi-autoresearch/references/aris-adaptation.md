# ARIS Adaptation

## Upstream Reference

The detailed local reference is:

```text
/g/data/wa66/Xiangyu/Auto-claude-code-research-in-sleep
```

This skill was designed against commit:

```text
e12e07c7b85ee1a4dc07e5463089aa16836af2bf
```

ARIS is MIT-licensed. Preserve its license and attribution if future updates copy upstream code or templates rather than only adapting workflow concepts.

Before using changed upstream behavior, inspect `git status`, record the new commit, and audit the relevant Codex skill. Do not pull or copy all upstream skills automatically.

## Preserved Concepts

| ARIS concept | Gadi autoresearch implementation |
|---|---|
| W1 idea discovery | immutable mission, adapter territory, observation probes, competing candidate portfolio, structured novelty audit, controller-launched cold review |
| W1.5 experiment bridge | implementation, code review, sanity-first, PBS experiment records |
| W2 auto review | bounded evidence/review iterations with explicit stop and pivot rules |
| W3 paper writing | plan, figures, LaTeX, compile, improvement, claim/citation audits |
| resumable runs | one atomic `campaign.json` with phase, jobs, artifacts, control handoff |
| external cadence | persistent controller only decides when Codex wakes |
| acceptance gate | same-family review provisional; deterministic/cross-family may accept |
| experiment integrity | cold review of code and raw result paths before claim synthesis |

The local discovery and novelty gates are stricter than a narrative W1 review: mission contribution
classes, adapter dependencies, candidate-count minimums, phase transitions, experiment stages,
artifact hashes, current-search timestamps, and distinct author/reviewer thread IDs are machine
checked. A rejected candidate returns to the portfolio or discovery rather than silently becoming a
diagnostic paper. A positive review still means only plausibly novel, not proven unique.

When a phase needs more detail, read only the corresponding upstream file, especially:

```text
skills/skills-codex/idea-discovery/SKILL.md
skills/skills-codex/experiment-plan/SKILL.md
skills/skills-codex/experiment-bridge/SKILL.md
skills/skills-codex/auto-review-loop/SKILL.md
skills/skills-codex/experiment-audit/SKILL.md
skills/skills-codex/result-to-claim/SKILL.md
skills/skills-codex/paper-writing/SKILL.md
skills/skills-codex/shared-references/resumable-runs.md
skills/skills-codex/shared-references/experiment-integrity.md
skills/skills-codex/shared-references/acceptance-gate.md
```

Do not invoke those execution instructions verbatim when they conflict with this skill.

## Deliberate Replacements

The following upstream defaults are prohibited on Gadi:

- `gpu: local|ssh|vast|modal`; use `gadi-interactive` or `gadi-batch`
- local conda environments and remote screen sessions; use immutable `.sqsh` and PBS
- `$HOME/.aris_queue` and per-run trace trees; use the approved campaign root and consolidated state
- 60-second GPU/PBS polling; use at least 600 seconds
- `MAX_PARALLEL_RUNS=4`; use the approved dynamic concurrency limit, default one
- `AUTO_DEPLOY=true` without a resource envelope; require recorded campaign approval
- one screen/job/log per small sweep cell; bundle trials inside bounded workers
- downloaded PDF/model/dataset caches in HOME or `.codex`; use copyq and packed storage
- automatic cloud fallback; never route Gadi work to Vast or Modal silently

## Review Semantics

Base Codex can execute and review, but a fresh Codex reviewer shares the same model family. Record:

```text
review_independence: same-family
acceptance_status: provisional
```

Only a genuinely different model family or deterministic verifier may produce `accepted`. Scheduler state, process exit, file existence, and metric parsing can deterministically accept execution facts; novelty, correctness, and publishability remain semantic judgments.

## File-Count Adaptation

ARIS's many Markdown artifacts and trace directories are useful on ordinary filesystems but unsafe as an unbounded default here. Gadi autoresearch keeps a fixed canonical artifact set, caps controller history, stores exact PBS scripts inside the state JSON, consolidates experiment ledgers, bundles sweep results, rotates checkpoints, and archives completed logs by phase.

The upstream repository itself is Codex-related reference source and may remain under `/g/data/wa66/Xiangyu`, but research outputs generated from it must never be written into that checkout or `.codex`.
