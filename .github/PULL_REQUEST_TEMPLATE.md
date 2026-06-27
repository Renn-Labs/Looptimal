<!-- Thanks for contributing to LoopPrint! See CONTRIBUTING.md. -->

## What & why
<!-- One or two lines: the change and the problem it solves. -->

## Checklist
- [ ] `pytest -q` passes; I added/updated tests for the change
- [ ] `loopprint-lint.py` stays GREEN on the example specs
- [ ] `loopprint-doctor.py` is HEALTHY
- [ ] Shell changes pass `shellcheck` (CI runs it)
- [ ] Docs updated (README / SKILL.md / `references/`) if behavior changed

## Invariants (LoopPrint keeps these — confirm none are broken)
- [ ] Stack-agnostic core; no hardcoded per-harness matrix (bindings live in profiles)
- [ ] Zero-runtime-dep core (only lint / skillify / profile-parsing may use PyYAML)
- [ ] No network / no phone-home
- [ ] maker ≠ checker — incl. on LoopPrint's own output; never auto-run; the runner never `eval`s a spec string
