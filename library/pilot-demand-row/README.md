# pilot-demand-row

Loop Store starter unit (`loop://pilot-demand-row@1.0.0`).

**Goal:** External pilot reactions are logged as source-bound demand rows; dogfood is isolated.

**Verifier command (adapt):** `test -f pilot-log.md && grep -q source_ref pilot-log.md`

Bind into a graph starter or run via local loop package after replacing the verifier with your real gate.
