# Novelty Audit

## Contents

1. Purpose
2. Search protocol
3. Author artifact
4. Cold reviewer artifact
5. Conditional probe and rebuttal
6. Independent arbitration
7. Gate outcomes

## Purpose

Novelty is a claim to test, not a name to trust. Apply it to algorithms, objectives,
representations, architectures, systems, data resources, evaluation protocols, empirical findings,
and theory. Separate these questions:

1. Does the mechanism work?
2. Is the mechanism new?
3. Is only its use in this task new?

A useful transfer from another field is not automatically a new method. Conversely, the existence
of a broad primitive in another ordered modality does not make every target-domain mechanism
derivative. Classify a transfer as `new_application` when brand substitution leaves the functional
mechanism unchanged. Preserve a primary claim only when the target setting forces a technically
non-obvious mechanism or interaction absent from the checked prior work.

The mission decides which contribution classes may be final. The author performs a structured audit
of the active portfolio candidate. The controller then starts a fresh Codex thread for
an adversarial review. The new thread is context-independent from the author thread, but a
same-family semantic verdict remains `provisional` scientific assurance.

## Search Protocol

First rewrite the candidate without its coined name, task brand, or desired conclusion. Split
it into mechanism primitives and predicted interactions. Then search all seven routes:

| Route | Required target |
|---|---|
| `exact_mechanism` | Functional description and exact primitive interaction |
| `synonyms` | Alternative terminology, older terminology, acronyms, and inverse wording |
| `task_local` | The target task, its streaming/offline variants, benchmarks, and workshops |
| `adjacent_fields` | Fields sharing the same information flow, latency constraint, or algorithmic primitive |
| `combinations` | Every primitive pair, full A+B combination, and obvious composition |
| `code` | Official implementations, repository search, issue discussions, and package names |
| `backward_forward` | References and citing work around the earliest, closest, and newest candidates |

Use current web search. Inspect primary papers and official code, not only titles, abstracts,
search snippets, surveys, or model-generated summaries. Record at least three checked primary
sources and the three nearest mechanism neighbors. For every source, record a plausible year,
the section/page/algorithm/code locator actually inspected, and a concise paraphrase of its
mechanism evidence. Negative search is never proof of novelty; the strongest permitted conclusion
is `clear_to_plan`, which means only that the bounded research plan is justified.

Apply two explicit falsification tests:

- **Brand substitution:** replace the target model/task/domain name. If the claimed method is
  unchanged, the delta is probably an application or evaluation contribution.
- **A+B decomposition:** search each primitive, every pair, and the combined control flow. A
  collection of known components is a method contribution only when the interaction is both
  absent from prior work and technically non-obvious. The statement that one *could* combine A+B
  is not evidence that the combination exists, is obvious, or has the claimed interaction.

## Author Artifact

Write and register `CANDIDATE_PORTFOLIO.json`, then `IDEA_REPORT.md`. Write
`NOVELTY_AUDIT.json` with this exact schema and register it as `provisional`. Timestamps must
be UTC ISO-8601 and no more than 30 days old.

