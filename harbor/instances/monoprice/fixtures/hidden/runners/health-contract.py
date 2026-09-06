#!/usr/bin/env python3
"""The candidate names the health path and its exact response.

The harness polls /__websitebench/health and compares {"status": "ok"}
literally. Extra keys are a difference in the one response it reads.
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


path_seen = response_seen = False
for _, body in text_files({".py", ".js", ".ts", ".mjs", ".go", ".rb", ".java",
                           ".json", ".yaml", ".yml", ".sh"}):
    if "__websitebench/health" in body:
        path_seen = True
    if re.search(r'"status"\s*:\s*"ok"', body) or "'status': 'ok'" in body:
        response_seen = True
    if path_seen and response_seen:
        ok("health path and exact ok response are declared")
fail(f"health path declared: {path_seen}; exact ok response declared: {response_seen}")
