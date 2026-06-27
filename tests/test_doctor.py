from __future__ import annotations

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
