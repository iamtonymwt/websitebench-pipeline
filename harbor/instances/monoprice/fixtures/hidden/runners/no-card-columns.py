#!/usr/bin/env python3
"""No schema anywhere can store a card number, CVV or expiry.

The boundary belongs in the schema, not in a comment promising not to
store payment data. This site's checkout settles against a local sandbox
and never accepts a card.
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


FORBIDDEN = ("card_number", "cardnumber", "card_no", "cvv", "cvc",
             "card_cvv", "exp_month", "exp_year", "expiry_date",
             "pan_number", "account_number")

# Match a *declaration*, not a mention.
#
# The first version searched for these words anywhere and failed on the comment
# that documents the boundary -- and on the test asserting the boundary holds.
# A check that flags the code proving it right is worse than no check: it
# trains whoever reads it to ignore the result.
#
# So: skip comment lines, and require the word to look like a column or field
# being defined rather than discussed.
COMMENT = re.compile(r"^\s*(?:#|//|--|\*|/\*)")
DECLARED = "|".join(FORBIDDEN)
DECLARATION = re.compile(
    rf"(?i)\b(?:{DECLARED})\b\s*"
    r"(?:TEXT|VARCHAR|CHAR|INTEGER|INT|NUMERIC|BLOB|REAL|STRING|"
    r"[:=]\s*(?!\s*[\"']?(?:None|null|false)\b))")

hits = []
for path, body in text_files({".py", ".sql", ".js", ".ts", ".go", ".rb", ".java"}):
    for number, line in enumerate(body.splitlines(), 1):
        if COMMENT.match(line):
            continue
        match = DECLARATION.search(line)
        if match:
            hits.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()[:60]}")
if hits:
    fail(f"payment-detail columns or fields declared: {hits[:5]}")
ok("no card, cvv or expiry column or field is declared anywhere")
