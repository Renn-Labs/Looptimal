from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
LINT = ROOT / "scripts" / "loopprint-lint.py"
GREEN_DIR = Path(__file__).resolve().parent / "golden" / "green"
RED_DIR = Path(__file__).resolve().parent / "golden" / "red"


def _load_lint():
    spec = importlib.util.spec_from_file_location("loopprint_lint", LINT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lint_mod = _load_lint()
lint_spec = lint_mod.lint_spec
main = lint_mod.main


@pytest.mark.parametrize("path", sorted(GREEN_DIR.glob("*.yaml")))
def test_green_specs(path: Path):
    with open(path) as fh:
        spec = yaml.safe_load(fh)
    assert lint_spec(spec) == []


@pytest.mark.parametrize("path", sorted(RED_DIR.glob("*.yaml")))
def test_red_specs(path: Path):
    with open(path) as fh:
        spec = yaml.safe_load(fh)
    assert lint_spec(spec) != []


def test_main_exit_codes():
    green = GREEN_DIR / "morty.yaml"
    red = RED_DIR / "empty-verifier.yaml"
    assert main([str(LINT), str(green)]) == 0
    assert main([str(LINT), str(red)]) == 1


def test_main_subprocess_exit_codes():
    green = GREEN_DIR / "morty.yaml"
    red = RED_DIR / "empty-verifier.yaml"
    proc = subprocess.run(
        [sys.executable, str(LINT), str(green)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 0
    proc = subprocess.run(
        [sys.executable, str(LINT), str(red)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 1
