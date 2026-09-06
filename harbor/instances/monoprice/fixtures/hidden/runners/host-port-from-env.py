#!/usr/bin/env python3
"""The candidate binds the HOST and PORT it is given.

The harness chooses the port. A build with a hard-coded port answers on
the wrong one and every case fails for a reason unrelated to the site.
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


host_seen = port_seen = False
for _, body in text_files({".py", ".js", ".ts", ".mjs", ".go", ".rb", ".sh"}):
    if re.search(r"\bHOST\b", body):
        host_seen = True
    if re.search(r"\bPORT\b", body):
        port_seen = True
    if host_seen and port_seen:
        ok("HOST and PORT are read from the environment")
fail(f"HOST read: {host_seen}; PORT read: {port_seen}")
