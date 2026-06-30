#!/usr/bin/env python3
"""C1 oracle (sealed, BEHAVIORAL): the pre-fix repro must no longer reproduce.
Imports the live module the executor produced and exercises the missing-project path -
a static string in a comment cannot satisfy it, only the real 404 code path can."""
import importlib.util, pathlib, sys
src = pathlib.Path("src/api/project_lookup.py")
if not src.exists():
    sys.exit("repro target missing")
spec = importlib.util.spec_from_file_location("project_lookup", src)
mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
    resp = mod.get_project("missing-id", {})
except Exception as exc:
    sys.exit("endpoint raised - bug still live: " + str(exc))
sys.exit(0 if getattr(resp, "status", None) == 404 else 1)
