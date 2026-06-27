#!/usr/bin/env python3
"""loopprint-doctor — diagnose (and safely repair) a LoopPrint install.

A broken skill install fails quietly: the wizard "isn't there", a script won't run, a partial
clone is missing templates, a symlink dangles after the repo moved. This walks the install
*bottom-up* — files intact? scripts runnable? binding resolves? harness wired? — and for every
problem prints an actionable fix. It is meant to be read by an agent OR a human: each finding
carries a copy-pasteable `fix:` line.

Two design rules keep it honest and public-safe:
  - It heals the GENERIC skill. Harness-specific bridges (a Codex/OMX real-copy, your plugin
    sync) are owned by your harness, so the doctor *detects* the ecosystem and points you at
    references/troubleshooting.md instead of hardcoding a private command (same decoupling rule
    as loopprint-detect.py: marker -> ecosystem NAME, never embed binding VALUES).
  - --fix only does SAFE, reversible repairs (chmod +x, relink a *dangling* symlink). Anything
    risky (re-clone, edit user config) is suggested, not done. Maker != checker, applied to the
    doctor itself.

Usage:
    loopprint-doctor.py            # diagnose, human-readable
    loopprint-doctor.py --json     # machine-readable findings (for agents)
    loopprint-doctor.py --fix      # also apply safe auto-repairs, then re-report

Exit code: 0 = no failures (warnings allowed), 1 = at least one FAIL, 2 = doctor error.
Stdlib-only, no network.
"""
from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # scripts/ -> repo root

# Files the wizard loads at runtime. A missing one means a partial/corrupt checkout.
CONTRACT = [
    "SKILL.md",
    "references/decision-gate.md",
    "references/patterns.md",
    "references/profiles.md",
    "templates/loop-spec.yaml",
    "templates/run-this-loop.sh",
    "templates/verification-hook.sh",
    "templates/state-template.md",
    "templates/safety-checklist.md",
    "templates/flow.mmd",
    "scripts/loopprint-lint.py",
    "scripts/loopprint-detect.py",
    "references/troubleshooting.md",
]

# Scripts that must be executable to run as `./scripts/x.py`. Absence is covered by CONTRACT.
EXEC_SCRIPTS = [
    "scripts/loopprint-lint.py",
    "scripts/loopprint-detect.py",
    "scripts/loopprint-doctor.py",
    "scripts/loopprint-ls.py",
    "scripts/loopprint-report.py",
    "scripts/loopprint-skillify.py",
    "scripts/banner.py",
]

COLORS = {"OK": "32", "WARN": "33", "FAIL": "31", "SKIP": "90", "INFO": "90"}


def _plain() -> bool:
    return bool(os.environ.get("NO_COLOR")) or os.environ.get("TERM") == "dumb" or not sys.stdout.isatty()


def _color(status: str, text: str) -> str:
    if _plain():
        return text
    return f"\033[{COLORS.get(status, '0')}m{text}\033[0m"


class Report:
    def __init__(self, fix: bool):
        self.fix = fix
        self.findings: list[dict] = []

    def add(self, check: str, status: str, detail: str, fix: str = "") -> None:
        self.findings.append({"check": check, "status": status, "detail": detail, "fix": fix})

    def counts(self) -> dict:
        c = {"OK": 0, "WARN": 0, "FAIL": 0, "SKIP": 0, "INFO": 0}
        for f in self.findings:
            c[f["status"]] = c.get(f["status"], 0) + 1
        return c


# --- safe auto-repairs ------------------------------------------------------

def _make_executable(path: Path) -> bool:
    if path.is_symlink():  # never chmod through a symlink — could change a target outside the repo
        return False
    try:
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return True
    except OSError:
        return False


def _relink(link: Path, target: Path) -> bool:
    """Repoint a *dangling* symlink to target. Caller must have verified link is a broken symlink."""
    try:
        link.unlink()
        link.symlink_to(target, target_is_directory=True)
        return link.resolve() == target.resolve()
    except OSError:
        return False


# --- checks -----------------------------------------------------------------

_BLOCK_SCALARS = {"", ">", "|", ">-", "|-", ">+", "|+"}


