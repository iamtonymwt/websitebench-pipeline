#!/usr/bin/env python3
"""The candidate's entry point stays in the foreground.

The ABI requires a foreground process that handles SIGTERM. One that
daemonises leaves the harness unable to stop it, and the next run
inherits a port that is already bound.
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


executable = ROOT / "executable"
if not executable.is_file():
    fail("no executable at the candidate root")
body = executable.read_text(encoding="utf-8", errors="replace")
if re.search(r"(?m)^\s*(nohup|setsid)\b", body) or "&\n" in body.replace(" ", ""):
    fail("the executable appears to background its process")
if not re.search(r"(?m)^\s*exec\b", body) and "SIGTERM" not in body:
    fail("the executable neither execs nor handles SIGTERM")
ok("the executable runs in the foreground")
