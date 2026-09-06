"""Ask the browser which first-party assets a page really loads.

A static scan of the served markup found 145 assets on www.monoprice.com. The
browser loads far more: this site uses RequireJS and a small loader at
`/src/index.js`, and both build their URLs at run time. `/Scripts/Footer.js`
appears **nowhere** in the served HTML of any page, yet every page requests it --
it defines the `<monoprice-footer>` custom element that renders the entire
footer.

That matters more than it sounds. Without those files the clone has an undefined
custom element where the footer should be, no product gallery, no tabs and no
carousel -- and not one closure gate notices, because an undefined element makes
no request and reports no error. The page is simply missing most of itself.

There is no way to find these by reading markup. Only a browser can say what was
asked for.

    python3 tools/discover_runtime_assets.py --report scope/runtime-assets.json \
        --merge-into scope/asset-plan.json
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from browser_session import attach  # noqa: E402
from fetch_assets import asset_target  # noqa: E402

# One representative per page family. A family whose page type is not here
# contributes nothing, so the list is the coverage claim.
SAMPLES = {
    "home": "https://www.monoprice.com/",
    "about": "https://www.monoprice.com/about-us",
    "category-l3": "https://www.monoprice.com/category/cables/hdmi-cables/hdmi-cables",
    "category-hub": "https://www.monoprice.com/category/pages/1",
    "product": "https://www.monoprice.com/product?p_id=10145",
    "search": "https://www.monoprice.com/search/index?keyword=hdmi+cable",
    "shop-collection": "https://www.monoprice.com/p/shop/usb-c-to-usb-3-0",
    "resource-article": "https://www.monoprice.com/p/resources/"
                        "inside-ethernet-cables-8-wires-shielding-and-grounding",
    "newsroom": "https://www.monoprice.com/home/newsroom",
    "static-page": "https://www.monoprice.com/pages/newproducts",
    "not-found": "https://www.monoprice.com/this-route-does-not-exist-websitebench",
    "absent-product": "https://www.monoprice.com/product?p_id=99999999",
}

from fetch_assets import WEBFLOW_HOSTS  # noqa: E402

# The Webflow hosts belong here for the same reason they belong in the asset
# plan: /p/shop and /p/resources load everything from them. Leaving them out
# made those two families report *zero* runtime assets -- which read like "these
# pages need nothing" and actually meant "this tool cannot see their host". The
# Webflow app then loaded its JS chunks at run time and the clone answered 404
# for them on 48 routes.
OBSERVED_HOSTS = ({"www.monoprice.com", "monoprice.com", "images.monoprice.com"}
                  | WEBFLOW_HOSTS)
# On monoprice.com an asset lives under one of these prefixes; everything else
# on that host is an HTML route, captured elsewhere. The CDN hosts serve nothing
# but assets, so any path on them qualifies -- and restricting them to the
# first-party prefixes is what made this tool report zero for those families.
ASSET_PREFIXES = ("/assets/", "/scripts/", "/src/", "/content/", "/cf-fonts/",
                  "/commissionjunction/")


def is_asset_path(host: str, path: str) -> bool:
    if host.lower() in WEBFLOW_HOSTS:
        return True
    return path.lower().startswith(ASSET_PREFIXES)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--merge-into", default=None,
                    help="asset plan to add newly discovered entries to")
    ap.add_argument("--settle-ms", type=int, default=7000)
    args = ap.parse_args()

    by_family: dict[str, list[str]] = {}
    seen_urls: set[str] = set()

    with attach(page_index=1) as (_browser, _context, page):
        for family, url in SAMPLES.items():
            captured: list[str] = []
            handler = lambda request: captured.append(request.url)  # noqa: E731
            page.on("request", handler)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=90_000)
                page.wait_for_timeout(args.settle_ms)
            except Exception as exc:  # noqa: BLE001 - a failed sample is a result
                by_family[family] = [f"ERROR {exc.__class__.__name__}"]
                page.remove_listener("request", handler)
                continue
            page.remove_listener("request", handler)

            here: set[str] = set()
            for raw in captured:
                split = urllib.parse.urlsplit(raw)
                if split.netloc.lower() not in OBSERVED_HOSTS:
                    continue
                if not is_asset_path(split.netloc, split.path):
                    continue
                clean = urllib.parse.urlunsplit(
                    (split.scheme, split.netloc, split.path, split.query, ""))
                here.add(clean)
            by_family[family] = sorted(here)
            seen_urls |= here
            print(f"{family:18s} {len(here):4d} first-party asset requests")

    merged = {"added": 0, "already_planned": 0}
    plan_path = pathlib.Path(args.merge_into) if args.merge_into else None
    added_entries: list[dict] = []
    if plan_path and plan_path.exists():
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        index = {f"{e['host']}/{e['local']}": e for e in plan["entries"]}
        for url in sorted(seen_urls):
            target = asset_target(url)
            if target is None:
                continue
            key = f"{target[0]}/{target[1]}"
            if key in index:
                merged["already_planned"] += 1
                continue
            entry = {"url": url, "host": target[0], "local": target[1],
                     "referrers": 0, "discovered_by": "browser-runtime"}
            plan["entries"].append(entry)
            index[key] = entry
            added_entries.append(entry)
            merged["added"] += 1
        plan["assets"] = len(plan["entries"])
        plan["by_host"] = dict(collections.Counter(e["host"] for e in plan["entries"]))
        plan["runtime_discovery"] = merged
        plan_path.write_text(json.dumps(plan, indent=1) + "\n", encoding="utf-8")

    report = {
        "schema_version": "monoprice.runtime-assets.v1",
        "method": ("navigated one page per family in the shared browser and "
                   "recorded every first-party asset request"),
        "families": {k: len(v) for k, v in by_family.items()},
        "distinct_urls": len(seen_urls),
        "merged_into_plan": merged,
        "newly_discovered_examples": [e["local"] for e in added_entries][:60],
        "by_family": by_family,
    }
    pathlib.Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.report).write_text(json.dumps(report, indent=2) + "\n",
                                         encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("by_family", "newly_discovered_examples")},
                     indent=2))
    print(f"\nnewly discovered (first 25): "
          f"{[e['local'] for e in added_entries][:25]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
