---
name: Feature request
about: Suggest an improvement to LoopPrint
title: "[feat] "
labels: enhancement
---

**The problem**
What's missing or painful? Lead with the problem, not the solution.

**Which area**
- [ ] Decision gate / Tier-0 ("is this even a loop?")
- [ ] One of the four atoms (Goal / State / Verifier / Stop)
- [ ] Pattern library / verifier library
- [ ] A tool (lint / detect / doctor / report / skillify / ls)
- [ ] Install / portability / a specific harness

**Proposed approach** (optional)

**Invariant check**
LoopPrint keeps a few hard invariants — does the idea hold them?
- [ ] Stack-agnostic (no hardcoded per-harness matrix)
- [ ] Zero-runtime-dep core (only lint / skillify may use PyYAML)
- [ ] No network / no phone-home
- [ ] maker ≠ checker; never auto-run; no eval-from-spec
