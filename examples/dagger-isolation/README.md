# Optional: Dagger Container-Use isolation for maker ≠ checker

Looptimal's disclosed security model (`SECURITY.md`) is honest that its anti-tamper trust rests on
OS filesystem permissions plus the checker controlling `--workdir` — a **process-level**
separation (maker and checker are different agent invocations), not an **infrastructure-level**
one (nothing stops the maker's process from, say, reading the checker's environment if they
happen to share a machine and a permission model badly). This example shows an optional pattern
that closes that gap: run the Execute-stage maker and the Verify-outcome-stage checker in
*separate, isolated containers* instead of separate processes on the same host.

## Why Dagger Container-Use, specifically

[Dagger's Container-Use](https://dagger.io/blog/agent-container-use) gives each agent its own
isolated, git-branch-backed containerized environment — the same environment an agent uses
locally is what CI runs, and each container's changes land on its own git branch. That maps
cleanly onto Looptimal's own model: the maker's container is one branch/environment, the
checker's is a completely separate one, and neither can read or write the other's filesystem,
process list, or environment variables. This turns maker ≠ checker from "a convention we trust
the operator to follow" into something the container boundary enforces mechanically.

## How this composes with Looptimal — the actual integration point

This is **strictly opt-in and additive** — it changes nothing about Looptimal's core, which stays
stdlib-only with zero network calls and zero knowledge of Dagger. The integration point is exactly
where you'd expect: `profile.yaml`'s existing `dispatch.maker` / `dispatch.checker` fields
(`references/profiles.md`) already exist to name "how this harness runs the maker step" and "how
it runs an independent checker" — pointing those at Dagger-isolated invocations instead of
in-process ones is the entire change. No script under `scripts/*.py` needs to know Dagger exists.

```yaml
# ~/.looptimal/profile.yaml (illustrative — adapt to your Dagger/Container-Use version; consult
# Dagger's current docs for exact CLI syntax, which is not something this repo tracks or pins)
dispatch:
  maker: "container-use run --env looptimal-maker -- bash maker.sh"
  checker: "container-use run --env looptimal-checker -- python3 scripts/verify-outcome.py --bundle evidence-bundle.json --workdir /workdir"
```

The two `--env` names are separate Container-Use environments — separate containers, separate git
branches, separate filesystems. `verify-outcome.py`'s own trust boundary (it loads only the
sealed contract at `--workdir`, never a maker-supplied one) is unchanged and still does the real
verification work; the container boundary is a second, independent layer on top, not a
replacement for it.

## What this does and doesn't harden

- **Hardens:** execution isolation — the maker process literally cannot read the checker's
  filesystem or vice versa, even if both run on the same host.
- **Does not harden:** the sealed-contract hash-pin itself (see `SECURITY.md` and roadmap item 7 —
  that's a cryptographic guarantee, orthogonal to where the processes physically run) or the
  underlying trust root (whoever controls the Dagger daemon / container runtime is still a trust
  boundary, the same way whoever controls `--workdir` already is).

## Status

This is documentation of a pattern, not a shipped, tested integration — Dagger is never imported
by any `scripts/*.py` file, and no CI job in this repo exercises Container-Use. Treat the YAML
above as illustrative, the same way `profiles/*.example.yaml` are documented as "not maintained
against harness releases — copy and adjust to your installed version."
