# critic-panel example

A Looptimal loop that gates on a **k-of-N quorum** of independent critics.
Three critics each score `artifact.md` against `rubric.md`; the loop is GREEN
only when at least 2 of the 3 score >= 80.

## The panel

| Script | Provider | Stub score |
|-|-|-|
| `critic-1.sh` | codex | 90 |
| `critic-2.sh` | grok | 85 |
| `critic-3.sh` | gemini | 70 |

`quorum_k: 2` — two passing critics are enough. Critics 1 and 2 pass (90 >= 80,
85 >= 80); critic 3 falls short (70 < 80). Quorum met → GREEN.

## Judge identity and reproducibility

`verify.sh` emits one JSON line per critic to `critics.jsonl`:

```
{"ts":"…","critic":"critic-1","provider":"codex","score":90,"threshold":80,
 "pass":true,"rubric_sha":"…","artifact_sha":"…","n":3,"quorum_k":2}
```

`rubric_sha` and `artifact_sha` are SHA-256 hashes of the committed rubric and
the judged artifact. Together with `provider`, they record *who judged what,
against which rubric, with what verdict* — inspectable after the fact.

## Judge != maker (cross-provider)

The maker (`maker.sh`) dispatches to `claude`. Each critic targets a different
provider: `codex`, `grok`, `gemini`. No critic shares a provider with the maker,
so the panel is fully cross-provider — the strongest form of judge-independence
Looptimal supports.

## Single-provider acknowledgement

If you only have one LLM CLI available, all critics will call the same provider.
The panel still enforces quorum and runs N independent calls, but a single model
judging its own output is weaker than cross-provider review. If that is your
situation, acknowledge it explicitly (e.g. in `state.md`) rather than leaving it
implicit. Use the `PROVIDER=` marker in each critic script so the lint advisory
fires and reminds you.

## Stub critics prove the mechanism, not LLM judgment quality

The stub critics in this example `echo` a fixed score. They prove that the
fan-out, score parsing, quorum tally, `critics.jsonl` emission, and exit-code
gate all work correctly without a live LLM. The gate bites: flip critic-2 to
score 50 and only 1 of 3 critics pass, dropping below quorum.

Wire real LLM dispatch (swap the `echo` for `claude -p`/`codex exec`/`grok …`)
to get real judgment quality. The mechanism is identical either way.

## Run the demo

```
bash examples/critic-panel/run_demo.sh
```

Runs entirely in a `mktemp -d` directory. Tracked files are never modified.
