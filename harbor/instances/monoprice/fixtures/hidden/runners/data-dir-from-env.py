#!/usr/bin/env python3
"""The candidate puts its state in DATA_DIR.

The harness supplies a data directory and resets it between runs. A build
that writes elsewhere carries state across runs, which makes a cart from
one case visible to another.
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


for _, body in text_files({".py", ".js", ".ts", ".mjs", ".go", ".rb", ".sh"}):
    if re.search(r"\bDATA_DIR\b", body):
        ok("DATA_DIR is read by the candidate")
fail("nothing in the candidate reads DATA_DIR")
