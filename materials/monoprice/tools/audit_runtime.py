"""Drive the running clone in a real browser and record what actually happens.

Four things are counted, and the third is the one no other gate can see:

1. **Requests that leave this machine.** The clone must make none.
2. **Console errors**, tallied by *route* rather than by occurrence -- one
   route throwing the same error forty times is one broken route, not forty.
3. **Same-origin failures**: requests to the clone itself that answer 4xx/5xx or
   never connect. These belong to no other gate. A link-closure audit counts
   links between pages; a remote-request audit counts requests that leave. A
   subresource the clone itself answers 404 for is neither, and on the last site
   that blind spot hid a broken hero image on every product page.
4. **A content floor.** An empty page has no broken links and makes no requests,
   so every closure gate passes it. Body text, image count and page height are
   recorded so "green" cannot mean "blank".

The browser is the only witness accepted here. A static scan reports references
inside comments and `<noscript>` as live, and cannot see a URL that is assembled
at run time.

    python3 tools/audit_runtime.py --base-url http://127.0.0.1:8412 \
        --report scope/runtime-audit.json --sample 400
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import random
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from browser_session import attach  # noqa: E402

# Anything not on the clone's own origin is off this machine.
LOOPBACK = {"127.0.0.1", "localhost", "[::1]"}


def route_sample(catalogue_path: pathlib.Path, route_map_path: pathlib.Path,
                 sample: int, seed: int) -> list[tuple[str, str]]:
    """Representative routes, at least one of every family we serve."""
    catalogue = json.loads(catalogue_path.read_text(encoding="utf-8"))
    routes: list[tuple[str, str]] = [
        ("home", "/"),
        ("cart-empty", "/cart"),
        ("checkout-empty", "/checkout"),
        ("search", "/search/index?keyword=hdmi+cable"),
        ("search-empty", "/search/index?keyword=zzzqqqnope"),
        ("not-found", "/definitely-not-a-real-route-websitebench"),
        ("absent-product", "/product?p_id=99999999"),
    ]
    rng = random.Random(seed)

    taxonomy = [c["path"] for c in catalogue["categories"]
                if c.get("kind") == "taxonomy"]
    shop = [c["path"] for c in catalogue["categories"]
            if c.get("kind") == "shop-collection"]
    products = [p["url_path"] for p in catalogue["products"]]

    # Products split by whether they have a frozen page or come from the
    # template: both paths have to be exercised, and sampling blind would mostly
    # hit whichever is larger.
    frozen_urls = set()
    if route_map_path.exists():
        for url in json.loads(route_map_path.read_text(encoding="utf-8"))["routes"]:
            frozen_urls.add(urllib.parse.urlsplit(url).path.lower()
                            + "?" + urllib.parse.urlsplit(url).query)
    frozen_products = [p for p in products
                       if f"/product?{p.split('?', 1)[1]}" in frozen_urls]
    template_products = [p for p in products if p not in set(frozen_products)]

    budget = max(0, sample - len(routes))
    for label, pool, share in (("category", taxonomy, 0.30),
                               ("shop-collection", shop, 0.20),
                               ("product-frozen", frozen_products, 0.20),
                               ("product-template", template_products, 0.30)):
        if not pool:
            continue
        take = min(len(pool), max(1, int(budget * share)))
        routes.extend((label, path) for path in rng.sample(pool, take))
    return routes


PROBE = r"""() => {
  const body = document.body;
  const text = body ? body.innerText : '';
  return {
    title: document.title,
    nodes: document.querySelectorAll('*').length,
    images: document.images.length,
    imagesBroken: [...document.images].filter(
        i => i.complete && i.naturalWidth === 0).length,
    stylesheets: document.styleSheets.length,
    styleRules: (() => {
      let n = 0;
      for (const sheet of document.styleSheets) {
        try { n += sheet.cssRules ? sheet.cssRules.length : 0; } catch (e) {}
      }
      return n;
    })(),
    height: body ? body.scrollHeight : 0,
    textChars: text.length,
    links: document.querySelectorAll('a[href]').length,
    undefinedCustomElements: [...document.querySelectorAll('*')]
      .filter(e => e.tagName.includes('-') && !customElements.get(e.tagName.toLowerCase()))
      .map(e => e.tagName.toLowerCase()),
  };
}"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--sample", type=int, default=400)
    ap.add_argument("--seed", type=int, default=20260905)
    ap.add_argument("--settle-ms", type=int, default=2500)
    args = ap.parse_args()

    site_dir = pathlib.Path(__file__).resolve().parent.parent
    routes = route_sample(site_dir / "data" / "catalogue.json",
                          site_dir / "clone" / "static" / "frozen" / "route-map.json",
                          args.sample, args.seed)
    base = args.base_url.rstrip("/")
    base_host = urllib.parse.urlsplit(base).hostname

    remote: dict[str, dict] = {}
    same_origin_failures: dict[str, dict] = {}
    console_by_route: dict[str, list[str]] = {}
    thin_pages: list[dict] = []
    undefined_elements: collections.Counter = collections.Counter()
    per_route: list[dict] = []
    failed_navigations: list[dict] = []

    # A clean context, not the shared one.
    #
    # The shared browser has browsed the real monoprice.com during capture, and
    # auditing the candidate in that profile measures the browser, not the
    # candidate: the first run reported 60 remote image requests that exist
    # nowhere in the served bytes. An audit context must carry no cache, no
    # cookies and no service worker from anywhere else.
    with attach(warm=False, page_index=0) as (browser, _shared, _shared_page):
        context = browser.new_context(viewport={"width": 1440, "height": 900},
                                      locale="en-US", timezone_id="Etc/UTC",
                                      service_workers="block")
        page = context.new_page()
        page.context.clear_cookies()
        for index, (family, path) in enumerate(routes, 1):
            url = base + path
            seen_remote: list[str] = []
            seen_failed: list[tuple[str, int | str]] = []
            console: list[str] = []

            def on_request(request, bucket=seen_remote):
                host = urllib.parse.urlsplit(request.url).hostname
                if host and host not in LOOPBACK and host != base_host:
                    bucket.append(request.url)

            def on_response(response, bucket=seen_failed):
                split = urllib.parse.urlsplit(response.url)
                if split.hostname in LOOPBACK or split.hostname == base_host:
                    if response.status >= 400:
                        bucket.append((split.path, response.status))

            def on_failed(request, bucket=seen_failed):
                split = urllib.parse.urlsplit(request.url)
                if split.hostname in LOOPBACK or split.hostname == base_host:
                    failure = (request.failure or "")
                    # An aborted request is the page navigating away, not a
                    # defect. Counting it would bury the real failures.
                    if "ERR_ABORTED" not in failure:
                        bucket.append((split.path, failure or "failed"))

            def on_console(message, bucket=console):
                if message.type == "error":
                    bucket.append(message.text[:200])

            page.on("request", on_request)
            page.on("response", on_response)
            page.on("requestfailed", on_failed)
            page.on("console", on_console)
            try:
                response = page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(args.settle_ms)
                observed = page.evaluate(PROBE)
                status = response.status if response else None
            except Exception as exc:  # noqa: BLE001
                failed_navigations.append({"path": path,
                                           "error": f"{exc.__class__.__name__}: {exc}"[:180]})
                observed, status = {}, None
            finally:
                page.remove_listener("request", on_request)
                page.remove_listener("response", on_response)
                page.remove_listener("requestfailed", on_failed)
                page.remove_listener("console", on_console)

            for remote_url in seen_remote:
                entry = remote.setdefault(remote_url, {"url": remote_url, "routes": []})
                if path not in entry["routes"]:
                    entry["routes"].append(path)
            for failed_path, why in seen_failed:
                key = f"{failed_path} :: {why}"
                entry = same_origin_failures.setdefault(
                    key, {"path": failed_path, "reason": why, "routes": []})
                if path not in entry["routes"]:
                    entry["routes"].append(path)
            if console:
                console_by_route[path] = sorted(set(console))
            for tag in observed.get("undefinedCustomElements", []):
                undefined_elements[tag] += 1

            record = {"family": family, "path": path, "status": status,
                      **{k: v for k, v in observed.items()
                         if k != "undefinedCustomElements"}}
            per_route.append(record)

            # An empty page passes every closure gate ever written.
            if observed and (observed.get("textChars", 0) < 500
                             or observed.get("height", 0) < 400
                             or observed.get("styleRules", 0) < 50):
                thin_pages.append(record)

            if index % 25 == 0:
                print(f"  {index}/{len(routes)} routes  remote={len(remote)} "
                      f"same-origin-fail={len(same_origin_failures)}")

        context.close()

    # Console errors counted by route, not by occurrence.
    console_tally: collections.Counter = collections.Counter()
    for messages in console_by_route.values():
        for message in set(messages):
            console_tally[message[:120]] += 1

    report = {
        "schema_version": "monoprice.runtime-audit.v2",
        "base_url": base,
        "routes_driven": len(routes),
        "routes_by_family": dict(collections.Counter(f for f, _ in routes)),
        "failed_navigations": failed_navigations,
        "remote_requests": {
            "distinct_urls": len(remote),
            "entries": sorted(remote.values(), key=lambda e: -len(e["routes"]))[:60],
        },
        "same_origin_failures": {
            "distinct": len(same_origin_failures),
            "routes_affected": len({r for e in same_origin_failures.values()
                                    for r in e["routes"]}),
            "entries": sorted(same_origin_failures.values(),
                              key=lambda e: -len(e["routes"]))[:80],
        },
        "console_errors": {
            "routes_with_errors": len(console_by_route),
            "by_message_route_count": console_tally.most_common(30),
        },
        "undefined_custom_elements": dict(undefined_elements.most_common(20)),
        "content_floor": {
            "thin_pages": len(thin_pages),
            "examples": thin_pages[:20],
            "rule": ("under 500 characters of body text, or under 400px tall, or "
                     "fewer than 50 CSS rules in force"),
        },
        "totals": {
            "min_text_chars": min((r.get("textChars", 0) for r in per_route
                                   if r.get("textChars") is not None), default=0),
            "min_style_rules": min((r.get("styleRules", 0) for r in per_route
                                    if r.get("styleRules") is not None), default=0),
            "broken_images": sum(r.get("imagesBroken", 0) for r in per_route),
        },
    }
    out = pathlib.Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("remote_requests", "same_origin_failures")},
                     indent=2)[:2200])
    print(f"\nremote requests: {len(remote)} distinct")
    print(f"same-origin failures: {len(same_origin_failures)} distinct across "
          f"{report['same_origin_failures']['routes_affected']} routes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
