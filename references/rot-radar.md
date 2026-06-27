# Rot radar — `loopprint ls`

A loop exists to keep working unattended. The failure that hurts most is the *silent* one: a loop whose verifier
has been RED for weeks, or that quietly stopped running, while you assumed it was fine. `loopprint ls` is the
one-glance answer to **"is any of my automation silently broken?"** — repo-local, cost-free, no network.

## Run it
```bash
python3 scripts/loopprint-ls.py                          # health table for every loop in this repo
python3 scripts/loopprint-ls.py --json                   # machine-readable
python3 scripts/loopprint-ls.py --rotten                 # only the broken / dormant ones
python3 scripts/loopprint-ls.py --exit-nonzero-if-rotten # exit 1 if any loop is ROTTEN (CI / cron)
```
No `loopprint` binary is installed by design; set `LOOPPRINT_ROOT` to run from anywhere (see the README
"Invoking the tools"). `loopprint-doctor.py` prints the exact command for your install.

## What it reads
Discovery is **binding-aware**: `ls` asks `loopprint-detect.py` where this harness keeps loop state (`state_dir`)
and scans there, plus `loops/` and `.omc/loops/`; add `--dir` for a custom root. It only *reads* state — it never
runs a loop, a maker, or a verifier.

Per loop it uses the first source that has data (the **health ladder**):
`metrics.jsonl` → `state.jsonl` → the verifier marker (`.omc/state/<mode>-verifier.json`, when the profile sets
`marker_path`). Streaks are counted in **file append order**, never by sorting timestamps — clocks skew and
backfills happen; the runner appends in order.

## The states
| Status | Means | Rule |
|-|-|-|
| **HEALTHY** | ran recently and has gone GREEN | default |
| **RUNNING** | a run is live right now | the runner holds a `.running` lock **and** wrote within `--running-grace` (120 s) |
| **PENDING** | ran recently but has never passed yet | recent, `red_streak < K`, not running, never GREEN |
| **ROTTEN** | failing repeatedly — fix it | `red_streak >= K` (`--rot-streak`, default 3), recent, not running |
| **STALE** | the automation went quiet | no run in > N days (`--stale-days`, default 14) |
| **UNKNOWN** | can't assess | reason: `never_run` · `no_verdict` (ran, only SKIP lines) · `no_timestamp` · `parse_error` · `no_data` |

Precedence (mutually exclusive): UNKNOWN → RUNNING → STALE → ROTTEN → PENDING → HEALTHY. A live run is detected by
a `.running` lock the runner holds, so a **terminal** RED loop is *not* masked — it reaches ROTTEN, which is the
point of `--exit-nonzero-if-rotten`. **STALE outranks ROTTEN** so a dormant loop reads as "stopped," not "actively
failing."

## Wire it into CI / cron
Fail a scheduled job when a loop has silently rotted:
```yaml
- run: python3 "$LOOPPRINT_ROOT/scripts/loopprint-ls.py" --exit-nonzero-if-rotten
```
`--exit-nonzero-if-rotten` fails on **ROTTEN only** — not STALE or RUNNING — so it's a clean "something that
should be passing is now failing" signal, not a noisy one.

## Notes & limits
- Health comes from each loop's *own* run history. No global/cross-repo aggregation, no telemetry — nothing
  leaves your machine.
- A marker-only loop (an OMC verifier marker, no jsonl) yields a last verdict but not a long streak: a recent RED
  marker is treated as ROTTEN; a longer streak needs `metrics.jsonl`/`state.jsonl` history. The marker is matched
  **exactly** by slug (no fuzzy filename matching), so it resolves only when the marker is named for this loop.
- `state.jsonl` carries `verifier_result` + `ts` but not `wall_ms`/`accepted` (it is the checkpoint log), so `ls`
  reads only the color and timestamp from it.