def _frontmatter(text: str):
    """Extract (name, description) from a leading --- YAML block, without needing PyYAML.

    Best-effort: handles inline `key: value` and block scalars (`key: >` / `key: |` with indented
    content on the following line). Not a full YAML parser — the harness uses real YAML; this only
    sanity-checks that the keys exist and aren't empty.
    """
    if not text.startswith("---"):
        return None, None
    end = text.find("\n---", 3)
    if end == -1:
        return None, None
    lines = text[3:end].splitlines()
    found: dict[str, str] = {}
    for i, line in enumerate(lines):
        m = re.match(r"\s*([A-Za-z_]+)\s*:\s*(.*)$", line)
        if not m or m.group(1) not in ("name", "description"):
            continue
        key, val = m.group(1), m.group(2).strip().strip("\"'")
        if val in _BLOCK_SCALARS:  # empty inline, or a block-scalar header whose body is indented below
            val = ""
            for nxt in lines[i + 1:]:  # a block scalar may have blank lines before its indented body
                if not nxt.strip():
                    continue
                val = "non-empty" if nxt[:1].isspace() else ""  # indented = body; unindented = next key
                break
        found[key] = val
    return found.get("name"), found.get("description")


def check_python(r: Report) -> None:
    v = sys.version_info
    if v < (3, 8):
        r.add("python", "FAIL", f"Python {v.major}.{v.minor} is below 3.8",
              "Install Python 3.8+ and run the scripts with it (the skill's tools assume 3.8+).")
    else:
        r.add("python", "OK", f"Python {v.major}.{v.minor}.{v.micro}")


def check_layout(r: Report) -> None:
    missing = [rel for rel in CONTRACT if not (ROOT / rel).is_file()]
    if missing:
        r.add("contract_files", "FAIL", f"missing {len(missing)}: {', '.join(missing)}",
              "Partial/corrupt checkout. Re-clone: "
              "git clone https://github.com/Renn-Labs/LoopPrint (or `git -C <repo> checkout -- .`).")
    else:
        r.add("contract_files", "OK", f"all {len(CONTRACT)} core files present")


def check_frontmatter(r: Report) -> None:
    skill = ROOT / "SKILL.md"
    if not skill.is_file():
        r.add("skill_frontmatter", "FAIL", "SKILL.md not found at repo root",
              "loopprint-doctor.py must live in <repo>/scripts/. Move it back or re-clone.")
        return
    name, desc = _frontmatter(skill.read_text(encoding="utf-8", errors="replace"))
    if not name or not desc:
        miss = "name" if not name else "description"
        r.add("skill_frontmatter", "FAIL", f"SKILL.md frontmatter missing `{miss}`",
              "SKILL.md must open with a `---` block containing `name:` and `description:`. "
              "Without it the harness won't discover the skill.")
    elif name != "loopprint":
        r.add("skill_frontmatter", "WARN", f"frontmatter name is '{name}', expected 'loopprint'",
              "Set `name: loopprint` in SKILL.md unless you deliberately forked it.")
    else:
        r.add("skill_frontmatter", "OK", "SKILL.md frontmatter has name + description")


def check_exec_bits(r: Report) -> None:
    if os.name == "nt":  # Windows has no Unix exec bit — scripts are invoked as `python <script>.py`
        r.add("exec_bits", "SKIP", "exec bits don't apply on Windows — invoke as `python <script>.py`")
        return
    issues = []
    for rel in EXEC_SCRIPTS:
        p = ROOT / rel
        if not p.is_file():
            continue  # covered by CONTRACT / not-required (banner)
        if not os.access(p, os.X_OK):
            if r.fix and _make_executable(p):
                issues.append(f"{rel} (auto-fixed)")
            else:
                issues.append(rel)
    if not issues:
        r.add("exec_bits", "OK", "scripts are executable")
    elif r.fix and all(i.endswith("(auto-fixed)") for i in issues):
        r.add("exec_bits", "OK", f"made executable: {', '.join(i.split(' ')[0] for i in issues)}")
    else:
        targets = " ".join(str(ROOT / i) for i in issues if not i.endswith("(auto-fixed)"))
        r.add("exec_bits", "WARN", f"not executable: {', '.join(issues)}",
              f"chmod +x {targets}   (or run this doctor with --fix)")


def _run(args: list[str], cwd: Path | None = None) -> tuple[int, str]:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=30, cwd=str(cwd or ROOT))
        return proc.returncode, (proc.stdout + proc.stderr)
    except (OSError, subprocess.SubprocessError) as e:
        return 127, str(e)


