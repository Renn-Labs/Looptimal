# Looptimal Example: Issue 123 to PR Bugfix

This is the one example that round-trips the full pipeline against the outcome-layer's sealed
contract (`contract_hash`) — the other 7 examples are loop-spec-layer only. `contract.yaml`'s hash
is sealed with the HMAC-keyed hash-pin (`DEMO-KEY-NOT-SECRET.hex` in this directory) rather than
the older unkeyed sha256, so it also demonstrates that mode end-to-end — see the root
[`README.md`](../../README.md#verify-it-yourself) for the runnable commands, and
[`SECURITY.md`](../../SECURITY.md) for what the keyed mode actually closes. **The key in this
directory is a fixed, all-zero demo value, loudly non-secret by construction — never reuse it. A
real mission generates a fresh key via `secrets.token_bytes(32)` and never commits it to a repo.**

## Stage 0: Contract

The run starts with `contract.yaml`.

Objective: fix issue 123, where `GET /api/projects/{id}` returns HTTP 500 instead of HTTP 404 when a missing project is requested after cache warmup.

The contract is checkpoint-autonomous and declares no irreversible actions.

## Stage 1: Sealed Oracle

The framer seals the acceptance suite around a pre-fix repro artifact.

The primary oracle is:

`pytest tests/api/test_project_lookup.py::test_missing_project_after_cache_warmup_returns_404`

Before the fix, this test is RED because the endpoint returns HTTP 500.

## Stage 2: Mission

`mission.yaml` creates one task lane:

- Lane: `L1`
- Archetype: `task`
- Capability: `backend-api`
- Verifier shape: `gate`

The stop condition is strict: C1, C2, and C3 must all be GREEN.

## Stage 3: Reproduce

The loop runs the sealed repro before implementation.

Receipt R1 records:

- Command: `pytest tests/api/test_project_lookup.py::test_missing_project_after_cache_warmup_returns_404`
- Result: RED
- Meaning: issue 123 is real and reproducible.

## Stage 4: Isolate

The executor inspects the project lookup path.

Finding: a missing cached project raises `KeyError` after cache warmup. The generic exception handler converts that into HTTP 500.

Expected behavior already exists on the cold lookup path through the `ProjectNotFound` domain exception.

## Stage 5: Fix

The minimal fix changes only backend project lookup handling.

The fixed route converts the missing-project cache miss into `ProjectNotFound`, preserving the shared error serializer and request metadata.

No database migration, production deploy, or external mutation is performed.

## Stage 6: Harden

A pre-mortem catches a risky false green: a broad `KeyError` catch would make the repro pass while incorrectly converting cache backend outages into HTTP 404.

The oracle is hardened with adjacent project API checks:

`pytest tests/api/test_project_lookup.py tests/api/test_project_cache.py`

This becomes acceptance criterion C2.

## Stage 7: Verdict

The final re-run checks are:

- C1: `pytest tests/api/test_project_lookup.py::test_missing_project_after_cache_warmup_returns_404` -> GREEN
- C2: `pytest tests/api/test_project_lookup.py tests/api/test_project_cache.py` -> GREEN
- C3: `pytest` -> GREEN

`evidence-bundle.json` records the artifacts, receipts, acceptance results, final state assertion, and persisted verdict reference.

`outcome-verdict.json` declares the result GREEN because all sealed acceptance criteria pass and no irreversible actions were performed.