```json
{
  "schema_version": 2,
  "candidate_id": "safe-short-id",
  "idea_report_sha256": "sha256-of-recorded-IDEA_REPORT.md",
  "mission_sha256": "canonical-sha256-recorded-in-campaign.json",
  "route_sha256": "sha256-of-current-adapter-route",
  "candidate_portfolio_sha256": "sha256-of-recorded-CANDIDATE_PORTFOLIO.json",
  "searched_at": "2026-08-13T00:00:00Z",
  "mechanism_without_brand": "Functional mechanism with no coined method or task name.",
  "claim_class": "new_mechanism",
  "verdict": "plausibly_novel",
  "primitives": [
    {"id": "primitive-a", "description": "First functional primitive."},
    {"id": "primitive-b", "description": "Second functional primitive."}
  ],
  "searches": {
    "exact_mechanism": ["query"],
    "synonyms": ["query"],
    "task_local": ["query"],
    "adjacent_fields": ["query"],
    "combinations": ["query"],
    "code": ["query"],
    "backward_forward": ["query"]
  },
  "sources": [
    {
      "id": "a1",
      "title": "Primary source title",
      "url": "https://primary.example/paper",
      "year": 2024,
      "checked_locator": "Section 3 and Algorithm 1",
      "mechanism_evidence": "Paraphrase of the mechanism established by the checked passage.",
      "primary_source": true,
      "full_text_checked": true
    },
    {
      "id": "a2",
      "title": "Second primary source",
      "url": "https://primary.example/paper-2",
      "year": 2025,
      "checked_locator": "Methods, Section 2",
      "mechanism_evidence": "Paraphrase of the relevant mechanism evidence.",
      "primary_source": true,
      "full_text_checked": true
    },
    {
      "id": "a3",
      "title": "Third primary source",
      "url": "https://primary.example/paper-3",
      "year": 2026,
      "checked_locator": "Section 4 and official implementation",
      "mechanism_evidence": "Paraphrase of the checked paper or code behavior.",
      "primary_source": true,
      "full_text_checked": true
    }
  ],
  "nearest_neighbors": [
    {
      "source_id": "a1",
      "mechanism_overlap": "What is already present.",
      "remaining_delta": "What remains after removing that overlap."
    },
    {
      "source_id": "a2",
      "mechanism_overlap": "What is already present.",
      "remaining_delta": "What remains."
    },
    {
      "source_id": "a3",
      "mechanism_overlap": "What is already present.",
      "remaining_delta": "What remains."
    }
  ],
  "brand_substitution_test": {
    "outcome": "materially_changed",
    "explanation": "Why removing the task or model name changes the technical claim."
  },
  "combination_test": {
    "existing_combination": false,
    "decomposition": "primitive-a plus primitive-b",
    "non_obvious_interaction": "The specific interaction that is not ordinary composition."
  },
  "strongest_rejection": "Best evidence that this is already known or obvious.",
  "author_rebuttal": "Evidence-based response, or admission that the rejection stands."
}
```

Allowed `verdict` values are `plausibly_novel`, `derivative`, `application_only`,
`reproduction_only`, `unresolved`, and `rejected`. Allowed `claim_class` values are:

- primary: `new_mechanism`, `new_combination`, `new_architecture`, `new_objective`,
  `new_representation`, `new_system`, `new_data_resource`, `new_evaluation_protocol`,
  `new_empirical_finding`, or `new_theory`
- fallback: `new_application`, `reproduction`, or `diagnostic`
- unresolved: `unresolved`

The author may audit only a non-unresolved class accepted by the mission. The fresh reviewer may
reclassify it outside the mission; that evidence triggers fallback rather than being suppressed.

Register and request cold review:

```bash
"$PYTHON" "$CAMPAIGN" artifact "$ROOT" \
  --name novelty_audit --path "$ROOT/NOVELTY_AUDIT.json" --assurance provisional
"$PYTHON" "$CAMPAIGN" phase "$ROOT" novelty_review \
  --reason "candidate decomposed and current primary-source search recorded"
"$PYTHON" "$CAMPAIGN" handoff "$ROOT" --state needs_novelty_review \
  --reason "launch a fresh adversarial novelty review"
```

The author thread must never create or register `NOVELTY_REVIEW.json`.
Commit deliberate source changes and leave the research workspace clean before handoff. The
controller verifies the same clean source commit before and after review; any reviewer edit or
commit invalidates the verdict and pauses the campaign. A new review request also invalidates
the previous review record, so the fresh thread must register a new artifact.

## Cold Reviewer Artifact

The reviewer independently repeats all seven search routes before considering the author's
rebuttal. It seeks the earliest prior, closest prior, newest relevant prior, and exact
combination. The first three require a checked source. Only `exact_combination.source_id` may
be `null`, and its `conclusion` must explain that the exact combination was not found.

