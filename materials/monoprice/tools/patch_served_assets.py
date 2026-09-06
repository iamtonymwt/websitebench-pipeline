"""Rewrite absolute references *inside* the served CSS and JS.

The freezer rewrites references in HTML. It does not reach inside the stylesheets
and scripts the clone serves, and those carry their own absolute URLs: a
`background-image: url(https://images.monoprice.com/...)` in a stylesheet, and a
handful of image bases built in JavaScript.

The runtime audit is what found this. Every one of these is invisible to a static
scan of the markup, and invisible to a link-closure audit, because they are not
links and they are not in the page -- they are in a file the page loads. The
browser asked for 60 distinct images on images.monoprice.com across 47 routes.

A run-time URL that cannot be reached by rewriting a file at all -- one assembled
from a hostname variable -- is handled the other way: the app answers the source's
own asset paths (`/cms_images/`, `/mp/`, `/productlargeimages/`) from the asset
tree, so the path resolves locally without any rewriting.

**This must run after anything that copies assets over the served tree**, or the
patches are silently reverted and nothing reports it.

    python3 tools/patch_served_assets.py --assets-dir source-assets \
        --report scope/served-asset-patches.json
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fetch_assets import WEBFLOW_HOSTS, asset_target  # noqa: E402

LOCAL_PREFIX = "/static/assets"
# Both schemes and protocol-relative. The logo was requested over plain http
# while everything else used https; a pattern that only matched https would have
# left the one reference that appears on 47 routes.
# Every host whose bytes we hold, not just monoprice's.
#
# This pattern named only images/www.monoprice.com, while the local host set had
# grown to include Webflow's. So a Webflow stylesheet and a Webflow JS chunk kept
# their absolute references to Webflow's CDN, the browser fetched two badge SVGs
# from the internet on all 48 shop-collection routes, and the patch report said
# "0 references rewritten" -- which reads like "nothing left to do" and meant
# "this pattern cannot see them".
_LOCAL_HOSTS = sorted({"images.monoprice.com", "www.monoprice.com",
                       "monoprice.com"} | set(WEBFLOW_HOSTS))
_LOCAL_HOST_ALTERNATION = "|".join(re.escape(h) for h in _LOCAL_HOSTS)
ABSOLUTE_REF = re.compile(
    rf"""(?P<url>(?:https?:)?//(?:{_LOCAL_HOST_ALTERNATION})/[^\s"'()\\]+)""",
    re.I)

TEXT_SUFFIXES = {".css", ".js", ".json", ".svg"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets-dir", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    assets_dir = pathlib.Path(args.assets_dir)
    rewritten: collections.Counter = collections.Counter()
    unresolved: collections.Counter = collections.Counter()
    files_changed: list[dict] = []

    for path in sorted(assets_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        # The cheap skip has to know about every host the pattern knows about.
        # It said `"monoprice.com/" not in text`, which skipped every Webflow
        # file before the pattern ran -- so widening the pattern changed nothing
        # and the report still said "0 rewritten". A fast path that is narrower
        # than the thing it is guarding silently disables it.
        if not any(f"{host}/" in text for host in _LOCAL_HOSTS):
            continue

        changes = 0
        misses = 0

        def replace(match: re.Match) -> str:
            nonlocal changes, misses
            raw = match.group("url")
            absolute = ("https:" + raw) if raw.startswith("//") else raw
            target = asset_target(absolute)
            if target is None:
                misses += 1
                unresolved[urllib.parse.urlsplit(absolute).path] += 1
                return raw
            host, local = target
            # Never point at bytes that are not here: that converts a remote
            # request into a local 404 and lets the closure report call it
            # resolved.
            if not (assets_dir / host / local).is_file():
                misses += 1
                unresolved[f"{host}/{local}"] += 1
                return raw
            changes += 1
            return f"{LOCAL_PREFIX}/{host}/{urllib.parse.quote(local)}"

        patched = ABSOLUTE_REF.sub(replace, text)
        if changes:
            rewritten[path.suffix.lower()] += changes
            files_changed.append({"file": str(path.relative_to(assets_dir)),
                                  "rewritten": changes, "unresolved": misses})
            if not args.dry_run:
                path.write_text(patched, encoding="utf-8")

    report = {
        "schema_version": "monoprice.served-asset-patches.v1",
        "assets_dir": str(assets_dir),
        "dry_run": args.dry_run,
        "references_rewritten": dict(rewritten),
        "references_rewritten_total": sum(rewritten.values()),
        "files_changed": len(files_changed),
        "files": sorted(files_changed, key=lambda f: -f["rewritten"])[:40],
        "unresolved_targets": dict(unresolved.most_common(40)),
        "unresolved_total": sum(unresolved.values()),
        "note": ("An unresolved reference is left pointing at the source. That is "
                 "deliberate: rewriting it to a local path we do not hold would "
                 "turn a visible remote request into a silent local 404 and let "
                 "the closure numbers call it resolved."),
    }
    pathlib.Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.report).write_text(json.dumps(report, indent=2) + "\n",
                                         encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "files"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
