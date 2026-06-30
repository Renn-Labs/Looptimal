# Oracle Library

The Oracle Library defines sealed domain outcome-oracle patterns for Looptimal. Every acceptance criterion MUST bind to one oracle pattern. This binding is lint-enforced.

An oracle pattern is sealed when its inputs, external check, assertions, and green condition are fixed before execution begins. A loop may produce artifacts, but it may not redefine the oracle after seeing results.

## Pattern Schema

Each oracle pattern uses this shape:

- `id`: stable oracle identifier.
- `capability`: delivery capability or task class.
- `kind`: oracle category.
- `sealed_inputs`: inputs fixed before execution.
- `external_check`: independent check performed by Stage-6 or a delegated verifier.
- `asserts`: concrete facts the oracle proves.
- `green_means`: condition required for acceptance.

## Binding Rule

Every acceptance criterion MUST bind to an oracle pattern.

Lint rule:

1. Read the accepted contract.
2. Extract every acceptance criterion.
3. Confirm each criterion has an `oracle` field or explicit binding reference.
4. Confirm the referenced oracle id exists in this library or in an approved project-local extension.
5. Confirm the oracle has sealed inputs.
6. Reject criteria bound only to raw booleans, free-form reviewer judgment, or unsealed loop-authored checks.

Failure rule:

- Acceptance criterion with no oracle binding: FAIL.
- Acceptance criterion bound to an unknown oracle id: FAIL.
- Acceptance criterion bound to an oracle whose sealed inputs are missing: FAIL.
- Acceptance criterion that relies on raw percentage coverage without changed-branch or mutation relevance: FAIL.

## Oracle Patterns

### 1. Pre-Fix Repro Artifact

- `id`: `pre-fix-repro-artifact`
- `capability`: bug fix, regression fix, incident remediation
- `kind`: repro-first behavioral oracle
- `sealed_inputs`:
  - bug report or failing scenario
  - pre-fix repro command
  - expected failure signature
  - fixed success condition
- `external_check`:
  - run the repro against the pre-fix baseline or preserved failing artifact
  - confirm the expected failure signature appears before the fix
  - run the same repro against the final state
  - confirm the failure is absent and the success condition holds
- `asserts`:
  - the issue was real before the change
  - the delivered state fixes the reproduced failure
  - the check targets the bug rather than only nearby code
- `green_means`:
  - pre-fix artifact fails with the sealed signature
  - final state passes the same scenario
  - no acceptance claim depends only on a self-reported pass

### 2. Pinned Manifest + Parity Matrix

- `id`: `pinned-manifest+parity-matrix`
- `capability`: dependency upgrade, package replacement, runtime migration, API migration
- `kind`: compatibility and dependency-state oracle
- `sealed_inputs`:
  - old manifest and lockfile
  - target manifest and lockfile
  - parity matrix of required behaviors
  - supported runtime versions
- `external_check`:
  - inspect final manifests and lockfiles from disk
  - run install or resolver verification
  - execute parity checks across required runtime versions
  - compare observed behavior to the sealed parity matrix
- `asserts`:
  - dependency state is pinned and reproducible
  - required behaviors are preserved
  - migration did not silently drop supported environments
- `green_means`:
  - final manifest matches target constraints
  - lockfile is reproducible
  - all parity rows pass in required runtimes

### 3. Affected DAG + Behavioral Probes

- `id`: `affected-DAG+behavioral-probes`
- `capability`: refactor, cleanup, internal architecture change
- `kind`: impact-surface behavioral oracle
- `sealed_inputs`:
  - affected dependency graph
  - public interfaces expected to remain stable
  - behavioral probe list
  - excluded files or intentionally changed interfaces
- `external_check`:
  - compute affected DAG from final code
  - run behavioral probes over affected public surfaces
  - compare outputs to baseline or accepted expected changes
- `asserts`:
  - behavior is preserved where required
  - intentional behavior changes are explicit
  - affected surfaces were tested rather than guessed
- `green_means`:
  - every affected required surface has a passing behavioral probe
  - no unapproved public interface drift is detected

### 4. Prod Load + Baseline Band

