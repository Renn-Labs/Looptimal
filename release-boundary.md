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

> **Status note (updated 2026-06-30):** The repository `Renn-Labs/Looptimal` is **public** and `main`
> ships the full v2.0.0 rebrand + orchestrator (name, pipeline, `marketplace.json`/`plugin.json`
> framing). **v2.0.0 is now tagged and released** (`e6fc04b`, SSH-signed, GitHub Release live). This
> document ratifies the v2.0.0 surface so the ledger matches reality; it does **not** itself authorize
> the public announcement — that remains a separate maintainer "go."

---

## v1.1.0 — LoopPrint (in effect; tagged + released 2026-06-28)

- **OPEN:** the loop-design wizard, the four-atom blueprint generator, runtime/observability scripts,
  rot radar, binding-aware install, doctor/lint. MIT. This is the clean, fully-ledgered surface.
- **WITHHELD:** none — 1.x contained no orchestrator material.
- **Disclosed residual:** the planned cryptographic framer hash-pin for the sealed contract was
  named as future hardening (see `SECURITY.md`), not claimed as shipped.

**Boundary sign-off (v1.1.0):**  ☑ signed  ·  maintainer: **Erik Ford (Renn Labs)**  ·  date: **2026-06-30**

---

## v2.0.0 — Looptimal (tagged + released 2026-06-30, ratified)

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

## v2.1.0 — Looptimal (pending tag)

What changed: everything in `CHANGELOG.md [2.1.0]` — the cryptographic sealed-contract hardening
(HMAC-SHA256 keyed mode + sealed-tree materials manifest), the checker-only visibility tier,
hard/soft gate labeling, structured critic verdicts, judge-calibration + two new oracles, packaging
(`pyproject.toml`/`looptimal_cli/`), `looptimal-persona-promote.py`, the demo asset, the 20-item
roadmap, `references/receipt.md`, and the `SKILL.md` single-pass mode fork. Unlike v2.0.0 (which
absorbed a previously-private codebase), **every line here was authored directly on this public
repo's `main` branch** — there is no separate, unpublished source this release draws from.

- **OPEN (confirm):**
  - The cryptographic framer hash-pin (`--key-file` / `LOOPTIMAL_FRAMER_KEY`) and sealed-tree
    materials manifest — `scripts/_common.py`, adversarially reviewed per the Review gate below.
  - Checker-only visibility tier, hard/soft gate labeling, structured critic verdicts, judge
    calibration, the two new oracle patterns — `scripts/looptimal-lint.py`, `templates/`,
    `references/oracle-library.md`.
  - Packaging (`pyproject.toml`, `looptimal_cli/`), `looptimal-persona-promote.py`, the demo asset,
    `ROADMAP.md`, `references/receipt.md`, and the `SKILL.md` mode-fork / single-pass mode.
- **WITHHELD / proprietary:** **None.** No component of this release was absorbed from a private
  source — it is new work authored on public `main`, same as the rest of the repo's history since
  the v2.0.0 rebrand. — confirmed by the maintainer, 2026-07-01.
- **Disclosed residual:** unchanged in kind, narrower in scope. Unkeyed mode (the default) still
  carries the same residual as v2.0.0/v1.1.0: OS-permission sealing only, recomputable by anyone who
  can write `sealed/`. The keyed HMAC mode (new this release) closes the recompute-after-tamper gap
  and is adversarially verified per the Review gate below; its own residual is key custody — the
  framer key must live outside every maker-writable root, or the guarantee it provides doesn't hold.
  Not marketed as fully tamper-proof in either mode.

**Boundary sign-off (v2.1.0):**  ☑ confirmed  ·  maintainer: **Erik Ford (Renn Labs)**  ·  date: **2026-07-01**

---

## Reconcile checklist (v2.1.0) — gated on the sign-off above

1. ☑ Maintainer confirms the **WITHHELD** section (nothing this release should have stayed private).
   2026-07-01.
2. ☑ `release-boundary.md` v2.1.0 block **signed** (verifiable attestation = the `git commit -s`
   updating this file under the maintainer's identity).
3. ☑ Ran the `RELEASE.md` offline gates + hazard scan from a clean tree — all GREEN/HEALTHY, hazard
   scan matches reviewed and confirmed pre-existing/benign (no new secrets, local paths, or private
   references). 2026-07-01.
4. ☑ Adversarial review of the enforcement scripts for gaming bypasses (`looptimal-lint.py`,
   `verify-outcome.py`, `_common.py`) — found and BLOCKed on a real, exploit-tested bypass (the
   framer HMAC key leaked into every oracle subprocess's environment via `safe_env()`, in exactly
   the documented CI-recommended key-delivery mode); fixed with an exploit-tested `--selftest`
   proving closure, plus 3 related hardening fixes from the same pass. A follow-up confirmation
   review then caught one regression the fix itself introduced (a crash on non-ASCII maker input)
   and that was fixed too. Final verdict: sufficient to unblock. 2026-07-01.
5. ☑ Tagged **`v2.1.0`** (SSH-signed, `cf533c2`) and cut the GitHub Release. 2026-07-01.
6. ☑ **Post-release falsification** (mandatory, not just pre-release): from a genuinely fresh temp
   dir, `uvx --from git+...@v2.1.0 verify-outcome --selftest` → `SELFTEST GREEN`; a fresh
   `git clone --branch v2.1.0` running README's full "Verify it yourself" block (incl. the
   `--key-file` example that also failed at the old tag) → all green. The bug this release exists
   to fix is confirmed closed, not just asserted. 2026-07-01.
7. ☐ **Separate maintainer "go"** before publishing any announcement referencing v2.1.0
   specifically (the existing v2.0.0 announcement gate above is unaffected/still open) — launch
   copy is drafted (`.omc/plans/launch-kit/`) but nothing has been posted.

---

## Reconcile checklist (v2.0.0) — gated on the sign-off above

1. ☑ Maintainer confirms the **WITHHELD** section (nothing from LoopOptimal should have stayed private). — Erik Ford, 2026-06-30
2. ☑ `release-boundary.md` v2.0.0 block **signed** (verifiable attestation = the `git commit -s` adding this file).
3. ☑ Run the `RELEASE.md` offline gates + hazard scan from a clean tree (RELEASE.md de-staled in PR #18). — all GREEN profile-clean, 2026-06-30
4. ☑ Tag **`v2.0.0`** and cut the GitHub Release (body = `CHANGELOG.md [2.0.0]`; see
   `release-notes-v2.0.0.md`). Closed the phantom-version gap. — tag `e6fc04b` (SSH-signed) + Release live, tag CI green, 2026-06-30
5. ☑ Fix the GitHub repo **description** (now reads "Looptimal — turn an objective into a delivered, VERIFIED outcome…"). — 2026-06-30
6. ☐ **Only then** — separate maintainer "go" — publish the announcement / reply referencing Looptimal.

Items 1–5 are complete and signed; the v2.0.0 surface is ratified and live. Item 6 (the public
announcement / reply referencing Looptimal) remains **open**, gated on a separate maintainer "go" —
until that go, the public-facing reply surface holds at the ratified release.