def check_detect_runs(r: Report) -> None:
    detect = ROOT / "scripts" / "loopprint-detect.py"
    if not detect.is_file():
        r.add("detect_runs", "SKIP", "loopprint-detect.py absent (see contract_files)")
        return
    rc, out = _run([sys.executable, str(detect)], cwd=Path.cwd())  # match check_profile's cwd-relative ./.loopprint
    if rc != 0 or "harness:" not in out:
        r.add("detect_runs", "FAIL", f"loopprint-detect.py exited {rc}: {out.strip()[:160]}",
              "The binding resolver crashed. Re-clone the file or report a bug; "
              "until then the wizard falls back to generic defaults.")
        return
    src = next((ln[len("# source: "):] for ln in out.splitlines() if ln.startswith("# source: ")), "?")
    # The resolver runs, but a present-yet-broken profile makes it fall back to generic. detect.py reports
    # that in the source line ("could not parse" / "is not a mapping") — don't green-wash a dropped binding.
    if "could not parse" in src or "is not a mapping" in src:
        r.add("detect_runs", "WARN", f"resolver ran but a profile didn't load — fell back to generic (source: {src})",
              "A profile.yaml exists but couldn't be read, so your harness binding is being ignored. "
              "See the `profile` / `pyyaml` checks below and fix or remove it.")
    else:
        r.add("detect_runs", "OK", f"binding resolver works (source: {src})")


def check_pyyaml(r: Report) -> None:
    import importlib.util
    if importlib.util.find_spec("yaml") is not None:
        r.add("pyyaml", "OK", "PyYAML importable")
    else:
        r.add("pyyaml", "WARN", "PyYAML not installed",
              "pip install pyyaml  —  loopprint-lint.py and profile parsing need it; "
              "the wizard otherwise runs on generic defaults.")


def check_lint_selftest(r: Report) -> None:
    lint = ROOT / "scripts" / "loopprint-lint.py"
    example = ROOT / "examples" / "ci-triage" / "loop-spec.yaml"
    if not lint.is_file() or not example.is_file():
        r.add("lint_selftest", "SKIP", "loopprint-lint.py or the bundled example is absent")
        return
    rc, out = _run([sys.executable, str(lint), str(example)])
    if rc == 0:
        r.add("lint_selftest", "OK", "linter passes the bundled example (GREEN)")
    elif rc == 2:
        r.add("lint_selftest", "WARN", "linter can't run (PyYAML missing)",
              "pip install pyyaml")
    else:
        r.add("lint_selftest", "FAIL", f"linter RED on the bundled example: {out.strip()[:160]}",
              "The shipped example should be GREEN — your copy of lint.py or the example is corrupt. Re-clone.")


def check_profile(r: Report) -> None:
    candidates = [(Path.cwd() / ".loopprint" / "profile.yaml", "./.loopprint/profile.yaml"),
                  (Path.home() / ".loopprint" / "profile.yaml", "~/.loopprint/profile.yaml")]
    found = [(p, label) for p, label in candidates if p.is_file()]
    if not found:
        r.add("profile", "SKIP", "no profile.yaml — generic defaults (loops/<slug>/, verify.sh); that's fine")
        return
    p, label = found[0]
    try:
        import yaml
    except ImportError:
        r.add("profile", "WARN", f"{label} present but PyYAML missing to validate it",
              "pip install pyyaml")
        return
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as e:
        r.add("profile", "FAIL", f"{label} won't parse: {str(e)[:120]}",
              "Fix the YAML, or remove the file to fall back to generic defaults. "
              "See references/profiles.md for the contract.")
        return
    if not isinstance(data, dict):
        r.add("profile", "FAIL", f"{label} is not a mapping",
              "The binding must be a YAML map (harness/state_dir/verifier/...). See references/profiles.md.")
    else:
        r.add("profile", "OK", f"{label} parses (harness: {data.get('harness', '?')})")


