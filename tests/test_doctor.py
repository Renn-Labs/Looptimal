from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCTOR = ROOT / "scripts" / "loopprint-doctor.py"


def test_doctor_json_output():
    proc = subprocess.run(
        [sys.executable, str(DOCTOR), "--json"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode in (0, 1)
    data = json.loads(proc.stdout)
    assert "findings" in data
    assert "counts" in data


def _load_doctor():
    """Import the hyphenated doctor script as a module so its functions can be unit-tested."""
    spec = importlib.util.spec_from_file_location("loopprint_doctor", DOCTOR)
    assert spec and spec.loader  # DOCTOR is a known-present file — also narrows Optional for the type checker
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_enabled_loopprint_plugins_filters_and_merges(tmp_path):
    doctor = _load_doctor()
    (tmp_path / "settings.json").write_text(
        json.dumps({"enabledPlugins": {"loopprint@x": True, "other@y": True, "loopprint@z": False}})
    )
    (tmp_path / "settings.local.json").write_text(
        json.dumps({"enabledPlugins": {"loopprint@z": True}})  # local flips z on -> local wins
    )
    assert sorted(doctor._enabled_loopprint_plugins(tmp_path)) == ["loopprint@x", "loopprint@z"]


def test_enabled_loopprint_plugins_ignores_non_dict_roots(tmp_path):
    # malformed config (valid JSON, wrong shape) must not raise — the doctor has to survive broken installs
    doctor = _load_doctor()
    (tmp_path / "settings.json").write_text("null")
    (tmp_path / "settings.local.json").write_text("[1, 2, 3]")
    assert doctor._enabled_loopprint_plugins(tmp_path) == []


def test_enabled_loopprint_plugins_no_files(tmp_path):
    doctor = _load_doctor()
    assert doctor._enabled_loopprint_plugins(tmp_path) == []


def _dual_registration_finding(doctor, monkeypatch, cfg_dir, *, link, enabled):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(cfg_dir))
    cfg_dir.mkdir(parents=True, exist_ok=True)
    if enabled:
        (cfg_dir / "settings.json").write_text(json.dumps({"enabledPlugins": {"loopprint@renn-labs": True}}))
    if link:
        skills = cfg_dir / "skills"
        skills.mkdir(parents=True, exist_ok=True)
        (skills / "loopprint").symlink_to(ROOT, target_is_directory=True)
    r = doctor.Report(fix=False)
    doctor.check_dual_registration(r)
    return r.findings[-1]


def test_dual_registration_warns_on_collision(tmp_path, monkeypatch):
    f = _dual_registration_finding(_load_doctor(), monkeypatch, tmp_path, link=True, enabled=True)
    assert f["check"] == "dual_registration"
    assert f["status"] == "WARN"
    assert "loopprint@renn-labs" in f["detail"]


def test_dual_registration_ok_when_plugin_only(tmp_path, monkeypatch):
    f = _dual_registration_finding(_load_doctor(), monkeypatch, tmp_path, link=False, enabled=True)
    assert f["status"] == "OK"


def test_dual_registration_ok_when_folder_only(tmp_path, monkeypatch):
    f = _dual_registration_finding(_load_doctor(), monkeypatch, tmp_path, link=True, enabled=False)
    assert f["status"] == "OK"


def test_dual_registration_skips_when_neither(tmp_path, monkeypatch):
    f = _dual_registration_finding(_load_doctor(), monkeypatch, tmp_path, link=False, enabled=False)
    assert f["status"] == "SKIP"


def test_check_available_providers_is_info_and_nonfailing():
    doctor = _load_doctor()
    r = doctor.Report(fix=False)
    doctor.check_available_providers(r)
    findings = [f for f in r.findings if f["check"] == "available_providers"]
    assert len(findings) == 1, "expected exactly one available_providers finding"
    assert findings[0]["status"] == "INFO"
    assert r.counts()["FAIL"] == 0, "INFO finding must not increment FAIL count"


def test_check_available_providers_zero_providers_ok(monkeypatch):
    import shutil as _shutil
    doctor = _load_doctor()
    monkeypatch.setattr(doctor.shutil, "which", lambda _: None)
    r = doctor.Report(fix=False)
    doctor.check_available_providers(r)
    f = next(f for f in r.findings if f["check"] == "available_providers")
    assert f["status"] == "INFO"
    assert "none detected" in f["detail"]
    assert r.counts()["FAIL"] == 0
