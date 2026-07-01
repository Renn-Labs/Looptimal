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
marketed as fully tamper-proof against a maker who can write the sealed dir.

**Cryptographic hardening (available, opt-in).** `scripts/_common.py::canonical_contract_hash()`
supports an HMAC-SHA256 keyed digest (`--key-file` / `LOOPTIMAL_FRAMER_KEY` on `verify-outcome.py`
and `looptimal-lint.py`) that also folds in a manifest of every file under `sealed/` — binding the
oracle *scripts* a criterion's `external_check` actually invokes, not just the criteria text
referencing them (previously zero cryptographic binding; only the `is_sealed()` filesystem-
permission check protected them). Without a key, `canonical_contract_hash()` falls back to the
original unkeyed sha256 self-digest — fully backward compatible, but weaker: anyone who can write
the sealed contract can also recompute a matching unkeyed hash after tampering. **The key itself
must never live under `sealed/` or anywhere the maker/executor can read** — it belongs wherever the
checker already keeps `--workdir` out of the maker's reach; a fresh key via `secrets.token_bytes(32)`
per mission, never committed to a repo. This closes the specific residual above (spec/oracle-script
tampering); it does not remove the underlying trust root (OS permissions + checker-controlled
`--workdir`) — a deployment where the checker doesn't actually control either is still unprotected,
key or no key.

## Reporting a vulnerability
Please open a private security advisory on the repository (GitHub → Security → Report a vulnerability) rather than
a public issue.