def check_plugin_manifests(r: Report) -> None:
    pdir = ROOT / ".claude-plugin"
    pj, mj = pdir / "plugin.json", pdir / "marketplace.json"
    if not pj.is_file() and not mj.is_file():
        r.add("plugin_manifests", "SKIP", "no .claude-plugin/ (folder-skill install only)")
        return
    problems = []
    if pj.is_file() != mj.is_file():  # a plugin install needs BOTH manifests, not one of the pair
        problems.append(f"{'marketplace.json' if pj.is_file() else 'plugin.json'} is missing — a plugin needs both")
    if pj.is_file():
        try:
            if "name" not in json.loads(pj.read_text(encoding="utf-8")):
                problems.append("plugin.json missing required `name`")
        except Exception as e:
            problems.append(f"plugin.json invalid JSON: {str(e)[:80]}")
    if mj.is_file():
        try:
            m = json.loads(mj.read_text(encoding="utf-8"))
            if "owner" not in m or "plugins" not in m:
                problems.append("marketplace.json missing `owner`/`plugins`")
        except Exception as e:
            problems.append(f"marketplace.json invalid JSON: {str(e)[:80]}")
    if problems:
        r.add("plugin_manifests", "FAIL", "; ".join(problems),
              "Plugin install (/plugin marketplace add ...) needs valid manifests. Restore them from a clean clone.")
    else:
        r.add("plugin_manifests", "OK", "plugin + marketplace manifests are valid JSON")


def _skills_dirs() -> list[Path]:
    dirs = []
    cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    if cfg:
        dirs.append(Path(cfg) / "skills")
    dirs.append(Path.home() / ".claude" / "skills")
    seen, out = set(), []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


HARNESS_SKILL_DIRS = [
    ("claude", _skills_dirs),                                       # ~/.claude/skills (+ CLAUDE_CONFIG_DIR)
    ("openclaw", lambda: [Path.home() / ".openclaw" / "skills"]),
    ("hermes", lambda: [Path.home() / ".hermes" / "skills"]),
    ("opencode", lambda: [Path.home() / ".config" / "opencode" / "skills",  # OpenCode: global + personal dirs
                          Path.home() / ".opencode" / "skills"]),
]


def _check_one_link(r: Report, harness: str, link: Path) -> None:
    """Inspect one folder-skill symlink: dangling -> WARN(+--fix relink), here -> OK, elsewhere -> WARN."""
    cid = f"{harness}_link"
    if not link.exists() and not link.is_symlink():
        r.add(cid, "INFO", f"no '{link.name}' in {link.parent} — fine if you don't use {harness}'s folder-skill path",
              f"To install as a folder skill: ln -s {ROOT} {link}")
        return
    if link.is_symlink() and not link.exists():  # dangling
        if r.fix and _relink(link, ROOT):
            r.add(cid, "OK", f"relinked dangling {link} -> {ROOT}")
        else:
            r.add(cid, "WARN", f"{link} is a dangling symlink (target moved)",
                  f"ln -sfn {ROOT} {link}   (or run this doctor with --fix)")
        return
    try:
        here = link.resolve() == ROOT
    except OSError:
        here = False
    if here:
        r.add(cid, "OK", f"{link} -> this repo")
    else:
        r.add(cid, "WARN", f"{link} exists but points elsewhere ({_safe_resolve(link)})",
              f"If that's a stale/forked copy: ln -sfn {ROOT} {link}")


def check_skill_links(r: Report) -> None:
    """Health-check the folder-skill symlink in EVERY harness skills dir present (Claude, OpenClaw, Hermes,
    OpenCode). They all discover <skills-dir>/<name>/SKILL.md the same way, so a dangling/wrong/missing link is
    checked alike — not just Claude's — and every existing skills dir is inspected, not only the first."""
    checked = False
    for harness, dirs_fn in HARNESS_SKILL_DIRS:
        for d in dirs_fn():
            if d.is_dir():
                checked = True
                _check_one_link(r, harness, d / "loopprint")
    if not checked:
        r.add("skill_links", "SKIP",
              "no harness skills dir (Claude/OpenClaw/Hermes/OpenCode) — plugin install, or none present")


def _safe_resolve(p: Path) -> str:
    try:
        return str(p.resolve())
    except OSError:
        return "unresolvable"


