#!/usr/bin/env python3
"""No outbound HTTP client is invoked against a non-loopback host.

The offline requirement is about behaviour, not intent. This looks for a
request being made to something that is not this machine.
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


CALLS = (r"requests\.(?:get|post|put|delete)\(", r"urllib\.request\.urlopen\(",
         r"httpx\.(?:get|post|Client)\(", r"fetch\(\s*[\"']https?://",
         r"axios\.(?:get|post)\(\s*[\"']https?://")
hits = []
for path, body in text_files({".py", ".js", ".ts", ".mjs", ".go", ".rb"}):
    for pattern in CALLS:
        for match in re.finditer(pattern, body):
            window = body[match.start():match.start() + 200]
            if re.search(r"127\.0\.0\.1|localhost|\[::1\]", window):
                continue
            if re.search(r"https?://", window):
                hits.append(f"{path.relative_to(ROOT)}: {window[:60]}")
if hits:
    fail(f"outbound HTTP to a non-loopback host: {hits[:4]}")
ok("no outbound HTTP client targets a non-loopback host")
