# Evidence Bundle DoD

`evidence-bundle.json` is the Stage-6 proof artifact for Looptimal delivery. It is not accepted because the loop wrote it. It is accepted only when Stage-6 can externally verify every material claim through hashes, re-execution, live-state reads, or independently obtained receipts.

Stage-6 rule: trust hashes and re-execution, never self-reported booleans.

## Required Fields

1. `contract_ref`
2. `contract_hash`
3. `accepted_plan_ref`
4. `artifacts[]`
5. `tool_receipts[]`
6. `verifier_trace[]`
7. `acceptance_results[]`
8. `final_state_assertion`
9. `unresolved_risks[]`
10. `persisted_state_update_ref`

Although the bundle contains ten top-level keys, the Definition of Done has nine verification obligations because `contract_ref` and `contract_hash` are checked together as the contract integrity obligation.

## 1. Contract Integrity: `contract_ref` + `contract_hash`

Purpose: prove the delivered outcome still targets the same objective and acceptance contract that Stage-0 accepted.

Required shape:

- `contract_ref`: stable path, URI, commit-addressed file reference, or immutable artifact locator for the accepted contract.
- `contract_hash`: SHA-256 hash of the contract bytes at `contract_ref`.

Stage-6 external check:

1. Read the contract from `contract_ref`.
2. Recompute SHA-256 over the exact bytes.
3. Compare the recomputed hash to `contract_hash`.

Failure rule:

- Hash mismatch is a hard FAIL.
- Treat mismatch as goal drift, even when the text appears semantically similar.
- Do not accept loop-authored explanations for a mismatch.

Green means:

- `contract_ref` resolves.
- Recomputed SHA-256 equals `contract_hash`.
- The referenced contract contains the objective, acceptance criteria, constraints, and stop condition used by the run.

## 2. Accepted Plan: `accepted_plan_ref`

Purpose: prove the loop ran against the plan accepted after design and war-game stages.

Required shape:

- `accepted_plan_ref`: stable path, URI, commit-addressed file reference, or immutable artifact locator for the accepted plan.

Stage-6 external check:

1. Read `accepted_plan_ref` from disk or the external artifact store.
2. Confirm it references the same `contract_hash`.
3. Confirm it contains the selected loop design, verifier bindings, stop conditions, and risk controls.
4. Confirm the plan was accepted before execution artifacts were produced.

Failure rule:

- Missing plan is FAIL.
- Plan that does not bind to the contract hash is FAIL.
- Plan timestamp or provenance after execution evidence is FAIL unless explicitly marked as a post-run amendment with a separate accepted amendment record.

Green means:

- The accepted plan is retrievable.
- It binds to the verified contract.
- It predates or formally controls the execution evidence.

## 3. Artifacts: `artifacts[]`

Purpose: prove claimed deliverables exist exactly as reported.

Required shape per artifact:

- `path`: repo-relative path or external immutable artifact locator.
- `sha256`: SHA-256 hash of the artifact bytes.

Stage-6 external check:

1. For each artifact, read the file from disk or the external artifact locator.
2. Recompute SHA-256 over the exact bytes.
3. Compare recomputed hash to the recorded `sha256`.

Failure rule:

- Missing artifact is FAIL.
- Hash mismatch is FAIL.
- Generated summaries of artifacts are not evidence.
- A loop-authored manifest is not enough unless every artifact in it is re-hashed against disk or the external store.

Green means:

- Every declared artifact exists.
- Every declared artifact hash matches the bytes Stage-6 reads independently.

## 4. Tool Receipts: `tool_receipts[]`

Purpose: prove tools or external systems produced the claimed evidence.

Required shape per receipt:

- `cmd`: exact command or external operation identifier.
- `exit`: process exit code or external operation status.
- `stdout_sha`: SHA-256 hash of captured stdout or canonical external response body.
- `ts`: timestamp in ISO-8601 UTC.

Stage-6 external check:

For idempotent commands:

1. Re-run the command in the declared environment or controlled equivalent.
2. Capture stdout.
3. Hash stdout.
4. Compare exit code and stdout hash to the recorded receipt.

For non-idempotent sends or mutations:

1. Do not trust a loop-authored receipt file.
2. Re-pull the write-back receipt from the external system of record.
3. Hash the canonical external response body.
4. Compare the external receipt to the claimed operation, timestamp window, and expected final state.

Failure rule:

- Idempotent command cannot be re-run and has no accepted reason: FAIL.
- Re-run exit code mismatch: FAIL.
- Re-run stdout hash mismatch: FAIL unless the accepted oracle explicitly allows a normalized dynamic field set.
- Non-idempotent send with only a local loop-authored receipt: FAIL.
- Non-idempotent send without external write-back confirmation: FAIL.

Green means:

- Idempotent receipts reproduce.
- Non-idempotent receipts are re-pulled from the external system of record.
- Receipt evidence supports, but does not replace, artifact and acceptance checks.

## 5. Verifier Trace: `verifier_trace[]`

Purpose: preserve diagnostic history of verifier attempts, failures, retries, and fixes.

Stage-6 external check:

1. Read the trace for chronology and debugging context.
2. Confirm trace entries correspond to actual receipt, artifact, or acceptance evidence where they make material claims.
3. Treat trace as advisory only.

Failure rule:

- Do not pass a run because `verifier_trace[]` says it passed.
- Do not trust self-reported verifier booleans.
- A trace entry with no external receipt, artifact hash, or live check is non-binding.

Green means:

- Trace is internally coherent.
- Trace helps explain how evidence was produced.
- No material acceptance claim depends only on the trace.

## 6. Acceptance Results: `acceptance_results[]`

Purpose: map each acceptance criterion to the oracle that proves it.

