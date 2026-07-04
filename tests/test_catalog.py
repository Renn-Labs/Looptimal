"""Tests for scripts/loopprint-library.py — library catalog search, verify, and install."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LIBRARY = REPO / "scripts" / "loopprint-library.py"
SECRET_SCAN = REPO / "library" / "secret-scan"


def _load():
    spec = importlib.util.spec_from_file_location("loopprint_library", LIBRARY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lib = _load()


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(LIBRARY), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def _init_git_repo(path: Path, files: dict[str, str] | None = None) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=path, check=True, capture_output=True)
    if files:
        for name, content in files.items():
            fp = path / name
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


def test_consumer_repo_root_finds_parent_git_dir(tmp_path):
    repo = tmp_path / "repo"
    _init_git_repo(repo, {"README.md": "# repo\n"})
    nested = repo / "a" / "b"
    nested.mkdir(parents=True)

    assert lib._consumer_repo_root(nested) == repo.resolve()


def test_consumer_repo_root_falls_back_outside_git_repo(tmp_path):
    plain = tmp_path / "plain" / "nested"
    plain.mkdir(parents=True)

    assert lib._consumer_repo_root(plain) == plain.resolve()


def test_consumer_repo_root_accepts_git_file_marker(tmp_path):
    repo = tmp_path / "worktree-like"
    nested = repo / "src"
    nested.mkdir(parents=True)
    (repo / ".git").write_text("gitdir: /tmp/example\n", encoding="utf-8")

    assert lib._consumer_repo_root(nested) == repo.resolve()


def _write_minimal_loop(loop_dir: Path, *, slug: str, verify_body: str) -> None:
    spec = {
        "schema_version": 1,
        "slug": slug,
        "created": "2026-07-02",
        "pattern": "spec-driven",
        "goal": "Synthetic loop for catalog security tests.",
        "state": {"path": f"loops/{slug}/state.md"},
        "verifier": {
            "kind": "lint",
            "command": "bash verify.sh",
            "green_means": "verifier command exists and runs",
        },
        "stop": {
            "success": "verifier GREEN",
            "max_iterations": 3,
            "budget": {"tokens": None, "wall_clock_minutes": 5},
            "halt_file": f"loops/{slug}/HALT",
        },
        "autonomy": "checkpoint",
        "human_checkpoints": [],
        "integrations": {
            "oh_my_claudecode": False,
            "subagent_isolation": False,
            "heavy_orchestrator": False,
        },
    }
    import yaml

    loop_dir.mkdir(parents=True, exist_ok=True)
    with open(loop_dir / "loop-spec.yaml", "w", encoding="utf-8") as fh:
        yaml.dump(spec, fh)
    (loop_dir / "verify.sh").write_text(verify_body, encoding="utf-8")


def _write_cant_exec_loop(loop_dir: Path) -> None:
    spec = {
        "schema_version": 1,
        "slug": "cant-exec",
        "created": "2026-07-02",
        "pattern": "spec-driven",
        "goal": "Synthetic loop whose verifier cannot execute in any environment.",
        "state": {"path": "loops/cant-exec/state.md"},
        "verifier": {
            "kind": "lint",
            "command": "bash verify.sh",
            "green_means": "verifier command exists and runs",
        },
        "stop": {
            "success": "verifier GREEN",
            "max_iterations": 3,
            "budget": {"tokens": None, "wall_clock_minutes": 5},
            "halt_file": "loops/cant-exec/HALT",
        },
        "autonomy": "checkpoint",
        "human_checkpoints": [],
        "integrations": {
            "oh_my_claudecode": False,
            "subagent_isolation": False,
            "heavy_orchestrator": False,
        },
    }
    import yaml

    loop_dir.mkdir(parents=True, exist_ok=True)
    with open(loop_dir / "loop-spec.yaml", "w", encoding="utf-8") as fh:
        yaml.dump(spec, fh)
    (loop_dir / "verify.sh").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        "nonexistent_command_loopprint_xyz_99999\n",
        encoding="utf-8",
    )


# ---- search -------------------------------------------------------------------

def test_search_finds_secret_scan():
    p = _run(REPO, "search", "secret", "--json")
    assert p.returncode == 0, p.stderr
    data = json.loads(p.stdout)
    slugs = {row["slug"] for row in data["loops"]}
    assert "secret-scan" in slugs


# ---- verify -------------------------------------------------------------------

def test_verify_green_on_clean_scratch_repo(tmp_path):
    repo = tmp_path / "clean"
    _init_git_repo(repo, {"README.md": "# clean\n"})
    p = _run(repo, "verify", "secret-scan")
    assert p.returncode == 0, p.stderr + p.stdout
    assert "GREEN" in p.stdout


def test_verify_red_on_scratch_repo_with_planted_secret(tmp_path):
    repo = tmp_path / "dirty"
    _init_git_repo(repo, {
        "README.md": "# dirty\n",
        "leak.txt": f"aws_key = {_FAKE_AWS_ACCESS_KEY_ID}\n",
    })
    p = _run(repo, "verify", "secret-scan")
    assert p.returncode == 0, p.stderr + p.stdout
    assert "RED" in p.stdout


def test_verify_red_when_secret_shares_line_with_url_comment(tmp_path):
    repo = tmp_path / "url-comment-leak"
    _init_git_repo(repo, {
        "README.md": "# dirty\n",
        "leak.txt": (
            f"aws_key = {_FAKE_AWS_ACCESS_KEY_ID}  # see https://github.com/example/docs\n"
        ),
    })
    p = _run(repo, "verify", "secret-scan")
    assert p.returncode == 0, p.stderr + p.stdout
    assert "RED" in p.stdout


_SHA256 = "f51f8b540b80c0afe446d5b25d28f9886ce3220e2813b71bc9cc1e1b16ade6fe"
_GIT_COMMIT = "326a2b489411a20ed742ff13701be39ba00063c8"
_FAKE_AWS_ACCESS_KEY_ID = "AKIA" + "IOSFODNN7EXAMPLE"
_SSH_PUBKEY = (
    "user@example.com ssh-ed25519 "
    "AAAAC3NzaC1lZDI1NTE5AAAAIGMQu4u13T0ZCz00OGvcEXFk4zVJcVwB+gIaJD7Qs1El"
)


def test_verify_green_on_hashes_public_keys_and_git_urls(tmp_path):
    """Regression: bare hex digests, ssh public keys, and git+https commit refs are not secrets."""
    repo = tmp_path / "benign-artifacts"
    _init_git_repo(repo, {
        "README.md": "# benign artifacts\n",
        "evidence.json": f'{{"contract_hash": "{_SHA256}"}}\n',
        "allowed_signers": f"{_SSH_PUBKEY}\n",
        "ci-snippet.yml": (
            f'pip install "git+https://github.com/example/pkg.git@{_GIT_COMMIT}"\n'
        ),
    })
    p = _run(repo, "verify", "secret-scan")
    assert p.returncode == 0, p.stderr + p.stdout
    assert "GREEN" in p.stdout


def test_verify_akia_with_url_comment_stays_red(tmp_path):
    """Regression: high-confidence AKIA is never suppressed by a URL on the same line."""
    repo = tmp_path / "akia-url-comment"
    _init_git_repo(repo, {
        "README.md": "# dirty\n",
        "leak.txt": (
            f"{_FAKE_AWS_ACCESS_KEY_ID}  # https://github.com/example/docs\n"
        ),
    })
    p = _run(repo, "verify", "secret-scan")
    assert p.returncode == 0, p.stderr + p.stdout
    assert "RED" in p.stdout


def test_verify_cant_execute_on_missing_command(tmp_path):
    bad = tmp_path / "cant-exec-loop"
    _write_cant_exec_loop(bad)
    p = _run(tmp_path, "verify", str(bad))
    assert p.returncode == 1, p.stderr + p.stdout
    assert "CANT_EXECUTE" in p.stdout


# ---- install ------------------------------------------------------------------

def test_install_red_on_arrival_with_planted_secret(tmp_path):
    consumer = tmp_path / "consumer-dirty"
    _init_git_repo(consumer, {
        "README.md": "# app\n",
        "config.env": f"AWS_ACCESS_KEY_ID={_FAKE_AWS_ACCESS_KEY_ID}\n",
    })
    p = _run(REPO, "install", "secret-scan", "--dest", str(consumer))
    assert p.returncode == 0, p.stderr + p.stdout
    assert "RED on arrival" in p.stdout
    installed = consumer / "secret-scan"
    assert installed.is_dir()
    assert (installed / "verify.sh").is_file()
    verdict_path = installed / "install-verdict.json"
    assert verdict_path.is_file()
    record = json.loads(verdict_path.read_text(encoding="utf-8"))
    assert record["slug"] == "secret-scan"
    assert record["verdict"] == "RED"
    assert record["verify_exit"] == 1


def test_install_green_on_clean_repo(tmp_path):
    consumer = tmp_path / "consumer-clean"
    _init_git_repo(consumer, {"README.md": "# clean app\n"})
    p = _run(REPO, "install", "secret-scan", "--dest", str(consumer))
    assert p.returncode == 0, p.stderr + p.stdout
    assert "gate passes" in p.stdout
    record = json.loads((consumer / "secret-scan" / "install-verdict.json").read_text(encoding="utf-8"))
    assert record["verdict"] == "GREEN"
    assert record["verify_exit"] == 0


def test_install_refuses_cant_execute_and_writes_nothing(tmp_path):
    lib_root = tmp_path / "library"
    _write_cant_exec_loop(lib_root / "cant-exec")
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    p = _run(tmp_path, "install", "cant-exec", "--dest", str(consumer))
    assert p.returncode == 1, p.stderr + p.stdout
    assert "REFUSE" in p.stderr or "REFUSE" in p.stdout
    assert not (consumer / "cant-exec").exists()


@pytest.mark.parametrize("evil_slug", ["../evil", "/tmp/evil-abs"])
def test_install_refuses_path_traversal_slug_and_writes_nothing(tmp_path, evil_slug):
    lib_root = tmp_path / "library"
    _write_minimal_loop(
        lib_root / "evil-loop",
        slug=evil_slug,
        verify_body="#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n",
    )
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    p = _run(tmp_path, "install", "evil-loop", "--dest", str(consumer))
    assert p.returncode == 1, p.stderr + p.stdout
    assert "REFUSE" in p.stderr
    assert list(consumer.iterdir()) == []


def test_install_refuses_syntax_broken_verify_and_writes_nothing(tmp_path):
    lib_root = tmp_path / "library"
    _write_minimal_loop(
        lib_root / "broken-syntax",
        slug="broken-syntax",
        verify_body="#!/usr/bin/env bash\nset -euo pipefail\nif [\n",
    )
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    p = _run(tmp_path, "install", "broken-syntax", "--dest", str(consumer))
    assert p.returncode == 1, p.stderr + p.stdout
    assert "REFUSE" in p.stderr
    assert "CANT_EXECUTE" not in p.stdout  # refusal before install verdict line
    assert not (consumer / "broken-syntax").exists()


# ---- unit coverage of helpers -------------------------------------------------

def test_classify_verify_exit():
    assert lib._classify_verify_exit(0) == "GREEN"
    assert lib._classify_verify_exit(1) == "RED"
    assert lib._classify_verify_exit(125) == "RED"
    assert lib._classify_verify_exit(126) == "CANT_EXECUTE"
    assert lib._classify_verify_exit(127) == "CANT_EXECUTE"