def check_ecosystem_hint(r: Report) -> None:
    cwd = Path.cwd()
    home = Path.home()
    seen = []
    if (cwd / ".omc").is_dir() or (home / ".claude" / "skills").is_dir():
        seen.append("oh-my-claudecode")
    if (cwd / ".omx").is_dir() or (home / ".codex" / "skills").is_dir():
        seen.append("oh-my-codex/Codex")
    if (home / ".openclaw" / "skills").is_dir():
        seen.append("openclaw")
    if (home / ".hermes" / "skills").is_dir():
        seen.append("hermes")
    if (home / ".config" / "opencode").is_dir() or (home / ".opencode" / "skills").is_dir():
        seen.append("opencode")
    if seen:
        r.add("ecosystem", "INFO", f"detected: {', '.join(seen)}",
              "Harnesses that discover a skills dir (OpenClaw, Hermes, OpenCode) install like Claude — symlink "
              "the repo into that skills dir (OpenCode also auto-loads skills from ~/.claude/skills). For "
              "harnesses that real-copy skills (Codex/OMX) or read an AGENTS.md catalog (Grok), re-run that "
              "harness's sync after updates. These bridges are owned by your harness; see "
              "references/troubleshooting.md.")
    else:
        r.add("ecosystem", "INFO", "no known harness markers — generic install")


def check_assets(r: Report) -> None:
    if (ROOT / "assets" / "logo.txt").is_file():
        r.add("assets", "OK", "banner art present")
    else:
        r.add("assets", "WARN", "assets/logo.txt missing (cosmetic — banner.py won't render)",
              "Restore from a clean clone if you want the banner; nothing functional depends on it.")


def check_invocation(r: Report) -> None:
    # The tools ship with no installed `loopprint` binary by design — they run from this clone.
    # Surface the canonical, copy-pasteable command (platform-aware) so a user (and their CI) has a stable path.
    if not (ROOT / "scripts" / "loopprint-ls.py").is_file():
        return
    if os.name == "nt":
        cmd = f'set "LOOPPRINT_ROOT={ROOT}" && python "%LOOPPRINT_ROOT%\\scripts\\loopprint-ls.py"'
    else:
        cmd = f'LOOPPRINT_ROOT="{ROOT}" python3 "$LOOPPRINT_ROOT/scripts/loopprint-ls.py"'
    r.add("invocation", "INFO", "tools run from this clone (no PATH binary by design)",
          f"loop health:  {cmd}")


CHECKS = [
    check_python,
    check_layout,
    check_frontmatter,
    check_exec_bits,
    check_detect_runs,
    check_pyyaml,
    check_lint_selftest,
    check_profile,
    check_plugin_manifests,
    check_skill_links,
    check_ecosystem_hint,
    check_assets,
    check_invocation,
]


def main(argv: list[str]) -> int:
    if "-h" in argv or "--help" in argv:
        print("usage: loopprint-doctor.py [--fix] [--json]\n"
              "  --fix   apply safe auto-repairs (chmod +x, relink a dangling symlink)\n"
              "  --json  machine-readable findings\n"
              "exit: 0 ok (warnings allowed), 1 at least one FAIL, 2 doctor error")
        return 0
    r = Report(fix="--fix" in argv)
    for check in CHECKS:
        try:
            check(r)
        except Exception as e:  # a check must never crash the doctor
            r.add(check.__name__, "FAIL", f"doctor check errored: {e}",
                  "This is a bug in loopprint-doctor.py — please report it.")

    if "--json" in argv:
        print(json.dumps({"root": str(ROOT), "findings": r.findings, "counts": r.counts()}, indent=2))
        return 1 if r.counts()["FAIL"] else 0

    print(_color("INFO", f"LoopPrint doctor — {ROOT}"))
    for f in r.findings:
        tag = _color(f["status"], f"{f['status']:<4}")
        print(f"  {tag} {f['check']}: {f['detail']}")
        if f["fix"] and f["status"] in ("WARN", "FAIL", "INFO"):
            print(f"       {_color('SKIP', 'fix:')} {f['fix']}")
    c = r.counts()
    print()
    summary = f"{c['OK']} ok · {c['WARN']} warn · {c['FAIL']} fail · {c['SKIP']} skip"
    if c["FAIL"]:
        print(_color("FAIL", f"NOT HEALTHY — {summary}"))
        print("Apply the fix: lines above. Re-run to confirm GREEN. (Safe fixes: add --fix.)")
        return 1
    if c["WARN"]:
        print(_color("WARN", f"USABLE, with warnings — {summary}"))
        return 0
    print(_color("OK", f"HEALTHY — {summary}"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))  # SystemExit (the normal path) carries the 0/1 code and propagates
    except Exception as e:  # a doctor-level failure (not a per-check error, which is caught above) -> exit 2
        print(f"loopprint-doctor: internal error: {e}", file=sys.stderr)
        sys.exit(2)