Required shape per result:

- `criterion`: exact acceptance criterion identifier or text.
- `oracle`: bound oracle pattern id from `references/oracle-library.md`.
- `passed_by`: external evidence reference, command receipt, live-state query, artifact hash, or external system receipt.
- `value`: measured value, normalized observation, or canonical result.

Stage-6 external check:

1. For every acceptance criterion in the contract, find exactly one or more corresponding acceptance result entries.
2. Confirm every entry binds to an oracle pattern.
3. Re-run the oracle check or re-pull the external state required by the oracle.
4. Compare the observed value to the criterion threshold.
5. Ignore self-reported `passed` booleans if present.

Failure rule:

- Missing criterion coverage is FAIL.
- Criterion without oracle binding is FAIL.
- Oracle cannot be re-run or externally checked: FAIL unless the accepted plan explicitly defines a sealed non-repeatable external receipt pattern.
- Re-run result does not satisfy the criterion: FAIL.

Green means:

- Every criterion is covered.
- Every criterion binds to a sealed oracle pattern.
- Stage-6 independently re-runs or externally verifies the result.

## 7. Final State Assertion: `final_state_assertion`

Purpose: state the final delivered condition in terms that can be compared against live state.

Stage-6 external check:

1. Parse the assertion into concrete state claims.
2. Query live disk, repo, service, database, deployment, registry, or external system state as applicable.
3. Compare live state to the assertion.
4. Confirm live state also satisfies the accepted acceptance criteria.

Failure rule:

- Assertion cannot be mapped to live checks: FAIL.
- Live state contradicts assertion: FAIL.
- Assertion is true only in generated files but false in the system of record: FAIL.

Green means:

- Final assertion is concrete.
- Live state matches it.
- Live state satisfies the contract.

## 8. Unresolved Risks: `unresolved_risks[]`

Purpose: prevent quiet burial of known residual risk.

Stage-6 external check:

1. Read risks from the evidence bundle.
2. Read risks from the analyze stage, war-game stage, review findings, and verifier failures.
3. Cross-check whether every still-relevant analyze-stage risk is either resolved with evidence or carried into `unresolved_risks[]`.
4. Confirm each unresolved risk has an owner, impact, likelihood, mitigation, and acceptance rationale where applicable.

Failure rule:

- Analyze-stage risk disappears without evidence: FAIL.
- Known unresolved risk omitted from the bundle: FAIL.
- Risk marked resolved without external proof: FAIL.
- Risk acceptance that violates the contract constraints: FAIL.

Green means:

- Residual risks are complete relative to earlier analysis.
- Resolved risks have evidence.
- Unresolved risks are explicit and compatible with the contract.

## 9. Persisted State Update: `persisted_state_update_ref`

Purpose: prove the loop wrote durable state so future runs do not reset context or repeat known failures.

Required shape:

- `persisted_state_update_ref`: path, URI, commit-addressed file reference, database key, issue comment, or external state locator.

Stage-6 external check:

1. Read the persisted state from `persisted_state_update_ref` after the run completes.
2. Confirm it contains the contract hash, accepted plan reference, verifier outcome, artifact references, unresolved risks, and next-run guidance.
3. Confirm the state write is durable in the expected store.
4. Confirm read-after-write behavior by retrieving the state through the same surface future runs will use.

Failure rule:

- Missing state update is FAIL.
- State exists only in transient logs: FAIL.
- State cannot be read after write: FAIL.
- State does not bind to the contract hash: FAIL.

Green means:

- Persisted state is durable.
- It is readable through the future-run surface.
- It binds to the verified delivery evidence.

## Stage-6 Acceptance Algorithm

1. Load `evidence-bundle.json`.
2. Validate required top-level fields.
3. Recompute `contract_hash` from `contract_ref`.
4. Read `accepted_plan_ref` and verify contract binding.
5. Re-hash every artifact against disk or external storage.
6. Re-run idempotent tool receipts.
7. Re-pull non-idempotent write-back receipts from external systems.
8. Treat `verifier_trace[]` as advisory context only.
9. Re-run every acceptance oracle in `acceptance_results[]`.
10. Compare `final_state_assertion` against live state.
11. Cross-check `unresolved_risks[]` against analyze-stage risks.
12. Read `persisted_state_update_ref` after write.
13. Pass only if every hard check is green.

## Non-Acceptance Rules

The following never satisfy Stage-6 by themselves:

- A boolean field saying `"passed": true`.
- A loop-authored receipt for an external mutation.
- A screenshot without an oracle that defines what is being asserted.
- A trace line saying a verifier passed.
- A generated summary of test output.
- A stale artifact hash from before final edits.
- A risk list that is not cross-checked against earlier analysis.
- A persisted-state path that cannot be read after write.

## Minimal Bundle Skeleton

{
  "contract_ref": "contracts/objective.md",
  "contract_hash": "sha256:<hex>",
  "accepted_plan_ref": "plans/accepted-plan.md",
  "artifacts": [
    {
      "path": "relative/path/to/artifact",
      "sha256": "sha256:<hex>"
    }
  ],
  "tool_receipts": [
    {
      "cmd": "command or external-operation-id",
      "exit": 0,
      "stdout_sha": "sha256:<hex>",
      "ts": "2026-06-28T00:00:00Z"
    }
  ],
  "verifier_trace": [],
  "acceptance_results": [
    {
      "criterion": "criterion-id",
      "oracle": "oracle-pattern-id",
      "passed_by": "receipt-or-live-check-ref",
      "value": "observed-value"
    }
  ],
  "final_state_assertion": "Concrete live-state assertion.",
  "unresolved_risks": [],
  "persisted_state_update_ref": ".omx/state/looptimal/<run-id>.json"
}
