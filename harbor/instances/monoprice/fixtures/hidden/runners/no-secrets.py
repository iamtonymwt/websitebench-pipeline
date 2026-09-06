#!/usr/bin/env python3
"""No credentials, tokens or keys are shipped in the candidate tree.

Nothing about reconstructing a public storefront requires a secret, so
any that appears is either a leak or a mistake.
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


PATTERNS = [
    (r"AKIA[0-9A-Z]{16}", "aws access key"),
    (r"sk_live_[0-9A-Za-z]{16,}", "stripe live key"),
    (r"sk_test_[0-9A-Za-z]{16,}", "stripe test key"),
    (r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", "private key"),
    (r"ghp_[0-9A-Za-z]{30,}", "github token"),
    (r"xox[baprs]-[0-9A-Za-z-]{10,}", "slack token"),
    (r"(?i)\bauthorization\s*[:=]\s*[\"']?bearer\s+[0-9A-Za-z._-]{20,}", "bearer token"),
]
hits = []
for path, body in text_files({".py", ".js", ".ts", ".json", ".yaml", ".yml",
                              ".env", ".sh", ".txt", ".cfg", ".ini"}):
    for pattern, label in PATTERNS:
        if re.search(pattern, body):
            hits.append(f"{path.relative_to(ROOT)}: {label}")
if hits:
    fail(f"secret-like material found: {hits[:5]}")
ok("no credentials, tokens or private keys in the tree")
