# Rubric — Draft README Quality

Score each dimension 0–100. Overall score = mean of all dimensions.

| Dimension | Weight | What earns full marks |
|-|-|-|
| Clarity | 25 | Plain-language opening; no jargon without definition |
| Completeness | 25 | Covers goal, usage, and output in enough detail to act on |
| Accuracy | 25 | No false claims; examples match described behavior |
| Conciseness | 25 | No padding; every sentence earns its place |

**Threshold:** 80 / 100 required to pass this critic's gate.

**Output contract:** a critic script prints one JSON object on stdout — `{"score": N, "reason":
"..."}` — never a bare integer. `reason` should name which dimension(s) drove the score, so a
boundary case is debuggable from `critics.jsonl` alone.
