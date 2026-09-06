#!/usr/bin/env python3
"""Shipped code does not reach for the source's live hosts.

The runtime must make no request off the machine. A reference to the
live site in shipped code is either a request waiting to happen or a
rewrite that was missed -- and a missed rewrite reports as closure.
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


HOSTS = ("www.monoprice.com", "images.monoprice.com",
         "cdn.prod.website-files.com")
hits = []
for path, body in text_files({".py", ".js", ".ts", ".mjs", ".go", ".rb"}):
    # A comment or a docstring naming the source is documentation, not a
    # request. Only flag it inside a string that looks like a URL in use.
    for host in HOSTS:
        for match in re.finditer(rf"https?://{re.escape(host)}/[^\s\"'`)]+", body):
            line_start = body.rfind("\n", 0, match.start()) + 1
            line = body[line_start:match.start()]
            if line.lstrip().startswith(("#", "//", "*")):
                continue
            hits.append(f"{path.relative_to(ROOT)}: {match.group(0)[:70]}")
if hits:
    fail(f"live source-host URLs in shipped code: {hits[:5]}")
ok("no live source-host URLs in shipped code")
