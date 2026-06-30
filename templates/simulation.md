# Looptimal War-Game Simulation Output
# Generated in Simulate phase (before human GO). Fill all sections; do not execute until hardened.

**Mission:** {{MISSION_ID}}
**Contract hash:** {{CONTRACT_HASH}}
**Simulation horizon (N steps):** {{N_STEPS}}
**Date:** {{ISO_TIMESTAMP}}

---

## Top-K execution paths (ranked by likelihood × impact)

| Rank | Path ID | Summary | Likelihood | Impact if wrong | Verdict |
|------|---------|---------|------------|-----------------|---------|
| 1 | PATH-A | {{one-line path description}} | high | high | proceed-with-guards |
| 2 | PATH-B | {{one-line path description}} | medium | high | harden-first |
| 3 | PATH-C | {{one-line path description}} | low | critical | block-without-go |

_Add rows until K paths are enumerated._

---

## Per-path N-step rollout

### PATH-A — {{path title}}

| Step | Actor | Action | Expected state | Failure signal | Rollback / checkpoint |
|------|-------|--------|----------------|----------------|------------------------|
| 1 | {{domain}} | {{action}} | {{state}} | {{signal}} | {{rollback}} |
| 2 | {{domain}} | {{action}} | {{state}} | {{signal}} | {{rollback}} |
| 3 | {{domain}} | {{action}} | {{state}} | {{signal}} | {{rollback}} |
| … | … | … | … | … | … |
| N | verifier | Re-run sealed suite vs live | GREEN only if external | self-report GREEN | freeze + human GO |

_Repeat this subsection for each ranked path (PATH-B, PATH-C, …)._

---

## Pre-mortem (failure modes before execution)

| ID | Failure mode | Root cause | Early warning | Oracle that catches it | Severity | Mitigation |
|----|--------------|------------|---------------|------------------------|----------|------------|
| PM-01 | Reward-hacking via quarantine | Scope shrink | Denominator drop | oracle-main-pass-rate-7d | high | Freeze critical-path manifest |
| PM-02 | Stale staging / env drift | External state lag | Receipt timestamp skew | external_write_back | high | Fresh runner + live API pull |
| PM-03 | Flaky verifier false GREEN | Nondeterminism | 1/5 runs fail | oracle-flake-stress-5x | medium | Quorum repeat |
| PM-04 | Irreversible merge without GO | Autonomy leak | irreversible flag set | human_go_gate | critical | Block task until GO recorded |
| PM-05 | Context rot long horizon | State not persisted | Repeated re-work | persisted_state_update_ref | medium | Checkpoint durable state each iter |

---

## Plan-hardening actions (apply before human GO)

- [ ] {{hardening item — e.g. pin sealed_inputs hash in mission.yaml}}
- [ ] {{hardening item — e.g. add quorum repeat to flaky oracle}}
- [ ] {{hardening item — e.g. split irreversible task behind explicit GO trigger}}
- [ ] {{hardening item — e.g. add idempotency key to tool receipts}}
- [ ] {{hardening item — e.g. reject path if meta-loop detected}}

**Simulation verdict:** {{GO | NO-GO | GO-with-conditions}}
**Conditions (if any):** {{list}}
