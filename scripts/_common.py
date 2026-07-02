#!/usr/bin/env python3
"""Shared, stdlib-only helpers for Looptimal's enforcement scripts.

This is the SINGLE SOURCE OF TRUTH for the three things the linter (plan-time) and
verify-outcome.py (Stage 6, outcome-time) must agree on:
  * the canonical contract hash (prefix-tolerant),
  * the "sealed vs maker-writable" path rule, and
  * the anti-gaming heuristics (symptom / self-grade / no-op command).

No third-party imports, no network. Config is parsed as a JSON-compatible YAML subset
(mappings, lists, inline [] / {}, scalars) — no anchors, tags, or multi-line scalars.
"""
from __future__ import annotations

import ast
import hashlib
import hmac
import json
import os
import re
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Anti-gaming heuristics (used identically by lint and verify-outcome)
# --------------------------------------------------------------------------- #
# A "symptom" is a cheap proxy a maker can satisfy WITHOUT achieving the outcome
# (alert cleared by a restart, CI green by deleting tests, coverage % by trivia).
SYMPTOM_PATTERN = re.compile(
    r"\b("
    r"alert[s]?[-_ ]?cleared|ci[-_ ]?green|build[-_ ]?green|"
    r"tests?\s+pass(?:es|ed)?|suite\s+pass(?:es|ed)?|all\s+green|"
    r"looks?\s+good|seems?\s+(?:fine|ok|okay|good)|"
    r"\bdone\b|complete[d]?|finished|succeed(?:s|ed)?|"
    r"coverage\s*(?:%|percent|increased|up)|"
    r"lint[-_ ]?(?:score|clean)|complexity\s*(?:score|reduced|down)"
    r")\b",
    re.IGNORECASE,
)
# A criterion green_means is allowed to assert an OUTCOME; these phrases are symptom-only.
SELF_GRADE_RE = re.compile(
    r"\b("
    r"self[-_\s]?grade[d]?|self[-_\s]?assess(?:ment|ed)?|self[-_\s]?reported|"
    r"verifier_trace|appears?\s+correct|by\s+inspection|trust\s+me|"
    r"maker[-_\s]?(?:approved|signed[-_\s]?off|review|says)|"
    r"i\s+(?:think|believe|judge)"
    r")\b",
    re.IGNORECASE,
)
# Any concrete agent-id literal bound in a GENERIC file (must come from a profile instead).
# Matches binding keys followed by something that looks like a real agent id.
NATIVE_AGENT_RE = re.compile(
    r"(?:^|[^A-Za-z_])(?:agent|executor|checker|verifier|reviewer|subagent[-_ ]?type)"
    r"\s*[:=]\s*[\"']?"
    r"([A-Za-z0-9][\w .:\-]*?"
    r"(?:oh-my-claudecode|agent|reviewer|critic|-pro\b|engineer|specialist|"
    r"claude|gpt-?5|codex|grok|gemini)"
    r"[\w .:\-]*)",
    re.IGNORECASE,
)
# Commands that always succeed regardless of state — never a valid external_check.
NOOP_COMMANDS = frozenset({
    "true", ":", "/bin/true", "/usr/bin/true", "exit", "exit 0", "echo",
    "test", "/bin/echo", "printf", "cat", "ls", "pwd",
})
# An interpreter running INLINE code is maker-controlled, not a sealed check file.
INLINE_INTERPRETERS = frozenset({"python", "python3", "sh", "bash", "zsh", "node",
                                 "ruby", "perl", "php"})
INLINE_EVAL_FLAGS = frozenset({"-c", "-e", "--eval", "--exec", "--command", "-"})
# Designated sealed roots. A path is sealed only if it lives under one of these AND that
# root is not itself executor-writable; callers MUST pass the path relative to the live work tree.
SEALED_ROOTS = ("sealed/", "acceptance/sealed/")
# Conventional maker-writable roots (the executor works here, so nothing sealed may live here).
DEFAULT_WRITABLE_ROOTS = (
    ".", "./", "tmp/", "temp/", "build/", "dist/", "out/", "artifacts/",
    "workspace/", "work/", "scratch/", "loops/", "src/", "lib/", "app/",
    "tests/", "test/", "scripts/", "bin/", "node_modules/", ".omc/", ".git/",
)

_HEX64 = re.compile(r"([0-9a-fA-F]{64})")

FRAMER_KEY_ENV = "LOOPTIMAL_FRAMER_KEY"  # hex-encoded; checker-side only, never repo-committed


