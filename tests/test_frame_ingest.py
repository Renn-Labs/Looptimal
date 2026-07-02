"""Tests for scripts/looptimal-frame-ingest.py — the optional Stage-0 Frame helper that
surfaces GitHub spec-kit / AWS Kiro artifacts as CANDIDATE (never sealed) acceptance-criteria
text (ROADMAP.md item #17a). Covers direct-import unit coverage of the extraction/discovery
functions, fixture-tree integration coverage of scan()/render_report(), and CLI-level
subprocess coverage of the --json/--out/refusal paths."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "looptimal-frame-ingest.py"


def _load():
    spec = importlib.util.spec_from_file_location("looptimal_frame_ingest", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fi = _load()

# ---- realistic fixture content -------------------------------------------------------
CONSTITUTION_MD = """# Project Constitution

## Core Principles

### I. Simplicity First
Every feature starts with the simplest design that could work.

### II. Test-First
Tests MUST be written before implementation code lands.

## Governance
This constitution supersedes all other engineering practices.
"""

SPEC_KIT_SPEC_MD = """# Feature Specification: Password Reset

## User Scenarios & Testing

### User Story 1 - Reset via email (Priority: P1)
As a returning user, I want to reset my password by email, so that I can regain access to my \
account.

## Requirements

- **FR-001**: System MUST allow a user to request a password-reset email.
- **FR-002**: System MUST invalidate the reset token after its first use.

## Success Criteria

- **SC-001**: 95% of reset requests complete within 5 minutes.
"""

SPEC_KIT_SPEC_PROSE_ONLY_MD = """# Feature Specification: Dark Mode

## Overview
Users have asked for a dark color theme across the dashboard.

## Design Notes
Follow the existing palette tokens; no new color primitives.
"""

KIRO_STEERING_MD = """# Product Overview

This product helps small teams track inventory in real time.

## Target Users
Warehouse managers and floor staff.
"""

KIRO_REQUIREMENTS_MD = """# Requirements Document

## Introduction
Checkout flow requirements for the online store.

## Requirements

### Requirement 1

**User Story:** As a shopper, I want to check out with a saved card, so that I can complete \
purchases quickly.

#### Acceptance Criteria