```json
{
  "schema_version": 2,
  "candidate_id": "safe-short-id",
  "audit_sha256": "sha256-of-recorded-NOVELTY_AUDIT.json",
  "reviewed_at": "2026-08-13T00:00:00Z",
  "independent_context": true,
  "decision": "clear_to_plan",
  "claim_class": "new_mechanism",
  "reviewer_searches": {
    "exact_mechanism": ["independent query"],
    "synonyms": ["independent query"],
    "task_local": ["independent query"],
    "adjacent_fields": ["independent query"],
    "combinations": ["independent query"],
    "code": ["independent query"],
    "backward_forward": ["independent query"]
  },
  "sources": [
    {
      "id": "r1",
      "title": "Checked primary source",
      "url": "https://primary.example/reviewer-paper-1",
      "year": 2024,
      "checked_locator": "Section 3 and Algorithm 1",
      "mechanism_evidence": "Independent paraphrase of the relevant mechanism.",
      "primary_source": true,
      "full_text_checked": true
    },
    {
      "id": "r2",
      "title": "Checked primary source two",
      "url": "https://primary.example/reviewer-paper-2",
      "year": 2025,
      "checked_locator": "Methods, Section 2",
      "mechanism_evidence": "Independent paraphrase of the relevant mechanism.",
      "primary_source": true,
      "full_text_checked": true
    },
    {
      "id": "r3",
      "title": "Checked primary source three",
      "url": "https://primary.example/reviewer-paper-3",
      "year": 2026,
      "checked_locator": "Section 4 and official implementation",
      "mechanism_evidence": "Independent paraphrase of the relevant mechanism.",
      "primary_source": true,
      "full_text_checked": true
    }
  ],
  "prior_checks": {
    "earliest": {"source_id": "r1", "conclusion": "Earliest relevant primitive."},
    "closest": {"source_id": "r2", "conclusion": "Closest mechanism and remaining delta."},
    "newest": {"source_id": "r3", "conclusion": "Newest relevant work."},
    "exact_combination": {"source_id": null, "conclusion": "No exact combination found."}
  },
  "primitive_overlap": [
    {
      "primitive_id": "primitive-a",
      "source_ids": ["r1", "r2"],
      "assessment": "Known overlap and what, if anything, remains."
    },
    {
      "primitive_id": "primitive-b",
      "source_ids": ["r2", "r3"],
      "assessment": "Known overlap and what, if anything, remains."
    }
  ],
  "strongest_rejection": "Best adversarial case against novelty.",
  "author_rebuttal_assessment": "Why the rebuttal fails or narrowly survives.",
  "blocking_overlaps": [],
  "required_changes": []
}
```

The reviewer registers this artifact with `--assurance provisional` and hands off to
`needs_agent`. The controller accepts it only when:

- the reviewer thread ID differs from the author thread ID
- the audit hash did not change during review
- every schema/search/source/primitive check passes
- the reviewer made the required handoff

The current reviewer decisions are exactly:

- `clear_to_plan`: no functionally equivalent exact prior was found, the remaining primary delta
  is technically justified, and both `blocking_overlaps` and `required_changes` are empty.
- `conditional_probe`: no functionally equivalent exact prior was found, but whether the proposed
  interaction exceeds a faithful naive A+B baseline is an empirical question answerable cheaply.
- `exact_prior_reject`: a checked primary source implements the functionally equivalent mechanism.

For `conditional_probe`, add this required object to the review:

```json
"probe_plan": {
  "question": "Single empirical novelty question.",
  "naive_combination_baseline": "Faithful competitive A+B implementation.",
  "distinguishing_outcome": "Result that supports a non-obvious interaction.",
  "falsifier": "Result that defeats the proposed interaction claim."
}
```

For `exact_prior_reject`, `prior_checks.exact_combination` must instead be:

```json
{
  "source_id": "r2",
  "conclusion": "Why this is the exact functional precedent.",
  "functionally_equivalent": true,
  "equivalence_evidence": "Checked algorithm or control-flow evidence showing the same inputs, decision, and effect."
}
```

Known primitives, a plausible A+B composition, brand similarity, or weak expected performance are
not sufficient for `exact_prior_reject`. If there is no exact prior and the remaining dispute is
empirical, the reviewer must use `conditional_probe` rather than manufacture a hard rejection.

## Conditional Probe and Rebuttal

The controller keeps the phase at `novelty_review`. Only `novelty_probe` experiments are opened;
planning and ordinary claim-bearing stages remain closed. Limits are the smaller of the campaign
envelope and all of these hard caps:

- three submitted job attempts
- 1,000 SU total, dynamically reduced for smaller campaigns
- one GPU and four hours per job
- 32 persistent entries including bounded output/log reserve

Every probe is hash-bound to the mission, route, portfolio, idea, audit, and cold review. It must
test the review's distinguishing question against the declared naive-combination baseline. After
one to three completed probes, the author writes and registers this exact provisional artifact:

```json
{
  "schema_version": 2,
  "candidate_id": "safe-short-id",
  "audit_sha256": "sha256-of-recorded-NOVELTY_AUDIT.json",
  "review_sha256": "sha256-of-recorded-NOVELTY_REVIEW.json",
  "written_at": "2026-08-14T00:00:00Z",
  "probe_experiment_ids": ["probe-coupling"],
  "probe_results": [
    {
      "experiment_id": "probe-coupling",
      "success_file_sha256": "sha256-of-published-success-marker",
      "finding": "Compact factual result, including the matched comparison."
    }
  ],
  "reviewer_objections": [
    {
      "objection": "The reviewer's concrete blocking objection.",
      "response": "Evidence-based response without expanding the claim.",
      "evidence_experiment_ids": ["probe-coupling"]
    }
  ],
  "naive_combination_baseline": "The implemented faithful A+B baseline.",
  "distinguishing_result": "Why the result supports a non-obvious interaction rather than branding or tuning.",
  "author_position": "advance",
  "remaining_risks": ["Unresolved limitation, or an empty list only when none remains."]
}
```

