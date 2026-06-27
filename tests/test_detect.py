from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DETECT = ROOT / "scripts" / "loopprint-detect.py"


def _load_detect():
    spec = importlib.util.spec_from_file_location("loopprint_detect", DETECT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


detect_mod = _load_detect()
resolve = detect_mod.resolve


def test_empty_dir_returns_generic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    isolated_home = tmp_path / "home"
    isolated_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: isolated_home))
    binding, note = resolve(tmp_path)
    assert "generic" in note.lower()
    assert binding.get("harness") == "generic"


def test_repo_local_profile_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    isolated_home = tmp_path / "home"
    isolated_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: isolated_home))
    home_profile = isolated_home / ".loopprint"
    home_profile.mkdir()
    (home_profile / "profile.yaml").write_text("harness: home-harness\n", encoding="utf-8")
    profile_dir = tmp_path / ".loopprint"
    profile_dir.mkdir()
    profile = profile_dir / "profile.yaml"
    profile.write_text(
        "harness: custom-harness\n"
        "state_dir: loops/<slug>\n"
        "verifier:\n"
        "  default: pytest -q\n"
        "dispatch:\n"
        "  maker: maker\n"
        "  checker: checker\n"
        "runner: run-this-loop.sh\n",
        encoding="utf-8",
    )
    binding, note = resolve(tmp_path)
    assert "repo-local" in note.lower()
    assert binding.get("harness") == "custom-harness"
