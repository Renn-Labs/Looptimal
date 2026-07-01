# Deploy the new cache layer

## Summary
Adds a read-through cache in front of the project lookup API to cut p95 latency.

## Risks
Cache staleness on rapid project renames; mitigated with a 30s TTL.

## Rollback
Feature-flagged; disabling the flag reverts to the direct-lookup path with no data migration.
