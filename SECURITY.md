# Security

Looptimal's loop-design mode generates and runs loop **blueprints**. In a generated package, two files are executable code:

- `run-this-loop.sh` — the loop runner.
- `verify.sh` — the external verifier the runner executes each iteration.

…and `loop-spec.yaml` parameterizes them. **Treat a loop-spec and its package as code, not data.**

## Trust boundary
Whoever authored a loop-spec/package is trusted to the level of "may run shell on your machine." Do **not** run a
`run-this-loop.sh`, `verify.sh`, or `loop-spec.yaml` from an untrusted source without reading it first — the same
caution you'd give any shell script.

## What the loop-design mode itself does (and doesn't)
- The skill and `scripts/loopprint-lint.py` only **read and validate** specs — they never execute them.
- `run-this-loop.sh` runs `verify.sh` as a separate process; it does **not** `eval` a command string taken from
  the spec. The verifier is a file you can read, not an inline string the runner interprets.
- In `checkpoint` autonomy the runner **refuses to proceed without an interactive TTY** rather than silently
  running unattended.

## Outcome verification & the sealed contract (orchestrator)
Looptimal's outcome gate (`scripts/verify-outcome.py`, Stage 6) is run by a **checker** separate from
the executor. It loads the **sealed** acceptance contract the evidence bundle points at (never a
maker-supplied `--contract`), validates the resolved path is sealed against the executor's writable
lanes, canonicalizes and hash-matches it, and **re-runs** each acceptance criterion authoritatively —
the bundle's self-reported result can only *lose*. It rejects no-op/inline-eval checks, requires each
criterion to invoke a sealed, workdir-contained oracle script, and strips interpreter env injection.

**Disclosed residual (be honest about this):** the irreducible trust root is OS filesystem permissions
plus the checker controlling `--workdir` (the real target repo, not the maker's bundle dir). The
**framer must own the `sealed/` directory** so the maker cannot author the contract or the oracle
scripts. Every other gaming vector is mechanically closed and exploit-tested, but Looptimal is **not**
marketed as fully tamper-proof against a maker who can write the sealed dir — a cryptographic framer
hash-pin for the sealed contract is planned to remove even that deployment-level trust.

## Reporting a vulnerability
Please open a private security advisory on the repository (GitHub → Security → Report a vulnerability) rather than
a public issue.
