# beachhead-job-select

Loop Store starter unit (`loop://beachhead-job-select@1.0.0`).

**Goal:** One segment and one recurring job are written with J1 definition and a 14-day kill rule.

**Verifier command (adapt):** `test -f beachhead-packet.md && grep -q J1 beachhead-packet.md`

Bind into a graph starter or run via local loop package after replacing the verifier with your real gate.
