"""Plan the assets that other assets reference.

A stylesheet asks for fonts and background images with paths relative to itself,
and those never appear in any page's markup. The asset plan is built from pages,
so it cannot contain them: the runtime audit found font-awesome's `.woff2`,
`.woff` and `.ttf` answering 404 on every route that uses the icon font, and 39
absolute image references inside stylesheets pointing at files nobody fetched.

This walks the assets already on disk, resolves every reference they make, and
adds the ones that are missing to the plan. It is a *second* closure pass and it
has to be repeated until it finds nothing, because a newly fetched stylesheet can
reference something of its own.

    python3 tools/plan_asset_subresources.py --assets-dir source-assets \
        --plan scope/asset-plan.json --report scope/asset-subresources.json
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
from fetch_assets import CHALLENGED_HOSTS, OPEN_HOSTS, asset_target  # noqa: E402

CSS_URL = re.compile(r"""url\(\s*(['"]?)([^)'"]+)\1\s*\)""", re.I)
CSS_IMPORT = re.compile(r"""@import\s+(?:url\()?\s*(['"])([^'"]+)\1""", re.I)
ABSOLUTE_IN_TEXT = re.compile(
    r"""(?:https?:)?//(?:[A-Za-z0-9.-]+)/[^\s"'()\\]+""")

SCANNABLE = {".css", ".js"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets-dir", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    assets_dir = pathlib.Path(args.assets_dir)
    plan_path = pathlib.Path(args.plan)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    have = {f"{e['host']}/{e['local']}" for e in plan["entries"]}

    added: list[dict] = []
    skipped_offsite: collections.Counter = collections.Counter()
    scanned = 0

    for path in sorted(assets_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SCANNABLE:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        relative = path.relative_to(assets_dir)
        host = relative.parts[0]
        # The URL this file was served from, so relative references resolve the
        # way the browser will resolve them.
        base = f"https://{host}/" + "/".join(relative.parts[1:])

        references: set[str] = set()
        for match in CSS_URL.finditer(text):
            references.add(match.group(2))
        for match in CSS_IMPORT.finditer(text):
            references.add(match.group(2))
        for match in ABSOLUTE_IN_TEXT.finditer(text):
            references.add(match.group(0))

        for raw in references:
            raw = raw.strip()
            if not raw or raw.startswith(("data:", "#", "about:")):
                continue
            absolute = urllib.parse.urljoin(base, raw)
            split = urllib.parse.urlsplit(absolute)
            if split.hostname and split.hostname.lower() not in (
                    OPEN_HOSTS | CHALLENGED_HOSTS):
                skipped_offsite[split.hostname.lower()] += 1
                continue
            target = asset_target(absolute)
            if target is None:
                continue
            key = f"{target[0]}/{target[1]}"
            if key in have or (assets_dir / target[0] / target[1]).is_file():
                continue
            have.add(key)
            entry = {"url": absolute, "host": target[0], "local": target[1],
                     "referrers": 1, "discovered_by": f"subresource-of:{relative}"}
            plan["entries"].append(entry)
            added.append(entry)

    plan["assets"] = len(plan["entries"])
    plan["by_host"] = dict(collections.Counter(e["host"] for e in plan["entries"]))
    plan_path.write_text(json.dumps(plan, indent=1) + "\n", encoding="utf-8")

    report = {
        "schema_version": "monoprice.asset-subresources.v1",
        "files_scanned": scanned,
        "added_to_plan": len(added),
        "added_by_extension": dict(collections.Counter(
            pathlib.PurePosixPath(e["local"]).suffix.lower() for e in added)),
        "examples": [e["local"] for e in added][:40],
        "offsite_references_not_planned": dict(skipped_offsite.most_common(20)),
        "note": ("Run again after fetching: a stylesheet that was just fetched "
                 "can reference subresources of its own, so one pass does not "
                 "close it."),
    }
    pathlib.Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.report).write_text(json.dumps(report, indent=2) + "\n",
                                         encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "examples"}, indent=2))
    print("examples:", report["examples"][:12])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