def resolve_framer_key(key_file: str | None) -> bytes | None:
    """Resolve the framer's HMAC key (hex-encoded), checker-side only. Precedence: `key_file`,
    then the LOOPTIMAL_FRAMER_KEY env var. Returns None if NEITHER is provided — the caller then
    falls back to the original unkeyed sha256 (fully backward compatible; see
    canonical_contract_hash's docstring). This function only ever reads `key_file` / the env
    var — never anything under a mission's --workdir; keeping the key outside that boundary is
    the checker's own responsibility, same as --workdir itself already is (see SECURITY.md).

    Fails closed (2026-07-01 adversarial review, finding 4) when a key source IS explicitly
    named but unusable (an empty/whitespace-only file or env var) — that case used to silently
    return None, so a run that believed itself keyed (the CI-recommended configuration) could
    run unkeyed with only a non-blocking advisory. Only the "neither provided" case returns
    None; "provided but empty" is now a hard error."""
    raw: str | None = None
    source: str | None = None
    if key_file:
        source = f"--key-file {key_file}"
        raw = Path(key_file).read_text(encoding="utf-8").strip()
    elif FRAMER_KEY_ENV in os.environ:
        source = FRAMER_KEY_ENV
        raw = os.environ[FRAMER_KEY_ENV].strip()
    if not raw:
        if source is not None:
            raise SystemExit(f"{source} was provided but empty — refusing to silently fall "
                              "back to an unkeyed run. Unset it if unkeyed is intended.")
        return None
    try:
        return bytes.fromhex(raw)
    except ValueError as exc:
        raise SystemExit(f"--key-file/{FRAMER_KEY_ENV} must be hex-encoded: {exc}")


class TinyYamlError(ValueError):
    pass


# --------------------------------------------------------------------------- #
# Tiny YAML (JSON-compatible subset)
# --------------------------------------------------------------------------- #
def strip_comment(line: str) -> str:
    in_single = in_double = False
    out: list[str] = []
    prev = ""
    for ch in line:
        if ch == "'" and not in_double and prev != "\\":
            in_single = not in_single
        elif ch == '"' and not in_single and prev != "\\":
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            break
        out.append(ch)
        prev = ch
    return "".join(out).rstrip()


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if value == "":
        return ""
    low = value.lower()
    if low in {"true", "false"}:
        return low == "true"
    if low in {"null", "none", "~"}:
        return None
    if value in {"[]", "{}"} or (value[0], value[-1]) in {("[", "]"), ("{", "}")}:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            try:
                return ast.literal_eval(value)
            except (ValueError, SyntaxError) as exc:
                raise TinyYamlError(f"bad inline collection: {value!r}") from exc
    if (value[0] == value[-1]) and value[0] in {'"', "'"} and len(value) >= 2:
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return value[1:-1]
    try:
        return int(value) if "." not in value else float(value)
    except ValueError:
        return value


def preprocess(text: str) -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    for raw in text.splitlines():
        if "\t" in raw.replace("\t", " ") and "\t" in raw:
            raise TinyYamlError("tabs are not supported in config indentation")
        line = strip_comment(raw)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        rows.append((indent, line.strip()))
    return rows


