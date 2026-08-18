# Research Lab Operating Model

Use this reference for role boundaries, scientific maturity, structured decision packets, and the schemas recorded inside `campaign.json` and `LEARNING_LEDGER.jsonl`.

## Contents

1. [Operating principle](#operating-principle)
2. [Roles and authority](#roles-and-authority)
3. [Portfolio maturity](#portfolio-maturity)
4. [Three independent state lanes](#three-independent-state-lanes)
5. [Opportunity scouts](#opportunity-scouts)
6. [Experiment cells and independent analysis](#experiment-cells-and-independent-analysis)
7. [Protocol revisions](#protocol-revisions)
8. [Director decisions](#director-decisions)
9. [Critic contract](#critic-contract)
10. [Circuit breakers](#circuit-breakers)
11. [Claim graph and paper](#claim-graph-and-paper)
12. [Schemas](#schemas)

## Operating Principle

The smallest research loop is:

```text
decision-changing question
  -> cheapest discriminating test
  -> raw compact result
  -> blind independent analysis
  -> Research Director decision
```

Do not optimize the campaign for the number of experiments, reviewer objections, or artifacts. Optimize early work for information gained per hour and time-to-kill. Increase rigor only when evidence promotes a branch.

The paper is downstream of a robust finding. A reviewer-shaped story without a core real-path signal is not progress.

Choose one recorded campaign posture: `signal_first` for new territory, `balanced` for normal discovery-to-paper work, or `submission` for a mature claim that now needs replication and audits. A mode changes prioritization, never storage, evidence, novelty, or safety gates.

## Roles and Authority

### Research Director

The resumable author thread is the PI and sole workspace writer. It owns:

- portfolio selection and branch budgets
- final interpretation after reading the blind analysis
- protocol scope and claim ceilings
- promote, park, kill, refine, branch, or pivot decisions
- code integration and one canonical Git history
- claim synthesis and paper writing

The Director must not simulate independent agreement in its own context.

### Opportunity scouts

The controller launches fresh literature, systems, and cross-domain scouts. They cannot edit source, see one another's reports, submit jobs, or select the final portfolio. Their reports are inputs to the Director.

### Branch scientist and experimental engineer

These are responsibilities inside the single writer thread, not competing writers:

- scientist: causal mechanism, predictions, falsifiers, and decision question
- engineer: implementation, interactive repair, environment/data staging, PBS execution

Infrastructure failure cannot change a scientific claim. Scientific taste cannot bypass an infrastructure receipt.

### Evidence analyst

For every completed evidence-bearing scientific batch, a fresh analyst sees the registered hypothesis, experiment, raw compact output, and attempt metadata before seeing the author's interpretation. Failed, cancelled, diagnostic, and interactive attempts go directly to infrastructure interpretation. The analyst cannot edit source or mutate campaign state except `analysis-record`.

### Critics

- novelty critic: invoked at claim promotion, not before the first real mechanism scout
- mechanism critic: invoked for a material scientific mutation
- integrity/reproducibility critic: invoked at claim or paper maturity

Critics are advisory except for a concrete `hard_invalidating` issue. The Director owns the next action and opportunity-cost tradeoff.

### Deterministic services

The campaign CLI, PBS controller, hashes, budgets, storage rules, resource validation, and state transitions are software, not LLM judgments.

## Portfolio Maturity

```text
seed -> scout -> pilot -> claim -> paper
  \       \        \       \
   park / kill / refine / branch / pivot
```

### Seed

- observation or formally defined tension
- causal hypothesis and nearest-work delta
- falsifier and cheapest distinguishing test
- no claim that a coined method is novel

### Scout

- preliminary nearest-prior search
- minimal integrated witness on a real model/runtime path
- narrow or clean subset is allowed when declared
- evidence ceiling is exploratory
- goal is to detect a signal or kill the branch quickly

### Pilot

- actual target model/runtime
- competitive naive baseline
- one decisive ablation or negative control
- protocol explicitly authorizes pilot scope
- result may justify a paper-facing claim but does not confirm it

### Claim

- branch promoted by a Director decision using valid core evidence
- exhaustive novelty audit and fresh critic
- frozen confirmatory protocol
- matched baselines, statistics, robustness, and claim-relevant integrity

### Paper

- independent reproduction of the central result
- claim graph and citation audit
- final novelty refresh
- English LaTeX source and compiled PDF

Promotion advances exactly one maturity level. A negative signal may still be high information, but does not become a positive paper claim without a new test.

## Three Independent State Lanes

### Scientific lane

Answers whether the causal mechanism, prediction, or ceiling is real. Valid outcomes can support, falsify, qualify, or reveal an anomaly.

### Protocol lane

Owns datasets, retained endpoints, split rules, metrics, baselines, human-evidence policy, and claim scope. Protocol revisions do not create child hypotheses.

Hard protocol blockers are limited to:

- actual leakage or contamination reachable by consumed evaluation examples
- invalid or non-identifying metrics
- safety, authorization, or provenance violations
- evidence that cannot be parsed or bound to the registered execution

Excluded records or unobserved relation types become warnings or scope ceilings unless they connect consumed endpoints. A relation with no real positive evidence can be declared out of scope.

### Infrastructure lane

Owns environments, data acquisition, parser and path defects, compilation, CUDA/runtime failures, OOM, PBS, and publication receipts. A technical failure uses repair and carries no scientific update.

One scientific cell may contain multiple technical attempts. Use a stable `cell_id`; do not create a new scientific question or source filename for each repair.

## Opportunity Scouts

The Director requests:

```bash
campaign.py handoff ROOT \
  --state needs_opportunity_scouts \
  --reason "new territory requires independent opportunity discovery"
```

The controller runs all three roles in fresh contexts. The Director resumes only after all reports are attested. Request another round only after a material territory change, not because the first ranking was uncomfortable.

Scout outputs describe causal opportunities rather than polished paper titles. Candidate ranking considers:

- importance and task relevance
- mechanistic distinctness from nearest work
- falsifiability
- cheapest time to a real signal
- implementation and data risk
- realistic paper ceiling if the signal survives

## Experiment Cells and Independent Analysis

Every scientific registration declares:

- `cell_id`: stable decision question across repairs
- `decision_question`
- `decision_if_supports`
- `decision_if_falsifies`
- `maturity`
- `protocol_revision`
- `core_mechanism_test` when applicable
- compatible queues, selected queue, one fallback, and resource rationale

Use `scout` for the first integrated mechanism witness. Do not label data audits as core mechanism tests.

Completed evidence-bearing batches automatically enter `needs_evidence_analysis`. The Director cannot call `learning-record` for those experiments until the controller attests the blind analysis. Technical failures and interactive debug receipts do not spend a separate analyst turn.

The author's interpretation schema adds:

```json
{
  "schema_version": 2,
  "lane": "scientific",
  "materiality": "branch_material",
  "decision_scope": "branch"
}
```

Allowed materiality values are `nonmaterial`, `branch_material`, and `claim_material`. A nonmaterial qualification plus `continue` never summons a critic.

Failure mining is bounded. After a valid negative or anomaly, perform at most one synthesis pass producing at most two discriminating child candidates. The next action must be an experiment, a Director decision, or a stop.

## Protocol Revisions

Record protocol changes with `protocol-record`. Each revision advances exactly one and includes the scope, claim ceiling, evidence IDs, blockers, warnings, and rationale.

Claim ceilings are:

- `exploratory`: scout only
- `pilot`: integrated pilot and baseline development
- `confirmatory`: frozen claim-facing experiments
- `submission`: central result replicated and audited

Protocol decisions are `authorize_exploratory`, `authorize_pilot`, `freeze_confirmatory`, `narrow_scope`, and `supersede`. The first three map exactly to `exploratory`, `pilot`, and `confirmatory` ceilings; an author cannot declare a stronger ceiling under a weaker decision label.

Do not ask a mechanism critic to approve a protocol revision. Do not use a protocol revision to manufacture support for a hypothesis.

## Director Decisions

Record a `director-decision` after a core signal, material critic, promotion, or circuit-breaker alert. Each decision states:

- current hypothesis and maturity transition
- evidence finding IDs and critic inputs
- causal question and rationale
- positive, negative, mixed, or no core signal
- next discriminating question
- maximum jobs, SU, Codex turns, and protocol diagnostics

The Director must decide after a critic; critics do not mutate the portfolio. After two reviews in one chain, no further critic is launched until the Director changes or closes the branch. The CLI snapshots campaign jobs, committed SU, and agent turns at each decision and blocks further adaptive work when those `next_budget` limits are exhausted; the protocol-diagnostic limit raises a Director-action circuit breaker.

Promotion requires a real core signal. Promotion to claim additionally requires a pilot-authorized protocol. `claim-freeze` requires claim maturity, a core signal, and the matching concept freeze.

## Critic Contract

Every material critic output includes:

```json
{
  "review_kind": "mechanism",
  "objection_severity": "claim_scope",
  "affected_claim": "...",
  "decision_changed": "...",
  "required_test": "one bounded discriminating test",
  "estimated_cost": {
    "jobs": 1,
    "hours": 2,
    "su": 50,
    "persistent_entries": 4
  }
}
```

Severities are:

- `hard_invalidating`: current result cannot answer its registered question
- `claim_scope`: evidence is usable only for a narrower claim
- `future_work`: valuable but unnecessary for the current decision
- `nonblocking`: does not change the next decision

A requested test must name an alternative explanation and the decision changed by either outcome. At most one test may be requested per review.

## Circuit Breakers

`campaign.py status` reports research health. Defaults trigger Director action when:

- no core signal appears within 24 hours and four scientific cells
- technical-invalid interpretations exceed 50% after six results
- more than two protocol diagnostics accumulate without a decision
- workspace inode growth exceeds 256 entries without a core signal
- two critic turns accumulate in one branch chain

Alerts do not pause uncertain science. They force a bounded choice: run one integrated core test, authorize scoped progress, narrow scope, park, kill, or pivot.

Track these meta-metrics in retrospectives:

- time to first core signal
- jobs, turns, SU, and inode growth per scientific decision
- technical-invalid fraction
- reviews per decision
- core-mechanism work versus audit work
- queue wait versus active experiment time

## Claim Graph and Paper

Before completion, record one compact `claim_graph` artifact. Each paper claim links to:

- hypothesis ID and maturity
- supporting and falsifying finding IDs
- experiment IDs and source commits
- protocol revision and scope
- primary literature
- assumptions, threats, and limitations

The central result must be independently reproduced after the protocol and claim are frozen. The writer may synthesize only claims present in this graph. Paper source is English LaTeX; compile it and audit citations and numerical statements.

## Schemas

### Preliminary novelty for `concept-freeze`

```json
{
  "schema_version": 1,
  "hypothesis_id": "candidate-id",
  "mechanism_without_brand": "...",
  "queries": ["exact mechanism", "task-local synonym", "adjacent mechanism"],
  "primary_sources": [
    {
      "title": "...",
      "url": "https://...",
      "checked_locator": "Section 3",
      "mechanism_delta": "..."
    },
    {
      "title": "...",
      "url": "https://...",
      "checked_locator": "Algorithm 1",
      "mechanism_delta": "..."
    }
  ],
  "nearest_work_delta": "...",
  "exact_prior_found": false,
  "decision": "proceed_scout",
  "checked_at": "2026-08-18T00:00:00Z"
}
```

### Protocol revision

```json
{
  "schema_version": 1,
  "protocol_id": "retained-consumer",
  "revision": 1,
  "parent_revision": 0,
  "decision": "authorize_exploratory",
  "claim_ceiling": "exploratory",
  "scope": ["retained examples consumed by the registered evaluator"],
  "hard_blockers": [],
  "warnings": ["excluded relation families are outside current scope"],
  "evidence_ids": ["protocol-check"],
  "rationale": "..."
}
```

### Director decision

```json
{
  "schema_version": 1,
  "decision_id": "promote-row-authority-pilot",
  "hypothesis_id": "candidate-id",
  "decision": "promote",
  "maturity_before": "scout",
  "maturity_after": "pilot",
  "finding_ids": ["integrated-scout-signal"],
  "critic_inputs": [],
  "question": "Does the mechanism change target work on the real path?",
  "rationale": "...",
  "core_signal": "positive",
  "next_question": "Does it beat the competitive baseline without quality loss?",
  "next_budget": {
    "max_jobs": 3,
    "max_su": 1000,
    "max_turns": 8,
    "max_protocol_diagnostics": 1
  }
}
```

### Opportunity scout

```json
{
  "schema_version": 1,
  "role": "systems",
  "round": 1,
  "territory_summary": "...",
  "opportunities": [
    {
      "id": "encoder-boundary-stall",
      "observation": "...",
      "causal_opportunity": "...",
      "differentiating_test": "...",
      "nearest_work_delta": "...",
      "closest_prior_queries": ["..."],
      "estimated_cost": {"jobs": 1, "su": 100, "hours": 2}
    }
  ]
}
```

### Independent analysis

```json
{
  "schema_version": 1,
  "experiment_id": "scout-real-path",
  "hypothesis_id": "candidate-id",
  "validity": "valid",
  "likely_outcome": "qualifies",
  "recommended_lane": "scientific",
  "observed": "...",
  "validity_rationale": "...",
  "causal_assessment": "...",
  "decision_relevance": "...",
  "alternative_explanations": ["..."],
  "threats": ["..."]
}
```

### Claim graph

```json
{
  "schema_version": 1,
  "mission_sha256": "...",
  "route_sha256": "...",
  "research_graph_sha256": "...",
  "claim_hypothesis_id": "candidate-id",
  "central_claim_id": "central-speed-quality-claim",
  "generated_at": "2026-08-18T00:00:00Z",
  "claims": [
    {
      "id": "central-speed-quality-claim",
      "text": "...",
      "status": "supported",
      "evidence_finding_ids": ["confirmatory-main", "independent-reproduction"],
      "experiment_ids": ["main-a100", "replication-a100"],
      "source_commits": ["0123456789abcdef0123456789abcdef01234567"],
      "protocol_revisions": [3],
      "reproduction_experiment_ids": ["replication-a100"],
      "primary_sources": [
        {
          "title": "Closest prior",
          "url": "https://...",
          "checked_locator": "Section 4",
          "supports": "Defines the nearest baseline and remaining mechanism delta."
        }
      ],
      "assumptions": ["Matched hardware and workload scope"],
      "limitations": ["Evidence is limited to the registered model families"]
    }
  ]
}
```

The completion gate verifies all finding, experiment, commit, and protocol links. The central claim must include a valid scientific replication whose outcome matches the declared claim status.
