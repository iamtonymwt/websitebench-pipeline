"""Cut the source's own page shell out of a frozen page.

The cart, checkout and order pages are written by this project rather than
captured -- `/cart`, `/Checkout` and `/sslchkout` are all under robots Disallow
rules on the source, so no evidence of them exists. What they can honestly reuse
is the shell: the real header, navigation, search box and footer, with our own
content between them. That is the same arrangement the last two sites in this
family used, and it is why those pages look like the site instead of like a
different site with the same data.

Interior pages open their content region with exactly one `<div id="page-content">`.
The matching close is found by counting div nesting from there.

Counting nesting is only trustworthy if it is checked, so it is: the tail after
the split must still contain the footer and `</html>`, and the head must contain
the header and the search form. If either fails the tool writes nothing and
exits non-zero -- a shell split in the wrong place produces pages that look
plausible and are missing their footer, which no gate would notice.

    python3 tools/extract_page_shell.py --page clone/static/frozen/about-us.html.gz \
        --out clone/static/page-shell.html --report scope/page-shell.json
"""

from __future__ import annotations

import argparse
import gzip
import json
import pathlib
import re

OPENER = '<div id="page-content">'
DIV_TOKEN = re.compile(r"<div\b|</div\s*>", re.I)
CONTENT_MARK = "@@WB_CONTENT@@"
TITLE_MARK = "@@WB_TITLE@@"


def load(path: pathlib.Path) -> str:
    if path.suffix == ".gz":
        with gzip.open(path, "rb") as fh:
            return fh.read().decode("utf-8", "replace")
    return path.read_text(encoding="utf-8")


def split_shell(html: str) -> tuple[str, str] | None:
    start = html.find(OPENER)
    if start == -1 or html.count(OPENER) != 1:
        return None
    cursor = start + len(OPENER)
    depth = 1
    for match in DIV_TOKEN.finditer(html, cursor):
        depth += 1 if match.group(0).lower().startswith("<div") else -1
        if depth == 0:
            return html[:cursor], html[match.start():]
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    page = pathlib.Path(args.page)
    html = load(page)
    split = split_shell(html)
    checks: dict[str, bool] = {}
    if split is None:
        checks["content_region_located"] = False
        head = tail = ""
    else:
        head, tail = split
        checks["content_region_located"] = True
        # The head must be a real page opening.
        checks["head_has_doctype"] = html[:200].lower().lstrip().startswith("<!doctype")
        checks["head_has_header"] = "<header" in head.lower()
        checks["head_has_search_form"] = 'action="/search/index"' in head
        checks["head_has_title_tag"] = "<title" in head.lower()
        # The tail must be a real page ending. If the div count went wrong, the
        # footer ends up on the wrong side of the split and the page silently
        # loses it.
        #
        # The footer is checked by its element, not by its words. This site
        # renders it as a `<monoprice-footer>` custom element fed by
        # window.footerData, so none of its link text exists in the served
        # markup. Looking for "Customer Service" failed the split -- and the
        # split was right; the check was wrong.
        checks["tail_has_footer_element"] = "<monoprice-footer" in tail.lower()
        checks["tail_has_footer_data"] = "footerdata" in tail.lower()
        checks["tail_closes_html"] = "</html>" in tail.lower()
        checks["tail_not_absurdly_short"] = len(tail) > 20_000

    failed = [name for name, ok in checks.items() if not ok]
    report = {
        "schema_version": "monoprice.page-shell.v1",
        "donor_page": str(page),
        "checks": checks,
        "failed_checks": failed,
        "head_bytes": len(head),
        "tail_bytes": len(tail),
        "written": not failed,
    }
    pathlib.Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.report).write_text(json.dumps(report, indent=2) + "\n",
                                         encoding="utf-8")
    print(json.dumps(report, indent=2))
    if failed:
        print(f"\nREFUSING to write the shell: {failed}. A shell split at the "
              "wrong place yields pages that look right and have lost their "
              "footer or their head.")
        return 1

    # One replaceable title, so a cart page does not claim to be the donor page.
    shell = re.sub(r"(<title[^>]*>)(.*?)(</title>)", rf"\1{TITLE_MARK}\3", head,
                   count=1, flags=re.I | re.S) + CONTENT_MARK + tail
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(shell, encoding="utf-8")
    print(f"\nwrote {out} ({len(shell)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
