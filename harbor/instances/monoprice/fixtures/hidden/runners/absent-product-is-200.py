#!/usr/bin/env python3
"""The candidate treats a discontinued product as 200, not 404.

The source answers 200 with 'Products no longer Available' for 1,906 ids.
A candidate that 404s them differs from the source on a third of its
sitemap, and the difference is invisible to any status-code-based check.
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


for _, body in text_files({".py", ".js", ".ts", ".mjs", ".go", ".rb", ".html"}):
    if "no longer available" in body.lower():
        ok("the discontinued-product response is present in the candidate")
fail("nothing in the candidate mentions the discontinued-product response")
