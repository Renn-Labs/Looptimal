# Looptimal Worked Simulation: Issue 123 Bugfix

## Scenario

Issue 123 reports that `GET /api/projects/{id}` returns HTTP 500 when the project is missing and the project cache has already been warmed. The expected behavior is HTTP 404 with a stable JSON error body.

The loop runs as a MORTY-style task archetype:

1. Reproduce.
2. Isolate.
3. Hypothesize.
4. Minimal fix.
5. Verify against the repro.
6. Verify adjacent behavior.
7. Persist evidence.

## Path 1: Straight-line success

### Iteration 1

The framer seals a pre-fix repro artifact:

- Check: `pytest tests/api/test_project_lookup.py::test_missing_project_after_cache_warmup_returns_404`
- Pre-fix result: RED
- Observed failure: HTTP 500
- Expected result after fix: HTTP 404 with `{"error":{"code":"PROJECT_NOT_FOUND"}}`

The executor inspects the backend route and finds that cache misses after warmup raise `KeyError`, which is caught by the generic exception handler and converted to HTTP 500.

The minimal fix changes the route-level miss handling so a missing cached project is converted to the same `ProjectNotFound` domain exception used by the cold lookup path.

Verification:

- C1: GREEN
- C2: GREEN
- C3: GREEN

Outcome: Accepted.

## Path 2: Pre-mortem catches adjacent regression

### Pre-mortem risk

Before accepting the minimal fix, the checker asks what could go wrong if only the sealed repro is run.

Identified risk:

The fix could make the issue-123 repro pass while changing adjacent behavior for cache invalidation, especially the case where a project exists, is deleted, and then is requested again after cache refresh.

### Failed candidate

A candidate patch catches every `KeyError` in the project route and returns 404.

The repro passes:

- `pytest tests/api/test_project_lookup.py::test_missing_project_after_cache_warmup_returns_404`
- Result: GREEN

But an adjacent test fails:

- `pytest tests/api/test_project_cache.py::test_cache_backend_error_is_reported_as_503`
- Result: RED
- Failure: backend cache outage is incorrectly converted to HTTP 404

### Hardening

The sealed oracle is hardened by adding the adjacent project API suite as criterion C2:

- `pytest tests/api/test_project_lookup.py tests/api/test_project_cache.py`

The patch is revised so only domain-level missing-project misses become 404. Cache backend failures still surface as HTTP 503.

Verification after hardening:

- C1: GREEN
- C2: GREEN
- C3: GREEN

Outcome: Accepted.

## Path 3: Full-suite protection

### Iteration 2

A narrower fix passes C1 and C2 but fails the full suite because one integration test expects the shared error serializer to include `request_id`.

Failed check:

- `pytest`
- Result: RED
- Failing test: `tests/integration/test_error_envelope.py::test_project_not_found_error_includes_request_id`

The fix is adjusted to raise the existing `ProjectNotFound` exception instead of constructing a route-local JSON response.

Final verification:

- `pytest tests/api/test_project_lookup.py::test_missing_project_after_cache_warmup_returns_404`: GREEN
- `pytest tests/api/test_project_lookup.py tests/api/test_project_cache.py`: GREEN
- `pytest`: GREEN

Outcome: Accepted with full evidence.
