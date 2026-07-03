# Verified loop library — first-party catalog, consumer-side trust

Looptimal ships a **first-party verified loop library** under [`library/`](../library/): installable loop bundles
that meet the same portable contract as any adopter-built loop, plus gates that refuse anything that cannot
execute in the consumer's environment.

Trust is never a stored editorial score. It is a **machine-derived indicator**: lint passes at publish time,
`verify.sh` smoke-runs in the consumer repo at install time, and (separately) a Stage-6 receipt can record a
GREEN live re-run ([`receipt.md`](receipt.md)). Competitors like [loops.show](https://loops.show) and Forward
Future curate prose descriptions or human ratings; our edge is **enforcement at the door**, **runs in your env**,
and **receipts** — not a directory you browse and hope.

> **Core invariant.** Verified means the install CLI smoke-runs the loop verifier in the **consumer repo**, fail-closed
> if it cannot execute there. A loop that only "passes" in the publisher's CI is not verified for you until your
> copy runs.

## Eligibility contract

A loop may appear in `library/` only if its bundle satisfies **all** of the following:

| Requirement | What it means |
|-|-|
| **Real verdict** | `verify.sh` executes to exit 0 (GREEN) or 1–125 (RED) in any repo that has `git` + coreutils — a binary pass/fail, not a hand-written status. |
| **Degrade-to-runnable, never cannot-execute** | Exit codes above 125 mean the gate could not run (missing interpreter, shell error, timeout). Publish-time and install-time gates treat that as **rot**, not a RED loop. |
| **Side-effect-free smoke** | The verifier inspects live state; it must not mutate the consumer repo during a smoke-run (no installs, no commits, no destructive writes as part of the check itself). |
| **Maker ≠ checker** | `verify.sh` is an external gate — it must not invoke `maker.sh`, self-grade, or echo maker output as proof. Same bar as [`loopprint-lint.py`](../scripts/loopprint-lint.py). |
| **Lint GREEN at publish** | `python3 scripts/loopprint-lint.py library/<slug>/loop-spec.yaml` exits 0 before the loop is cataloged. |

Optional niceties (README, `maker.sh` remediation guide) do not substitute for the contract above.

### First shipped loop: `secret-scan`

[`library/secret-scan/`](../library/secret-scan/) is the reference bundle: a `loop-spec.yaml`, an external
`verify.sh` that scans tracked files for committed secret patterns, and a `maker.sh` remediation guide when the
verifier is RED. It demonstrates the full install path without proprietary dependencies.

---

## Install and verify UX — `scripts/loopprint-library.py`

[`scripts/loopprint-library.py`](../scripts/loopprint-library.py) is the consumer-facing CLI. Stdlib + optional
PyYAML; shells out to existing gates (lint, `bash verify.sh`); no network imports.

| Subcommand | Purpose |
|-|-|
| `search [query] [--dir DIR]` | Walk `*/loop-spec.yaml`; substring-match slug, goal, pattern. |
| `verify SLUG_OR_DIR` | Smoke-run `verify.sh` once against the **consumer repo root** (`git rev-parse --show-toplevel`, else cwd). |
| `install SLUG --dest DIR` | Lint-gate → smoke-verify → copy bundle to `DEST/SLUG/` (refuse if destination exists unless `--force`). |

Typical flow:

```bash
python3 scripts/loopprint-library.py search secret
python3 scripts/loopprint-library.py verify secret-scan
python3 scripts/loopprint-library.py install secret-scan --dest ./loops
```

Resolution order for library roots: `--dir` if given, then `./library/`, then the script repo's `library/`.

### Three-way fail-closed classification

Every smoke-run classifies `verify.sh`'s exit code the same way [`run-this-loop.sh`](../templates/run-this-loop.sh)
does for `--check`:

| Verdict | Exit code | Install behavior |
|-|-|-|
| **GREEN** | `0` | Install proceeds; gate passes in this environment. |
| **RED** | `1`–`125` | Install proceeds — RED on arrival is fine; the loop has real work to do. Writes `install-verdict.json`. |
| **cannot-execute** | `> 125` (or missing `verify.sh`) | **REFUSE** — nothing written to `--dest`. Exit 1. |

`install` runs lint **before** smoke-verify. Lint findings refuse immediately — no copy, no verdict file.

`verify` alone prints the classification and returns exit 0 for GREEN or RED (a real verdict), exit 1 only for
cannot-execute.

---

## `install-verdict.json` — local smoke-run, not a receipt

On successful install (GREEN or RED), the CLI writes `DEST/SLUG/install-verdict.json`:

```json
{
  "slug": "secret-scan",
  "verify_exit": 1,
  "verdict": "RED",
  "timestamp": "2026-07-02T12:00:00+00:00",
  "cwd": "/path/to/consumer/repo"
}
```

**Honest scope:** this file is a **local smoke-run result** for the machine that ran `install`. It records one
`verify.sh` exit against the consumer repo root at install time.

It is **explicitly NOT**:

- the HMAC-signed [`looptimal-receipt.json`](receipt.md) emitted by `verify-outcome.py` after a GREEN Stage-6
  live re-run
- a CI-verified adoption badge
- proof that the loop is GREEN in any other environment or at any later time

Do not treat `install-verdict.json` as portable trust evidence. Re-run `verify` or the loop's runner when you need
a current verdict.

---

## Publish-time rot gate — `library-lint` CI

The [`library-lint`](../.github/workflows/ci.yml) job is the catalog's anti-rot gate:

1. `python3 scripts/loopprint-lint.py library/*/loop-spec.yaml` — every first-party spec must lint GREEN.
2. Smoke-run each `library/*/verify.sh` in the publisher repo — exit 0–125 counts as executable; `> 125` fails the
   job.

A loop that drifts to cannot-execute in CI is removed from trust by failure, not by editorial review. Consumer-side
`install` repeats the smoke-run against **your** repo root so trust is bilateral: publish-time executability plus
install-time executability in the environment you actually use.

---

## Trust display — machine-derived, never editorial

When this repo (or a future catalog UI) surfaces "verified" or trust indicators for a library loop, the inputs are
**mechanical only**:

| Signal | Source |
|-|-|
| Spec conforms | `loopprint-lint` GREEN |
| Verifier executes | smoke-run exit ≤ 125 in consumer repo |
| Outcome receipt (optional, separate) | `looptimal-receipt.json` from Stage-6 GREEN per [`receipt.md`](receipt.md) |

There is no stars column, no curator score, no "editor's pick." A loop is trusted to the extent its gates run and
return a real verdict — GREEN or RED — in your environment. RED on install is honest; cannot-execute is refused.

For extending the platform or adding loops in your own repo (outside this catalog), see [`extending.md`](extending.md).