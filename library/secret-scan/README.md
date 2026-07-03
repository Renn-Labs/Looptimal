# Library loop: secret-scan

Scans git-tracked files (or regular files when not in a git repo) for committed secrets and
high-entropy credentials: AWS access keys (`AKIA…`), PEM private-key headers, common
`api_key` / `secret` / `password` / `token` assignments, and long base64-ish blobs.

Files:
- `loop-spec.yaml` — the four atoms (spec-driven pattern, checkpoint autonomy).
- `verify.sh` — portable, side-effect-free external gate (git + coreutils only; exit 0 = GREEN).
- `maker.sh` — separate remediation guide; prints file:line and rotation steps, never auto-edits.

`verify.sh` is read-only and needs no network. When you install this loop into a consumer repo,
the install CLI smoke-runs `verify.sh` there so you get a real GREEN/RED verdict before the
loop is wired in.