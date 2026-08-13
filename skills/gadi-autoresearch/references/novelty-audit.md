# Novelty Audit

## Contents

1. Purpose
2. Search protocol
3. Author artifact
4. Cold reviewer artifact
5. Gate outcomes

## Purpose

Novelty is a claim to test, not a name to trust. Apply it to algorithms, objectives,
representations, architectures, systems, data resources, evaluation protocols, empirical findings,
and theory. Separate these questions:

1. Does the mechanism work?
2. Is the mechanism new?
3. Is only its use in this task new?

A useful transfer from another field is not automatically a new method. Classify it as
`new_application` unless the target setting forces a technically non-obvious mechanism or
interaction that the source-field method did not contain.

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
mechanism evidence. Negative search is never proof of novelty; the strongest permitted
conclusion is `plausibly_novel`.

Apply two explicit falsification tests:

- **Brand substitution:** replace the target model/task/domain name. If the claimed method is
  unchanged, the delta is probably an application or evaluation contribution.
- **A+B decomposition:** search each primitive, every pair, and the combined control flow. A
  collection of known components is a method contribution only when the interaction is both
  absent from prior work and technically non-obvious.

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
  "decision": "plausibly_novel",
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

## Gate Outcomes

| Review outcome | Permitted work |
|---|---|
| `plausibly_novel` + mission-accepted primary class | Claim-bearing pilot, main, and ablation under the matching adapter evidence protocol |
| Mission explicitly permits the resolved fallback class | Application/reproduction/diagnostic baseline, audit, and paper only |
| Rejected, unresolved, required changes, or class outside mission | Controller returns to portfolio when a backup exists, otherwise discovery |

`discovery`, `sanity`, and `profile` experiments may run before the gate because they generate
bounded observations or test infrastructure/feasibility with existing frozen inputs. Environment/data scripts may be previewed, but new
persistent storage jobs also wait for a resolved classification. All later experiment
registration and submission revalidate the bound artifacts.
Changing the mission requires a new campaign. Changing the route or portfolio invalidates later
claim artifacts. Changing the idea report invalidates the audit; changing the audit invalidates the review. A
review older than 30 days blocks later work and final completion until the search is refreshed
through a new audit and a new fresh reviewer thread.