def parse_block(rows: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(rows):
        return {}, index
    current_indent, content = rows[index]
    if current_indent < indent:
        return {}, index
    if content.startswith("- "):
        seq: list[Any] = []
        while index < len(rows):
            row_indent, item = rows[index]
            if row_indent != indent or not item.startswith("- "):
                break
            body = item[2:].strip()
            index += 1
            if body == "":
                value, index = parse_block(rows, index, indent + 2)
                seq.append(value)
            elif ":" in body and body[0] not in {"'", '"'}:
                key, raw_value = body.split(":", 1)
                obj: dict[str, Any] = {}
                key, raw_value = key.strip(), raw_value.strip()
                if raw_value:
                    obj[key] = parse_scalar(raw_value)
                else:
                    nested, index = parse_block(rows, index, indent + 2)
                    obj[key] = nested
                while index < len(rows):
                    nxt_indent, nxt = rows[index]
                    if nxt_indent != indent + 2 or nxt.startswith("- "):
                        break
                    if ":" not in nxt:
                        raise TinyYamlError(f"expected 'key: value' near {nxt!r}")
                    k, v = nxt.split(":", 1)
                    k, v = k.strip(), v.strip()
                    index += 1
                    if v:
                        obj[k] = parse_scalar(v)
                    else:
                        nested, index = parse_block(rows, index, indent + 4)
                        obj[k] = nested
                seq.append(obj)
            else:
                seq.append(parse_scalar(body))
        return seq, index

    mapping: dict[str, Any] = {}
    while index < len(rows):
        row_indent, content = rows[index]
        if row_indent < indent:
            break
        if row_indent > indent:
            raise TinyYamlError(f"unexpected indentation near {content!r}")
        if content.startswith("- "):
            break
        if ":" not in content:
            raise TinyYamlError(f"expected 'key: value' near {content!r}")
        key, raw_value = content.split(":", 1)
        key, raw_value = key.strip(), raw_value.strip()
        index += 1
        if raw_value:
            mapping[key] = parse_scalar(raw_value)
        else:
            nested, index = parse_block(rows, index, indent + 2)
            mapping[key] = nested
    return mapping, index


def load_config(path: Path) -> Any:
    text = Path(path).read_text(encoding="utf-8")
    if not text.strip():
        raise TinyYamlError(f"empty config file: {path}")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        rows = preprocess(text)
        if not rows:
            raise TinyYamlError(f"no parseable content: {path}")
        parsed, index = parse_block(rows, 0, rows[0][0])
        if index != len(rows):
            raise TinyYamlError(f"unparsed trailing content in {path} at row {index}")
        return parsed


# --------------------------------------------------------------------------- #
# Small typed accessors
# --------------------------------------------------------------------------- #
def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def text_tree(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


# --------------------------------------------------------------------------- #
# Canonical contract hash (prefix-tolerant: accepts "sha256:<hex>" or bare hex)
# --------------------------------------------------------------------------- #
def normalize_hash(value: Any) -> str:
    """Extract a bare lowercase hex digest, tolerant of a 'sha256:' prefix. Anything that isn't
    a 64-hex-char run normalizes to "" rather than an arbitrary lowercased string (2026-07-01
    adversarial review, finding 3.1) — callers compare the result with hmac.compare_digest,
    which raises TypeError on non-ASCII str input; a maker-supplied contract_hash/bundle field
    is hostile input and must fail CLOSED (a clean mismatch -> RED) rather than crash the
    checker before it can even write a verdict."""
    if not value:
        return ""
    m = _HEX64.search(str(value))
    return m.group(1).lower() if m else ""


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sealed_dir_materials(sealed_dir: Path, exclude: Path | None = None) -> dict[str, str]:
    """Sorted {relpath: sha256} of every file under sealed_dir — the in-toto "materials" idea,
    folded into the contract hash so the oracle SCRIPTS a criterion's external_check actually
    invokes are cryptographically bound, not just protected by the is_sealed() filesystem-
    permission check. `exclude` (typically the sealed contract file itself, whose content is
    already covered via the parsed contract mapping) is skipped to avoid a circular hash."""
    materials: dict[str, str] = {}
    if not sealed_dir.is_dir():
        return materials
    exclude_resolved = exclude.resolve() if exclude else None
    for path in sorted(sealed_dir.rglob("*")):
        if path.is_dir():
            continue
        if exclude_resolved is not None and path.resolve() == exclude_resolved:
            continue
        materials[path.relative_to(sealed_dir).as_posix()] = _sha256_file(path)
    return materials


def canonical_contract_hash(
    contract: dict[str, Any],
    *,
    key: bytes | None = None,
    sealed_dir: Path | None = None,
    exclude: Path | None = None,
) -> str:
    """The canonical hash of a sealed contract.

    Backward compatible by construction: called with no keyword args (as every pre-existing
    call site does), this is byte-identical to the original unkeyed sha256-over-the-contract-
    mapping behavior — no forced break for any contract sealed before this function grew these
    parameters.

    `sealed_dir`, when given, folds a manifest of every file under it into the hashed material —
    binding the oracle scripts a criterion's external_check invokes, not just the contract text
    referencing them (previously zero cryptographic binding; only the is_sealed() filesystem-
    permission check protected them).

    `key`, when given, switches from an unkeyed self-digest (anyone who can write the contract
    can recompute a matching hash after tampering) to a keyed HMAC-SHA256 (only someone holding
    `key` can produce a valid hash). The key MUST live outside any path the executor/maker can
    read — never under `sealed_dir`, never committed to a repo — the same trust boundary this
    project already documents for the checker controlling `--workdir`.
    """
    material = {k: v for k, v in dict(contract).items() if k != "contract_hash"}
    if sealed_dir is not None:
        material["__sealed_materials__"] = sealed_dir_materials(sealed_dir, exclude=exclude)
    payload = json.dumps(material, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True).encode("utf-8")
    if key:
        return hmac.new(key, payload, hashlib.sha256).hexdigest()
    return hashlib.sha256(payload).hexdigest()


# --------------------------------------------------------------------------- #
# Sealed-path rule: a path is SEALED iff the executor lanes cannot write to it.
# --------------------------------------------------------------------------- #
def executor_writable_roots(mission: dict[str, Any]) -> set[str]:
    """Every path an executor lane may write to. The acceptance suite / sealed oracle
    must NOT live under any of these, so the maker cannot edit the gate mid-loop."""
    roots: set[str] = set(DEFAULT_WRITABLE_ROOTS)
    cm = mission.get("capability_manifest")
    if isinstance(cm, dict):
        for cap in cm.values():
            for p in as_list(as_dict(cap).get("allowed_paths")):
                roots.add(str(p).replace("\\", "/").lstrip("/").rstrip("/") + "/")
    for lane in as_list(mission.get("lanes")):
        sd = as_dict(lane).get("state_dir")
        if sd:
            roots.add(str(sd).replace("\\", "/").lstrip("/").rstrip("/") + "/")
    return roots


def is_sealed(path_text: Any, writable_roots: set[str]) -> bool:
    """SEALED iff the (work-tree-relative) path lives under a designated sealed root AND that
    root is not itself executor-writable. The caller MUST pass the path relative to the live
    work tree (resolve first): a literal 'sealed/x' that actually resolves under a writable
    root such as loops/<slug>/sealed/x is NOT sealed and must be normalized before this call."""
    p = str(path_text or "").replace("\\", "/").lstrip("/")
    if not p or ".." in p.split("/"):
        return False
    if not any(p == r.rstrip("/") or p.startswith(r) for r in SEALED_ROOTS):
        return False
    for r in writable_roots:
        r = r.rstrip("/")
        if r and r not in {".", "./"} and (p == r or p.startswith(r + "/")):
            return False
    return True


VALID_VISIBILITIES = ("maker-visible", "checker-only")
VALID_GATE_TYPES = ("hard", "soft")


def maker_safe_view(contract: dict[str, Any]) -> dict[str, Any]:
    """The view that Stage-5 Execute context-assembly should hand the maker: criteria marked
    `visibility: checker-only` (an omitted/unrecognized value defaults to maker-visible) are
    redacted down to just `id`/`category` — never `oracle`/`external_check`/`green_means` text,
    the parts that let a maker aim at the gate instead of the fix. Stage 6 (verify-outcome.py) is
    completely unaffected by this — it always operates on the full, unredacted sealed contract;
    this function is only ever for what gets shown to the maker beforehand."""
    view = dict(contract)
    suite = as_dict(view.get("acceptance_suite"))
    if not suite:
        return view
    redacted: list[Any] = []
    for raw in as_list(suite.get("criteria")):
        c = as_dict(raw)
        if str(c.get("visibility") or "maker-visible").strip().lower() == "checker-only":
            redacted.append({"id": c.get("id"), "category": c.get("category")})
        else:
            redacted.append(dict(c))
    view["acceptance_suite"] = {**suite, "criteria": redacted}
    return view


def is_noop_command(external_check: Any) -> bool:
    """True if the external_check is empty or a command that always succeeds."""
    if not external_check:
        return True
    if isinstance(external_check, str):
        parts = external_check.strip().split()
    elif isinstance(external_check, list):
        parts = [str(x) for x in external_check]
    else:
        return True
    if not parts:
        return True
    head = parts[0].strip()
    joined = " ".join(parts).strip().lower()
    if head in NOOP_COMMANDS or joined in NOOP_COMMANDS or Path(head).name in NOOP_COMMANDS:
        return True
    # An interpreter running inline code (python3 -c, sh -c, node -e, or program-from-stdin)
    # is maker-controlled and trivially satisfiable — it is not a sealed check, so reject it.
    if Path(head).name in INLINE_INTERPRETERS and any(a in INLINE_EVAL_FLAGS for a in parts[1:]):
        return True
    return False


def executed_program(external_check: Any) -> str | None:
    """The program an external_check actually EXECUTES — not just any path-shaped argument.

    2026-07-01 adversarial review, finding 2: the prior `candidate_paths()` check accepted a
    check as "invokes a sealed oracle" if ANY path-like token in the command resolved sealed —
    including a sealed *data file* passed as an argument to a maker-writable *program*, e.g.
    `["python3", "src/passer.py", "sealed/fixture.txt"]` runs the maker's own script and was
    accepted because `sealed/fixture.txt` happened to also be present. Only the executed
    program can make that guarantee.

    For a direct invocation (`["sealed/check.sh"]`) that's the first token. For an interpreter
    invocation (`["python3", "sealed/check.py", ...]`) it's the first non-flag argument after
    the interpreter — `is_noop_command()` has already rejected inline eval (`-c`/`-e`/stdin)
    before any caller reaches this point, so what remains for an interpreter head is a script
    argument. Returns None if no such program can be identified."""
    if isinstance(external_check, str):
        parts = external_check.split()
    elif isinstance(external_check, list):
        parts = [str(x) for x in external_check]
    else:
        return None
    if not parts:
        return None
    head = parts[0].strip()
    if Path(head).name in INLINE_INTERPRETERS:
        for a in parts[1:]:
            a = a.strip()
            if a and not a.startswith("-"):
                return a
        return None
    return head or None
