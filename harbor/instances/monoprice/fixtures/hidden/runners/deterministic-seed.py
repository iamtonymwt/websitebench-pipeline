#!/usr/bin/env python3
"""The candidate reads the SEED environment variable.

The harness sets SEED and expects runs to be reproducible. A build that
never reads it cannot honour that, and the divergence would show up as
flaky scoring rather than as a clear failure.
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
    if re.search(r"\bSEED\b", body):
        ok("SEED is read by the candidate")
fail("nothing in the candidate reads SEED")