1. WHEN the cart is empty THEN the system SHALL disable the checkout button
2. IF payment fails THEN the system SHALL display a retry option
"""


def _write_spec_kit(root: Path, *, constitution: str | None = None,
                     specs: dict[str, str] | None = None) -> None:
    if constitution is not None:
        d = root / ".specify" / "memory"
        d.mkdir(parents=True, exist_ok=True)
        (d / "constitution.md").write_text(constitution, encoding="utf-8")
    for feature, content in (specs or {}).items():
        d = root / "specs" / feature
        d.mkdir(parents=True, exist_ok=True)
        (d / "spec.md").write_text(content, encoding="utf-8")


def _write_kiro(root: Path, *, steering: dict[str, str] | None = None,
                 specs: dict[str, str] | None = None) -> None:
    for name, content in (steering or {}).items():
        d = root / ".kiro" / "steering"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.md").write_text(content, encoding="utf-8")
    for feature, content in (specs or {}).items():
        d = root / ".kiro" / "specs" / feature
        d.mkdir(parents=True, exist_ok=True)
        (d / "requirements.md").write_text(content, encoding="utf-8")


# =====================================================================================
# Discovery
# =====================================================================================
def test_find_spec_kit_artifacts_both_present(tmp_path):
    _write_spec_kit(tmp_path, constitution=CONSTITUTION_MD, specs={"user-auth": SPEC_KIT_SPEC_MD})
    found = fi.find_spec_kit_artifacts(tmp_path)
    assert found["constitution"] == tmp_path / ".specify" / "memory" / "constitution.md"
    assert found["specs"] == [tmp_path / "specs" / "user-auth" / "spec.md"]


def test_find_spec_kit_artifacts_constitution_only(tmp_path):
    _write_spec_kit(tmp_path, constitution=CONSTITUTION_MD)
    found = fi.find_spec_kit_artifacts(tmp_path)
    assert found["constitution"] is not None
    assert found["specs"] == []


def test_find_spec_kit_artifacts_specs_only(tmp_path):
    _write_spec_kit(tmp_path, specs={"user-auth": SPEC_KIT_SPEC_MD})
    found = fi.find_spec_kit_artifacts(tmp_path)
    assert found["constitution"] is None
    assert len(found["specs"]) == 1


def test_find_spec_kit_artifacts_none(tmp_path):
    found = fi.find_spec_kit_artifacts(tmp_path)
    assert found["constitution"] is None
    assert found["specs"] == []


def test_find_kiro_artifacts_both_present(tmp_path):
    _write_kiro(tmp_path, steering={"product": KIRO_STEERING_MD},
                specs={"checkout": KIRO_REQUIREMENTS_MD})
    found = fi.find_kiro_artifacts(tmp_path)
    assert found["steering"] == [tmp_path / ".kiro" / "steering" / "product.md"]
    assert found["requirements"] == [tmp_path / ".kiro" / "specs" / "checkout" / "requirements.md"]


def test_find_kiro_artifacts_steering_only(tmp_path):
    _write_kiro(tmp_path, steering={"product": KIRO_STEERING_MD})
    found = fi.find_kiro_artifacts(tmp_path)
    assert len(found["steering"]) == 1
    assert found["requirements"] == []


def test_find_kiro_artifacts_requirements_only(tmp_path):
    _write_kiro(tmp_path, specs={"checkout": KIRO_REQUIREMENTS_MD})
    found = fi.find_kiro_artifacts(tmp_path)
    assert found["steering"] == []
    assert len(found["requirements"]) == 1


def test_find_kiro_artifacts_none(tmp_path):
    found = fi.find_kiro_artifacts(tmp_path)
    assert found["steering"] == []
    assert found["requirements"] == []


def test_specs_dir_present_but_no_spec_md_is_not_matched(tmp_path):
    # specs/<feature>/ exists but doesn't follow the spec-kit spec.md shape -- must not match.
    (tmp_path / "specs" / "unrelated").mkdir(parents=True)
    (tmp_path / "specs" / "unrelated" / "notes.md").write_text("not a spec-kit file\n")
    found = fi.find_spec_kit_artifacts(tmp_path)
    assert found["specs"] == []


# =====================================================================================
# extract_requirement_lines() — EARS-informed, not a full parser
# =====================================================================================
def test_extract_requirement_lines_ears_when_then_shall():
    lines = fi.extract_requirement_lines(
        "1. WHEN the cart is empty THEN the system SHALL disable the checkout button\n"
    )
    assert lines == ["WHEN the cart is empty THEN the system SHALL disable the checkout button"]


def test_extract_requirement_lines_ears_if_shall():
    lines = fi.extract_requirement_lines("IF payment fails THEN the system SHALL retry.\n")
    assert lines == ["IF payment fails THEN the system SHALL retry."]


def test_extract_requirement_lines_ubiquitous_shall_with_no_trigger():
    lines = fi.extract_requirement_lines("The system SHALL log every failed login attempt.\n")
    assert lines == ["The system SHALL log every failed login attempt."]


def test_extract_requirement_lines_fr_id_lines():
    lines = fi.extract_requirement_lines(
        "- **FR-001**: System MUST allow a user to reset their password.\n"
        "- **SC-002**: 99% uptime measured monthly.\n"
    )
    assert "FR-001: System MUST allow a user to reset their password." in lines
    assert "SC-002: 99% uptime measured monthly." in lines


def test_extract_requirement_lines_user_story():
    lines = fi.extract_requirement_lines(
        "As a shopper, I want to check out quickly, so that I don't abandon my cart.\n"
    )
    assert lines == ["As a shopper, I want to check out quickly, so that I don't abandon my cart."]


def test_extract_requirement_lines_user_story_with_bold_prefix():
    # Kiro's "**User Story:** As a ..." shape -- bold prefix must not block detection.
    lines = fi.extract_requirement_lines(
        "**User Story:** As a shopper, I want to save my card, so that checkout is faster.\n"
    )
    assert any("As a shopper, I want to save my card" in ln for ln in lines)


def test_extract_requirement_lines_ignores_fenced_code_blocks():
    text = (
        "Some intro text.\n"
        "```bash\n"
        "echo 'the system SHALL do nothing, this is just an example'\n"
        "```\n"
        "The system SHALL be the only real requirement here.\n"
    )
    lines = fi.extract_requirement_lines(text)
    assert lines == ["The system SHALL be the only real requirement here."]


def test_extract_requirement_lines_plain_prose_yields_nothing():
    lines = fi.extract_requirement_lines(
        "This is just background context with no imperative language at all.\n"
    )
    assert lines == []


def test_extract_requirement_lines_empty_text_returns_empty():
    assert fi.extract_requirement_lines("") == []


# =====================================================================================
# extract_section_outline() — header + lead-line fallback signal
# =====================================================================================
def test_extract_section_outline_basic():
    outline = fi.extract_section_outline(CONSTITUTION_MD)
    titles = dict(outline)
    assert titles["I. Simplicity First"] == "Every feature starts with the simplest design that could work."
    assert titles["Governance"] == "This constitution supersedes all other engineering practices."


def test_extract_section_outline_ignores_h1_and_h4():
    text = "# Title (h1, ignored)\n\nsome lead\n\n#### Deep header (h4, ignored)\n\nother lead\n"
    outline = fi.extract_section_outline(text)
    assert outline == []


def test_extract_section_outline_header_with_no_body_has_empty_lead():
    text = "## Empty Section\n### Next Section\nbody text\n"
    outline = fi.extract_section_outline(text)
    titles = dict(outline)
    assert titles["Empty Section"] == ""
    assert titles["Next Section"] == "body text"


def test_extract_section_outline_empty_text_returns_empty():
    assert fi.extract_section_outline("") == []


# =====================================================================================
# ingest_*_doc() — per-artifact-kind ingestion
# =====================================================================================
def test_ingest_requirement_doc_spec_kit_spec(tmp_path):
    path = tmp_path / "spec.md"
    path.write_text(SPEC_KIT_SPEC_MD, encoding="utf-8")
    candidates = fi.ingest_requirement_doc(path, tmp_path)
    kinds = {c.kind for c in candidates}
    assert "user-story" in kinds
    assert "requirement" in kinds
    assert any("FR-001" in c.text for c in candidates)
    assert any("SC-001" in c.text for c in candidates)
    assert all(c.source == "spec.md" for c in candidates)


def test_ingest_requirement_doc_falls_back_to_section_outline_when_prose_only(tmp_path):
    path = tmp_path / "spec.md"
    path.write_text(SPEC_KIT_SPEC_PROSE_ONLY_MD, encoding="utf-8")
    candidates = fi.ingest_requirement_doc(path, tmp_path)
    assert candidates, "a prose-only spec must still surface its section outline"
    assert all(c.kind == "context" for c in candidates)
    assert any("Overview" in c.text for c in candidates)


def test_ingest_requirement_doc_kiro_requirements(tmp_path):
    path = tmp_path / "requirements.md"
    path.write_text(KIRO_REQUIREMENTS_MD, encoding="utf-8")
    candidates = fi.ingest_requirement_doc(path, tmp_path)
    texts = [c.text for c in candidates]
    assert any("WHEN the cart is empty" in t for t in texts)
    assert any("IF payment fails" in t for t in texts)
    assert any(c.kind == "user-story" for c in candidates)


def test_ingest_principle_doc_constitution(tmp_path):
    path = tmp_path / "constitution.md"
    path.write_text(CONSTITUTION_MD, encoding="utf-8")
    candidates = fi.ingest_principle_doc(path, tmp_path)
    assert any(c.kind == "principle" and "Simplicity First" in c.text for c in candidates)
    # The Test-First principle's MUST sentence is also surfaced as a bonus bare requirement.
    assert any(c.kind == "requirement" and "Tests MUST be written" in c.text for c in candidates)


def test_ingest_principle_doc_steering(tmp_path):
    path = tmp_path / "product.md"
    path.write_text(KIRO_STEERING_MD, encoding="utf-8")
    candidates = fi.ingest_principle_doc(path, tmp_path)
    assert any(c.kind == "principle" and "Target Users" in c.text for c in candidates)


def test_ingest_doc_missing_file_returns_empty(tmp_path):
    assert fi.ingest_requirement_doc(tmp_path / "nope.md", tmp_path) == []
    assert fi.ingest_principle_doc(tmp_path / "nope.md", tmp_path) == []


def test_ingest_doc_empty_file_returns_empty_not_crash(tmp_path):
    path = tmp_path / "empty.md"
    path.write_text("", encoding="utf-8")
    assert fi.ingest_requirement_doc(path, tmp_path) == []
    assert fi.ingest_principle_doc(path, tmp_path) == []


def test_ingest_doc_binary_garbage_does_not_crash(tmp_path):
    path = tmp_path / "garbage.md"
    path.write_bytes(b"\x80\x81\xff not valid utf-8 \x00 garbage")
    # Must not raise; content simply yields no recognizable candidates.
    assert fi.ingest_requirement_doc(path, tmp_path) == []


# =====================================================================================
# scan() — the four required coverage shapes: both / only-one / neither / malformed
# =====================================================================================
def test_scan_both_spec_kit_and_kiro_present(tmp_path):
    _write_spec_kit(tmp_path, constitution=CONSTITUTION_MD, specs={"user-auth": SPEC_KIT_SPEC_MD})
    _write_kiro(tmp_path, steering={"product": KIRO_STEERING_MD},
                specs={"checkout": KIRO_REQUIREMENTS_MD})
    result = fi.scan(tmp_path)
    assert result.found_anything is True
    sources = {c.source for c in result.candidates}
    assert ".specify/memory/constitution.md" in sources
    assert "specs/user-auth/spec.md" in sources
    assert ".kiro/steering/product.md" in sources
    assert ".kiro/specs/checkout/requirements.md" in sources


def test_scan_only_spec_kit_present(tmp_path):
    _write_spec_kit(tmp_path, constitution=CONSTITUTION_MD, specs={"user-auth": SPEC_KIT_SPEC_MD})
    result = fi.scan(tmp_path)
    assert result.found_anything is True
    assert result.kiro["steering"] == []
    assert result.kiro["requirements"] == []
    assert all(not c.source.startswith(".kiro") for c in result.candidates)


def test_scan_only_kiro_present(tmp_path):
    _write_kiro(tmp_path, steering={"product": KIRO_STEERING_MD},
                specs={"checkout": KIRO_REQUIREMENTS_MD})
    result = fi.scan(tmp_path)
    assert result.found_anything is True
    assert result.spec_kit["constitution"] is None
    assert result.spec_kit["specs"] == []
    assert all(c.source.startswith(".kiro") for c in result.candidates)


def test_scan_neither_present_is_graceful_no_op(tmp_path):
    result = fi.scan(tmp_path)
    assert result.found_anything is False
    assert result.candidates == []


def test_scan_malformed_empty_and_binary_files_do_not_crash(tmp_path):
    (tmp_path / ".specify" / "memory").mkdir(parents=True)
    (tmp_path / ".specify" / "memory" / "constitution.md").write_text("", encoding="utf-8")
    (tmp_path / ".kiro" / "specs" / "x").mkdir(parents=True)
    (tmp_path / ".kiro" / "specs" / "x" / "requirements.md").write_bytes(
        b"\x80\x81\xff garbage \x00"
    )
    result = fi.scan(tmp_path)  # must not raise
    assert result.found_anything is True
    assert result.candidates == []


# =====================================================================================
# render_report() / result_to_json()
# =====================================================================================
def test_render_report_not_found_message(tmp_path):
    report = fi.render_report(fi.scan(tmp_path))
    assert "No GitHub spec-kit or AWS Kiro artifacts found" in report
    assert "no-op, not an error" in report


def test_render_report_includes_both_vendor_sections_when_both_present(tmp_path):
    _write_spec_kit(tmp_path, constitution=CONSTITUTION_MD)
    _write_kiro(tmp_path, steering={"product": KIRO_STEERING_MD})
    report = fi.render_report(fi.scan(tmp_path))
    assert "GitHub spec-kit" in report
    assert "AWS Kiro" in report
    assert "NOT sealed" in report


def test_render_report_omits_vendor_section_when_absent(tmp_path):
    _write_kiro(tmp_path, steering={"product": KIRO_STEERING_MD})
    report = fi.render_report(fi.scan(tmp_path))
    assert "GitHub spec-kit" not in report
    assert "AWS Kiro" in report


def test_render_report_footer_present_when_found(tmp_path):
    _write_spec_kit(tmp_path, constitution=CONSTITUTION_MD)
    report = fi.render_report(fi.scan(tmp_path))
    assert "Stage 0 Frame was not invoked" in report
    assert "acceptance_suite.criteria" in report


def test_render_report_file_with_zero_candidates_says_so(tmp_path):
    (tmp_path / ".specify" / "memory").mkdir(parents=True)
    (tmp_path / ".specify" / "memory" / "constitution.md").write_text("", encoding="utf-8")
    report = fi.render_report(fi.scan(tmp_path))
    assert "review the file by hand" in report


def test_result_to_json_shape(tmp_path):
    _write_spec_kit(tmp_path, constitution=CONSTITUTION_MD, specs={"user-auth": SPEC_KIT_SPEC_MD})
    data = fi.result_to_json(fi.scan(tmp_path))
    assert data["sealed"] is False
    assert data["found_anything"] is True
    assert data["spec_kit"]["constitution"] == ".specify/memory/constitution.md"
    assert data["spec_kit"]["specs"] == ["specs/user-auth/spec.md"]
    assert isinstance(data["candidates"], list) and data["candidates"]
    assert {"source", "kind", "text"} <= set(data["candidates"][0].keys())


def test_result_to_json_is_actually_json_serializable(tmp_path):
    _write_kiro(tmp_path, specs={"checkout": KIRO_REQUIREMENTS_MD})
    json.dumps(fi.result_to_json(fi.scan(tmp_path)))  # must not raise


# =====================================================================================
# CLI-level: full subprocess round trip
# =====================================================================================
def _run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True,
                          text=True, encoding="utf-8")


def test_cli_default_directory_is_cwd(tmp_path):
    _write_spec_kit(tmp_path, constitution=CONSTITUTION_MD)
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True,
                            encoding="utf-8", cwd=str(tmp_path))
    assert result.returncode == 0
    assert "GitHub spec-kit" in result.stdout


def test_cli_explicit_directory_arg(tmp_path):
    _write_kiro(tmp_path, steering={"product": KIRO_STEERING_MD})
    result = _run(str(tmp_path))
    assert result.returncode == 0
    assert "AWS Kiro" in result.stdout


def test_cli_exit_code_zero_when_nothing_found(tmp_path):
    result = _run(str(tmp_path))
    assert result.returncode == 0


def test_cli_exit_code_zero_when_artifacts_found(tmp_path):
    _write_spec_kit(tmp_path, constitution=CONSTITUTION_MD)
    result = _run(str(tmp_path))
    assert result.returncode == 0


def test_cli_json_flag_emits_valid_json(tmp_path):
    _write_spec_kit(tmp_path, specs={"user-auth": SPEC_KIT_SPEC_MD})
    result = _run(str(tmp_path), "--json")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["found_anything"] is True
    assert data["sealed"] is False


def test_cli_out_writes_file_and_prints_confirmation(tmp_path):
    _write_spec_kit(tmp_path, constitution=CONSTITUTION_MD)
    out = tmp_path / "candidates.txt"
    result = _run(str(tmp_path), "--out", str(out))
    assert result.returncode == 0
    assert "wrote candidate summary to" in result.stdout
    assert out.is_file()
    assert "GitHub spec-kit" in out.read_text(encoding="utf-8")


def test_cli_out_refuses_reserved_contract_yaml_name(tmp_path):
    _write_spec_kit(tmp_path, constitution=CONSTITUTION_MD)
    out = tmp_path / "contract.yaml"
    result = _run(str(tmp_path), "--out", str(out))
    assert result.returncode == 2
    assert "reserved" in result.stderr
    assert not out.exists()


def test_cli_out_refuses_reserved_mission_yaml_name(tmp_path):
    _write_spec_kit(tmp_path, constitution=CONSTITUTION_MD)
    out = tmp_path / "mission.yaml"
    result = _run(str(tmp_path), "--out", str(out))
    assert result.returncode == 2
    assert not out.exists()


def test_cli_out_refuses_reserved_name_case_insensitively(tmp_path):
    _write_spec_kit(tmp_path, constitution=CONSTITUTION_MD)
    out = tmp_path / "Contract.YAML"
    result = _run(str(tmp_path), "--out", str(out))
    assert result.returncode == 2
    assert not out.exists()


def test_cli_nonexistent_directory_errors(tmp_path):
    result = _run(str(tmp_path / "does-not-exist"))
    assert result.returncode == 2
    assert "not a directory" in result.stderr


def test_cli_never_writes_contract_or_mission_yaml_as_a_side_effect(tmp_path):
    # Pure content-ingestion helper: a normal scan (no --out at all) must never create any
    # file anywhere, sealed contract or otherwise.
    _write_spec_kit(tmp_path, constitution=CONSTITUTION_MD, specs={"user-auth": SPEC_KIT_SPEC_MD})
    before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    result = _run(str(tmp_path))
    after = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert result.returncode == 0
    assert before == after
