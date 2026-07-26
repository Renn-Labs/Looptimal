# product-slice-ship

Loop Store starter unit (`loop://product-slice-ship@1.0.0`).

**Goal:** A framed product slice is committed on an isolated branch without sweeping concurrent work.

**Verifier command (adapt):** `git status --porcelain | test -z "$(cat)"`

Bind into a graph starter or run via local loop package after replacing the verifier with your real gate.
