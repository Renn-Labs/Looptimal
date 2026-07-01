# Rotate the CI signing key

## Summary
Replaces the expiring GitHub Actions signing key with a new one, keeping the same trust chain.

## Risks
A brief window where old and new keys are both valid; bounded to the rotation PR's lifetime.

## Rollback
Revert the PR; the old key remains valid until its original expiry, so no hard cutover risk.
