"""Structural coverage of templates/verifier-library.yaml.

Nothing parsed this file before. A syntax error in any of the 13 recipes — or a snippet
that is not valid bash — shipped green, even though these snippets are copied verbatim
into users' verify.sh. Found the hard way: an unquoted ':' in a caveats string made the
whole library unloadable and the full suite still passed.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
LIBRARY = REPO / "templates" / "verifier-library.yaml"


def _recipes() -> list[dict]:
    data = yaml.safe_load(LIBRARY.read_text(encoding="utf-8"))
    key = "verifiers" if "verifiers" in data else next(iter(data))
    return data[key]


def test_library_parses():
    assert _recipes(), "verifier-library.yaml yielded no recipes"


def test_every_recipe_has_its_contract_fields():
    for recipe in _recipes():
        rid = recipe.get("id")
        assert rid, f"recipe without an id: {recipe}"
        for field in ("use_when", "snippet", "green_means"):
            assert recipe.get(field), f"{rid}: missing {field}"


def test_recipe_ids_are_unique():
    ids = [r["id"] for r in _recipes()]
    assert len(ids) == len(set(ids)), f"duplicate recipe ids in {ids}"


@pytest.mark.skipif(
    sys.platform.startswith("win") or not shutil.which("bash"),
    reason="snippet syntax check needs a POSIX bash",
)
@pytest.mark.parametrize("recipe", _recipes(), ids=lambda r: r["id"])
def test_snippet_is_valid_bash(recipe):
    # These snippets are copied straight into a verify.sh, so a syntax error here is a
    # broken gate in someone else's repo.
    result = subprocess.run(
        [shutil.which("bash"), "-n"], input=recipe["snippet"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"{recipe['id']}: {result.stderr}"


def test_critic_panel_keeps_its_isolation_canary():
    # Locks the gate on: a generated panel must plant the canary, not just the worked example.
    panel = next(r for r in _recipes() if r["id"] == "critic-panel")
    assert "CANARY_TOKEN" in panel["snippet"]
    assert "exit 3" in panel["snippet"]
    assert panel["green_means"].startswith("No critic quoted")
