# Looptimal — repo guidance for AI agents

Looptimal turns an objective into a delivered, **verified** outcome: a sealed acceptance suite, the
right loop, a war-game pass, domain-expert execution (**maker ≠ checker**), and a separate verifier.
Keep the core generic, dependency-light, and honest about its gates (see `CONTRIBUTING.md`,
`SECURITY.md`, `RELEASE.md`).

## Build Journal — capture the concepts, not the changelog

Append an entry to `.buildlog/journal.md` (create it, and add `.buildlog/` to `.gitignore`, if this
is the first) only when there's a **high-level idea with real weight**:

- a principle the build taught (or re-taught) you,
- a decision with lasting consequence, and why,
- a limitation you're choosing to own rather than hide,
- a gotcha that revealed something deeper than its immediate fix,
- a genuine milestone.

**Skip** routine progress, mechanical fixes, and anything you'd only care about this week. Frequency
follows insight, not activity — a stretch with nothing worth logging is fine.

Format per entry:

```
## <ISO timestamp> — <category> — <short title>
<commit: optional SHA if directly tied to a change>
1-3 sentences, first person, honest. The concept and why it matters — not the play-by-play.
No marketing voice: explain it to a teammate, don't pitch it.
```

Category is one of: `breakthrough` | `learning` | `gotcha` | `decision` | `milestone` | `honest-limitation`

Rules:
- Be honest about what didn't work. Owned limitations and honest misses make better build-in-public
  content than polished wins — don't sand them off.
- Don't self-edit into marketing copy. This is raw material; a separate process shapes it later.
- Never put secrets, credentials, internal paths, or proprietary details in an entry — this file is
  read by that separate process.
- `.buildlog/` is gitignored on purpose: raw internal narrative must never ship in the public OSS
  history.
