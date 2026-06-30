<!-- Human-readable ratification record. The verifiable attestation is the `git commit -s` that
     adds this file under the maintainer's identity. Before committing, the maintainer MUST confirm
     the WITHHELD lines below are true. -->
<!-- Maintainer of record: Erik Ford · Renn Labs (organization). -->

> **⚠️ Before you `git commit -s` this file:** confirm the **v2.0.0 WITHHELD = None** line is correct.
> By signing you attest that nothing in the absorbed LoopOptimal orchestrator was meant to stay
> proprietary. If anything was, name it and pull it from public `main` *before* signing.

# Release Disclosure Boundary

Authoritative record of what is **OPEN** (public, MIT) versus **WITHHELD** (proprietary / not
disclosed) at each released version, plus the honestly-disclosed residual. The marketing/announcement
surface may only assert what this document marks OPEN **and signed** for the version being referenced.

> **Status note (2026-06-30):** The repository `Renn-Labs/Looptimal` is **public** and `main` already
> ships the full v2.0.0 rebrand + orchestrator (name, pipeline, `marketplace.json`/`plugin.json`
> framing). The last *tagged release* is **v1.1.0 (LoopPrint)**. This document ratifies the v2.0.0
> surface so the ledger matches reality; it does **not** itself authorize the public announcement —
> that remains a separate maintainer "go."

---

## v1.1.0 — LoopPrint (in effect; tagged + released 2026-06-28)

- **OPEN:** the loop-design wizard, the four-atom blueprint generator, runtime/observability scripts,
  rot radar, binding-aware install, doctor/lint. MIT. This is the clean, fully-ledgered surface.
- **WITHHELD:** none — 1.x contained no orchestrator material.
- **Disclosed residual:** the planned cryptographic framer hash-pin for the sealed contract was
  named as future hardening (see `SECURITY.md`), not claimed as shipped.

**Boundary sign-off (v1.1.0):**  ☑ signed  ·  maintainer: **Erik Ford (Renn Labs)**  ·  date: **2026-06-30**

---

## v2.0.0 — Looptimal (LIVE on `main`, AWAITING tag + ratification)

What changed: the previously-private **LoopOptimal** orchestrator was absorbed into this repo as a
single product (`CHANGELOG.md [2.0.0]`). Everything below is **already public on `main`**.

- **OPEN (confirm):**
  - Outcome-orchestration pipeline — `SKILL.md`, `references/pipeline.md` (the 0→7 stages, incl. the
    "sealed acceptance suite", Simulate/war-game, maker ≠ checker, Stage-6 separate verifier).
  - Enforcement scripts — `looptimal-lint.py`, `verify-outcome.py`, `_common.py`, `looptimal-detect.py`.
  - Agent Foundry — `references/agent-foundry.md`, `personas/`.
  - The sealing model and its **disclosed residual** (already public in `SECURITY.md`).
  - Brand/manifests — name, logo, `marketplace.json`, `plugin.json` (v2.0.0).
- **WITHHELD / proprietary:** **None.** The absorbed LoopOptimal orchestrator is published in full
  under MIT on public `main`; no component is withheld. The only undisclosed-but-named item is the
  *planned* cryptographic framer hash-pin (future work, not yet built) — see the disclosed residual
  below. — ratified **Erik Ford (Renn Labs), 2026-06-30**
- **Disclosed residual:** the cryptographic framer hash-pin remains *planned, not shipped*. The
  irreducible trust root is OS filesystem permissions + the checker controlling `--workdir`
  (`SECURITY.md`). Not marketed as fully tamper-proof. ✅ already disclosed honestly.

**Boundary sign-off (v2.0.0):**  ☑ signed  ·  maintainer: **Erik Ford (Renn Labs)**  ·  date: **2026-06-30**

---

## Reconcile checklist (v2.0.0) — gated on the sign-off above

1. ☑ Maintainer confirms the **WITHHELD** section (nothing from LoopOptimal should have stayed private). — Erik Ford, 2026-06-30
2. ☑ `release-boundary.md` v2.0.0 block **signed** (verifiable attestation = the `git commit -s` adding this file).
3. ☐ Run the `RELEASE.md` offline gates + hazard scan from a clean tree (RELEASE.md de-staled in PR #18).
4. ☐ Tag **`v2.0.0`** and cut the GitHub Release (body = `CHANGELOG.md [2.0.0]`; see
   `release-notes-v2.0.0.md`). This closes the phantom-version gap (manifests say 2.0.0, no tag exists).
5. ☐ Fix the GitHub repo **description** (still reads "LoopPrint — an interactive wizard…").
6. ☐ **Only then** — separate maintainer "go" — publish the announcement / reply referencing Looptimal.

Until 1–5 are complete and signed, the public-facing reply surface stays **LoopPrint v1.1.0 + the
verifier thesis** (the last ratified release).