- `id`: `prod-load+baseline-band`
- `capability`: performance optimization, capacity change, latency reduction
- `kind`: benchmark oracle
- `sealed_inputs`:
  - production-like load profile
  - baseline measurement window
  - allowed variance band
  - target performance threshold
  - environment descriptor
- `external_check`:
  - run the sealed load profile in the declared environment
  - compare results to baseline band
  - verify no required resource or error-rate budget is exceeded
- `asserts`:
  - performance changed under representative load
  - observed improvement is outside noise tolerance
  - optimization did not trade off prohibited reliability metrics
- `green_means`:
  - target metric satisfies threshold
  - result is within or better than accepted baseline band
  - error and resource budgets remain acceptable

### 5. Joint Cost and SLO Window

- `id`: `joint-cost-and-SLO-window`
- `capability`: cost optimization, infra tuning, model-routing change
- `kind`: multi-objective operations oracle
- `sealed_inputs`:
  - cost baseline
  - SLO baseline
  - measurement window
  - allowed cost and SLO thresholds
  - traffic or workload definition
- `external_check`:
  - collect cost data from billing or metering source
  - collect SLO data from monitoring source
  - compare both over the sealed measurement window
- `asserts`:
  - cost movement is real
  - SLO impact is measured at the same time
  - savings do not hide reliability regression
- `green_means`:
  - cost target is met
  - SLO remains within the accepted window
  - both are verified from external systems of record

### 6. Adversarial Variant Corpus

- `id`: `adversarial-variant-corpus`
- `capability`: prompt system, classifier, moderation, extraction, agent policy
- `kind`: robustness oracle
- `sealed_inputs`:
  - representative test corpus
  - adversarial variant corpus
  - expected outputs or scoring rubric
  - minimum pass thresholds
  - prohibited failure classes
- `external_check`:
  - run the final system against the sealed corpus
  - score outputs using deterministic checks or independent evaluator
  - inspect prohibited failure classes
- `asserts`:
  - system handles normal and adversarial variants
  - improvements are not limited to happy paths
  - prohibited failures are absent or below threshold
- `green_means`:
  - required score threshold is met
  - prohibited failure classes do not occur
  - evaluator evidence is reproducible or independently recorded

### 7. Data Invariants + Receipt Crosscheck

- `id`: `data-invariants+receipt-crosscheck`
- `capability`: data migration, ETL, reconciliation, financial or transactional workflow
- `kind`: data correctness oracle
- `sealed_inputs`:
  - source dataset reference
  - destination dataset reference
  - invariant list
  - reconciliation keys
  - external receipt source
- `external_check`:
  - compute invariants on source and destination
  - reconcile records by sealed keys
  - pull receipts from the external system of record
  - compare counts, sums, identities, and exception lists
- `asserts`:
  - data moved or transformed without unauthorized loss
  - exceptions are explicit
  - external receipts support the claimed final state
- `green_means`:
  - all invariants hold
  - receipt crosscheck matches destination state
  - exceptions are accepted in the contract or risk register

### 8. Sealed Holdout + Drift + Shadow Metric

- `id`: `sealed-holdout+drift+shadow-metric`
- `capability`: ML model change, ranking change, prediction system, personalization
- `kind`: model quality oracle
- `sealed_inputs`:
  - holdout dataset
  - drift reference distribution
  - shadow metric definition
  - minimum quality threshold
  - maximum drift threshold
- `external_check`:
  - evaluate final model on sealed holdout
  - compute drift against reference distribution
  - compute shadow metrics from replay or shadow traffic
- `asserts`:
  - model quality satisfies the accepted metric
  - population drift is within tolerance
  - shadow behavior does not reveal hidden regression
- `green_means`:
  - holdout threshold is met
  - drift threshold is not exceeded
  - shadow metric stays within accepted bounds

### 9. Scripted Assistive Tech Journeys

- `id`: `scripted-assistive-tech-journeys`
- `capability`: accessibility, frontend workflow, UI remediation
- `kind`: accessibility journey oracle
- `sealed_inputs`:
  - user journeys
  - target assistive technologies or emulations
  - WCAG or project accessibility criteria
  - viewport and input modality matrix