The CLI verifies that every referenced experiment is a completed current-lineage `novelty_probe`
and that each success-marker hash matches. Then request the third evaluator:

```bash
"$PYTHON" "$CAMPAIGN" artifact "$ROOT" \
  --name novelty_rebuttal --path "$ROOT/NOVELTY_REBUTTAL.json" --assurance provisional
"$PYTHON" "$CAMPAIGN" handoff "$ROOT" --state needs_novelty_arbitration \
  --reason "bounded novelty probes and bound rebuttal complete"
```

The author must never create or register `NOVELTY_ARBITRATION.json`.

## Independent Arbitration

The controller starts a fresh non-resumed third thread. Its ID must differ from both the resumable
author thread and cold-review thread. It reads the checked prior work, probe results, review, and
rebuttal; it may not modify source or run more experiments. It writes:

```json
{
  "schema_version": 2,
  "candidate_id": "safe-short-id",
  "audit_sha256": "sha256-of-recorded-NOVELTY_AUDIT.json",
  "review_sha256": "sha256-of-recorded-NOVELTY_REVIEW.json",
  "rebuttal_sha256": "sha256-of-recorded-NOVELTY_REBUTTAL.json",
  "arbitrated_at": "2026-08-14T01:00:00Z",
  "independent_context": true,
  "decision": "clear_to_plan",
  "claim_class": "new_mechanism",
  "probe_validity_assessment": "Whether the probe isolates the disputed interaction.",
  "naive_combination_assessment": "Whether the A+B baseline is faithful and competitive.",
  "non_obvious_interaction_assessment": "Whether the result exceeds ordinary composition or tuning.",
  "paper_contribution_assessment": "The narrow paper-facing contribution that remains.",
  "blocking_issues": [],
  "required_changes": [],
  "exact_prior": null
}
```

For `exact_prior_reject`, `exact_prior` must contain `title`, an HTTP(S) `url`,
`checked_locator`, `equivalence_evidence`, `primary_source: true`, `full_text_checked: true`, and
`functionally_equivalent: true`. A clear arbitration requires a mission-accepted primary class,
no blocking issues, and `exact_prior: null`. The controller binds final clearance to both the
rebuttal and arbitration hashes.

## Gate Outcomes

| Review outcome | Permitted work |
|---|---|
| `clear_to_plan` (or legacy `plausibly_novel`) + mission-accepted primary class | Claim-bearing pilot, main, and ablation under the matching adapter evidence protocol |
| `conditional_probe` | At most the bounded `novelty_probe` jobs, then rebuttal and third-thread arbitration |
| Attested arbitration `clear_to_plan` | Claim-bearing work bound to review, rebuttal, and arbitration hashes |
| `exact_prior_reject` from cold review or arbitration | Controller returns to portfolio/discovery; no claim-bearing work |
| Mission explicitly permits the resolved fallback class | Application/reproduction/diagnostic baseline, audit, and paper only |
| Rejected, unresolved, required changes, or class outside mission | Controller returns to portfolio when a backup exists, otherwise discovery |

`discovery`, `sanity`, and `profile` experiments may run before the gate because they generate
bounded observations or test infrastructure/feasibility with existing frozen inputs. Before final
clearance, at most two candidate-independent storage jobs may publish one environment and one data
object, totaling at most 500 SU and eight persistent entries. They still require explicit
`allow_storage_publish`, the audited jobfs builder/packer, an immutable `.sqsh` under
`/g/data/wa66/Xiangyu/enviroment_cache`, or packed data under `/g/data/wa66/Xiangyu/Data`.
All experiment registration and submission revalidate the applicable bound artifacts and caps.
Changing the mission requires a new campaign. Changing the route or portfolio invalidates later
claim artifacts. Changing the idea report invalidates the audit; changing the audit invalidates the
review, rebuttal, and arbitration. A new review invalidates prior rebuttal/arbitration. A review
older than 30 days blocks later work and final completion until the search is refreshed through a
new audit and a new fresh reviewer thread.
