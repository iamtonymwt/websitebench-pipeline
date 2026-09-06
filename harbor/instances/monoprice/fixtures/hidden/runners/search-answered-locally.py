#!/usr/bin/env python3
"""Search and its type-ahead are answered by the candidate itself.

On the source the type-ahead is a third-party call on every keystroke.
A candidate that proxies it would leave the machine on a control the
reference never leaves it on -- and no page-load check would see it.
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


THIRD_PARTY = ("unbxdapi.com", "dxpapi.com", "bloomreach", "hawksearch.com",
               "searchspring", "algolia")
hits = []
for path, body in text_files({".py", ".js", ".ts", ".mjs", ".go", ".rb", ".html"}):
    low = body.lower()
    for name in THIRD_PARTY:
        if name in low and re.search(rf"https?://[^\s\"']*{re.escape(name)}", low):
            hits.append(f"{path.relative_to(ROOT)}: {name}")
if hits:
    fail(f"third-party search service referenced: {hits[:4]}")
ok("no third-party search service is called")
