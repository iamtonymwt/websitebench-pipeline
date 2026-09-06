#!/usr/bin/env python3
"""The deployment ABI's two entry points exist and are executable.

compile.sh -> executable is the contract. A candidate that builds
perfectly and cannot be started scores nothing, and the failure would
otherwise surface only at run time.
"""
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(os.environ.get("WEBSITEBENCH_CANDIDATE_ROOT", ".")).resolve()


def fail(message):
    print(f"FAIL: {message}")
    sys.exit(1)


def ok(message):
    print(f"ok: {message}")
    sys.exit(0)


def text_files(suffixes, limit=20000):
    seen = 0
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        if path.stat().st_size > 4_000_000:
            continue
        seen += 1
        if seen > limit:
            return
        try:
            yield path, path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue


missing = [name for name in ("compile.sh", "executable")
           if not (ROOT / name).is_file()]
if missing:
    fail(f"missing deployment entry points: {missing}")
for name in ("compile.sh", "executable"):
    mode = (ROOT / name).stat().st_mode
    if not mode & 0o111:
        fail(f"{name} is not executable")
ok("compile.sh and executable are present and executable")