- `external_check`:
  - run scripted keyboard, screen reader, and semantic checks
  - inspect focus order, labels, roles, names, contrast, and announcements
  - compare against sealed journey expectations
- `asserts`:
  - required journeys are usable without unsupported input assumptions
  - semantic structure supports assistive tech
  - visual and interaction states meet criteria
- `green_means`:
  - every sealed journey completes
  - required accessibility checks pass
  - no critical assistive-tech blocker remains

### 10. Canonical Doc Generation

- `id`: `canonical-doc-generation`
- `capability`: documentation generation, API docs, runbooks, knowledge base updates
- `kind`: documentation fidelity oracle
- `sealed_inputs`:
  - canonical source references
  - required doc sections
  - freshness constraints
  - link and example validation commands
- `external_check`:
  - regenerate or validate docs from canonical sources
  - run link checks
  - run code example checks where applicable
  - compare documented behavior to source-of-truth definitions
- `asserts`:
  - docs reflect canonical sources
  - examples are executable or explicitly marked illustrative
  - stale links and stale claims are detected
- `green_means`:
  - required sections exist
  - source-derived claims match canonical sources
  - links and examples pass validation

### 11. Published Hash + Legal Receipt

- `id`: `published-hash+legal-receipt`
- `capability`: release publication, compliance filing, legal or policy artifact delivery
- `kind`: publication and compliance oracle
- `sealed_inputs`:
  - artifact to publish
  - expected artifact hash
  - publication destination
  - legal or compliance receipt source
  - required metadata
- `external_check`:
  - fetch published artifact from destination
  - hash published artifact
  - pull legal or compliance receipt from system of record
  - compare metadata and timestamps
- `asserts`:
  - the intended artifact was published
  - published bytes match the accepted artifact
  - external legal or compliance system acknowledges receipt
- `green_means`:
  - published hash matches expected hash
  - legal receipt is externally retrievable
  - metadata satisfies the contract

### 12. Causal Control Test

- `id`: `causal-control-test`
- `capability`: experiment, growth change, policy change, causal claim
- `kind`: causal inference oracle
- `sealed_inputs`:
  - treatment definition
  - control definition
  - assignment method
  - primary metric
  - guardrail metrics
  - analysis window
  - minimum detectable effect or decision threshold
- `external_check`:
  - verify assignment integrity
  - compute treatment and control outcomes
  - compute guardrail metrics
  - apply the sealed statistical decision rule
- `asserts`:
  - observed effect is attributable to treatment under the accepted design
  - guardrails did not regress beyond threshold
  - analysis did not move goalposts after seeing results
- `green_means`:
  - assignment is valid
  - primary metric satisfies the decision rule
  - guardrails remain acceptable

### 13. Mutation or Changed-Branch Coverage

- `id`: `mutation-or-changed-branch-coverage`
- `capability`: test coverage, safety net improvement, regression harness
- `kind`: test adequacy oracle
- `sealed_inputs`:
  - changed files or affected branch set
  - mutation targets or changed branches
  - minimum mutation score or branch assertion requirements
  - excluded lines with rationale
- `external_check`:
  - run mutation testing over the sealed target set, or
  - run changed-branch coverage with assertion relevance checks
  - inspect surviving mutants or uncovered changed branches
- `asserts`:
  - tests exercise the changed behavior
  - assertions detect meaningful incorrect behavior
  - coverage is tied to changed logic, not broad raw percentage
- `green_means`:
  - mutation threshold is met with no critical surviving mutants, or
  - changed branches are covered by behaviorally relevant assertions
  - exclusions are justified and accepted

Important rejection rule:

Raw coverage percentage is rejected. A claim such as "85% coverage" is not an oracle result unless it is bound to changed branches, mutation targets, or another behaviorally relevant sealed target set.

## Project-Local Extensions

Projects may add oracle patterns only when the extension is:

- reviewed before execution
- assigned a stable id
- sealed with fixed inputs
- lint-visible
- referenced from the accepted plan
- externally checkable by Stage-6

Project-local oracle extensions must not weaken the global rule: acceptance is proven by hashes, re-execution, live-state reads, and external receipts, never by self-reported booleans.
