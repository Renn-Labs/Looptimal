#!/usr/bin/env python3
"""C2 oracle (sealed, BEHAVIORAL): baseline behavior must not regress, and no baseline
test was removed. Exercises the existing-project path (must still 200) + inventory intact."""
import importlib.util, pathlib, sys
src = pathlib.Path("src/api/project_lookup.py")
inv = pathlib.Path("sealed/baseline-inventory.txt")
if not src.exists() or not inv.exists():
    sys.exit("baseline target or inventory missing")
spec = importlib.util.spec_from_file_location("project_lookup", src)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
ok_existing = getattr(mod.get_project("p1", {"p1": {"id": "p1"}}), "status", None) == 200
need = ("test_existing_project_returns_200", "test_missing_project_returns_404")
ok_inv = all(n in inv.read_text() for n in need)
sys.exit(0 if ok_existing and ok_inv else 1)
