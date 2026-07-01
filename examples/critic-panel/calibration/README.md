# Judge calibration — a bounded smoke test

Both `llm-rubric-judge` and `critic-panel` carry the caveat "rubric drift and judge inconsistency
are real" — but until now Looptimal gave you no way to actually *check* that before wiring a judge
into a real loop's `verify.sh`. This closes that gap, narrowly: a small, human-labeled golden set
(`golden/`) plus a harness (`check_calibration.sh`) that runs a judge against every example and
requires a minimum agreement rate before you trust it.

## What's here

- `golden/pass-1.md`, `golden/pass-2.md`, `golden/fail-1.md` — three tiny artifacts, hand-labeled
  once by a human (`golden/expected.txt`) and never touched by the judge under test.
- `judge_under_test.sh` — a deterministic, mildly content-aware **stub** (counts required section
  headers), standing in for a real judge/critic script so this example needs no live LLM call.
  Point `JUDGE=` at your actual critic script for real use.
- `check_calibration.sh` — runs the judge against every golden example, compares its verdict to
  the expected label, and requires `MIN_AGREEMENT` (default `1.0` — every example must agree, for
  a set this small) before printing GREEN.

## Run it

```bash
bash check_calibration.sh                       # GREEN: judge_under_test.sh agrees 3/3
JUDGE=/path/to/broken/judge.sh bash check_calibration.sh   # catches a miscalibrated judge
```

## What this proves — and what it doesn't

A 3-5 example golden set is a **directional smoke test**: it catches a broken or lazy judge (one
that always scores 90 regardless of input, or ignores the rubric entirely) — exactly the failure
mode `check_calibration.sh` demonstrates against a deliberately broken judge that always returns
`{"score": 90, ...}`. It is **not** statistically rigorous calibration and doesn't measure
fine-grained scoring accuracy. Treat a GREEN here as "not obviously broken," not "provably
accurate" — see `templates/verifier-library.yaml`'s `judge-calibration-check` recipe for the
copy-paste version and the same caveat in context.
