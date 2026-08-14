# Paper Completion

## Paper Construction

Create a compact `PAPER_PLAN.md` from `NARRATIVE_REPORT.md`. Every section, table, and figure must map to existing evidence or be marked as a limitation/future-work item. Never create a result-shaped placeholder that could be mistaken for measured evidence.

Generate figures from canonical machine-readable results with committed scripts. Retain only final figures and their small generation sources. Do not persist plot caches, per-seed images, LaTeX auxiliary trees, or multiple full PDF rounds.

Write English LaTeX with this compact durable shape unless a venue requires more:

```text
paper/
  main.tex
  references.bib
  figures/
  sections/        # only when genuinely useful
  main.pdf
```

Build auxiliary files in `$PBS_JOBFS` when compilation needs a PBS/container environment, then copy back only source, bibliography, final figures, and `main.pdf`. A short lightweight compile may run as static work if it stays within login limits; otherwise use a CPU batch job and a TeX `.sqsh`.

## Overleaf Git Handoff

When the user identifies an Overleaf project, use its project ID with the clean remote URL `https://git.overleaf.com/<PROJECT_ID>`. The username is `git`; the host-specific Git credential helper obtains the authentication token from `OVERLEAF_TOKEN`, with a private gdata-backed fallback. The token is an account credential, not a project ID.

Clone only into the campaign workspace or another user-approved path under `/g/data/wa66/Xiangyu`, never HOME or `.codex`. Keep the paper repository compact and exclude LaTeX auxiliary output. Never put the token in a clone URL, Git remote, tracked `.env` file, PBS script, command log, paper source, or skill repository. A clone or pull does not authorise pushing changes to Overleaf; push only when the user explicitly requests that external update.

## Required Audits

Before final completion:

1. **Mission and novelty refresh**: mission, adapter route, portfolio, idea, audit, and review hashes agree; searches are no more than 30 days old; the paper uses a mission-permitted claim class.
2. **Experiment integrity**: real ground truth/proxy labels, no leakage, no phantom files, no selective normalization, honest scope.
3. **Result-to-claim**: every headline and abstract claim has raw evidence and respects its claim ceiling.
4. **Paper claim audit**: every number, comparison, dataset size, seed count, and tolerance agrees with canonical machine-readable results.
5. **Citation audit**: every cited work exists, metadata is correct, and the cited passage actually supports the surrounding statement.
6. **Compilation check**: clean LaTeX build succeeds, references resolve, figures exist, and the final PDF is nonempty/readable.
7. **Human-evidence check**: every perceptual or preference claim has accepted real evidence when the route requires it; no ratings or participant records were invented.
8. **Limitations check**: negative results, failed settings, compute limits, proxy evaluation, population limits, and unresolved risks appear in the paper.
9. **Learning-lineage check**: every terminal scientific experiment has one interpretation, every required failure review is independently attested, the final claim is frozen on the current hypothesis version, and no generating evidence is reused as confirmation for its child.

Semantic audits performed only by fresh Codex reviewers remain `provisional`. Deterministic compilation, schema, metric-trace, and file checks may be recorded as `deterministic`. Do not upgrade provisional science to submission-ready wording.

## Campaign Artifact Gate

Record these canonical names with `campaign.py artifact`:

| Name | Typical path |
|---|---|
| `mission` | `MISSION.json` |
| `research_brief` | `RESEARCH_BRIEF.md` |
| `discovery_report` | `DISCOVERY_REPORT.md` |
| `candidate_portfolio` | `CANDIDATE_PORTFOLIO.json` |
| `research_graph` | `RESEARCH_GRAPH.json` |
| `learning_ledger` | `LEARNING_LEDGER.jsonl` |
| `idea_report` | `IDEA_REPORT.md` |
| `novelty_audit` | `NOVELTY_AUDIT.json` |
| `novelty_review` | `NOVELTY_REVIEW.json` |
| `research_contract` | `RESEARCH_CONTRACT.md` |
| `experiment_plan` | `EXPERIMENT_PLAN.md` |
| `experiment_ledger` | `EXPERIMENT_LEDGER.jsonl` |
| `results` | `RESULTS.md` |
| `experiment_audit` | `EXPERIMENT_AUDIT.md` or JSON |
| `claim_audit` | `CLAIM_AUDIT.md` or JSON |
| `narrative_report` | `NARRATIVE_REPORT.md` |
| `paper_source` | `paper/main.tex` |
| `paper_pdf` | `paper/main.pdf` |
| `citation_audit` | `paper/CITATION_AUDIT.md` or JSON |
| `final_report` | `FINAL_REPORT.md` |

When the selected adapter route has `human_evaluation: required`, also record
`human_evaluation` as accepted JSON. The completion gate validates its real source, population,
blinding, positive rater/judgment counts, metrics, limitations, packed-evidence digest, and binding
to the current mission, route, active candidate, and novelty audit.

`FINAL_REPORT.md` must state:

- immutable mission, final adapter route, and research question
- discovered opportunity, selected candidate, rejected candidates, and important pivots
- novelty decision, claim class, closest prior work, and reviewer thread provenance
- exact Git commit, `.sqsh`, data versions, projects, jobs, GPU/SU estimates, and file-count delta
- primary results with uncertainty and baseline comparison
- negative results and remaining limitations
- paper source and PDF paths
- audit provenance and `overall_assurance`
- human-evidence provenance and population limits when applicable
- whether the work is a draft, provisional submission candidate, or accepted-assurance candidate

Commit the final paper source and evidence-generation code, leave the workspace clean, and record artifacts only after their final content is stable. `paper_source` must be a tracked `.tex` file; the completion gate records the final Git commit. Only after inspecting every recorded path and confirming no active jobs remain may the agent run:

```bash
"$PYTHON" "$CAMPAIGN" handoff "$ROOT" --state complete \
  --reason "all canonical artifacts inspected; no active jobs; final PDF compiles"
```
