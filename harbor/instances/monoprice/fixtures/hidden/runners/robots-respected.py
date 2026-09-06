#!/usr/bin/env python3
"""No page under a source robots Disallow rule was reproduced from capture.

/cart, /Checkout, /sslchkout and /myaccount are disallowed on the source.
A candidate may implement them; it must not ship a copy of the source's.
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


MARKERS = ("sslchkout", "ProductSavedListUpdate", "ProductShareOnBlog")
hits = []
for path, body in text_files({".html", ".htm"}):
    for marker in MARKERS:
        if marker in body:
            hits.append(f"{path.relative_to(ROOT)}: {marker}")
if hits:
    fail(f"markup from robots-disallowed source pages: {hits[:5]}")
ok("no captured markup from robots-disallowed paths")
