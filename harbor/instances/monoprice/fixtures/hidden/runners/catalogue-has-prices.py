#!/usr/bin/env python3
"""The candidate ships a product catalogue with names and prices.

A storefront that serves pages but knows no products cannot answer a
single journey. This is the cheapest possible check that the data layer
exists at all.
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


import json
best = None
for path in ROOT.rglob("*.json"):
    if not path.is_file() or path.stat().st_size < 10_000:
        continue
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (ValueError, OSError):
        continue
    items = data.get("products") if isinstance(data, dict) else None
    if isinstance(items, list) and len(items) > 100:
        priced = [p for p in items if isinstance(p, dict)
                  and p.get("price") is not None and p.get("name")]
        if best is None or len(priced) > best[1]:
            best = (path, len(priced), len(items))
if best is None:
    fail("no catalogue with more than 100 products found")
path, priced, total = best
if priced < total * 0.9:
    fail(f"{total - priced} of {total} products lack a name or price")
ok(f"catalogue with {priced} priced, named products")
