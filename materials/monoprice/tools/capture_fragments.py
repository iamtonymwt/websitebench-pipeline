"""Capture the HTML fragments the site injects into hidden containers.

Six first-party endpoints fill visible content *after* page load, and the whole
run missed all six. `mp_productPage_more.js` and `mp_homepage.js` share one
filler:

    $(item.outerContainerSelector).hide();          // hide FIRST
    $.ajax({url: item.url + "?p_id=" + p_id + "&cust_review=" + r,
             success: function (data) {
                 $(item.innerContainerSelector).html(data);   // then fill
                 ...
             }});

The container is hidden before the request and only revealed on success, so a
request that fails leaves it hidden forever. On the clone the three `/home/*`
endpoints answered 404 and the three `/product/*` ones were swallowed by the
catch-all, which returned the entire 407 KB product page to be injected into a
carousel. Visible consequence: the source product page shows 35 product tiles
and the clone showed 1; the source home page renders 9,264 characters and the
clone 3,678.

This is the same failure family as the HawkSearch result containers and the
stripped `dataLayer`/`_satellite`/`F9` globals: **first-party content that is
present-but-unreachable because the thing that reveals it never ran.** It is
worth stating once more that no gate in this run could see any of it -- the
requests are same-origin, so the remote-request audit is blind; they answer 200
or 404 without the page erroring, so the console listener is blind; and the
markup is "closed" because the fragment was never referenced statically.

Fetching is done with in-page `fetch()` from the already-warm browser context,
which is how everything else on this site is captured: the endpoints sit behind
the same Cloudflare challenge as the HTML. It reuses the existing page and never
opens a page or a context -- see the note in `tools/README.md` about page churn.

These are GETs of endpoints the page itself calls on load. Nothing here submits
a form, changes a cart, or touches an account.

    python3 tools/capture_fragments.py probe                 # a few, then look
    python3 tools/capture_fragments.py run --catalogue data/catalogue.json
"""

from __future__ import annotations

import argparse
import datetime
import gzip
import json
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from browser_session import attach  # noqa: E402

BASE = "https://www.monoprice.com"

# The endpoints that fill a container with markup, and the container each one
# fills. Taken from the two `contentFills` tables in the served scripts rather
# than guessed.
HOME_ENDPOINTS = [
    ("/home/getRecentlyViewed", ".home-layer7"),
    ("/home/getRecommendationsForYou", ".home-layer3"),
    ("/home/getTopSellers", None),
]
PRODUCT_ENDPOINTS = [
    ("/product/GetCustomersAlsoShoppedFor", "#AlsoBought"),
    ("/product/getrecommendationsforyou", "#RecommandationsForYou"),
    ("/product/getrecentlyviewed", "#RecentlyViewed"),
]

# `probe` measured which of these actually vary by product, and only one does.
# Fetching all three per product would have meant 11,577 requests to the source
# to obtain 3,859 distinct answers and two constants.
#
#   GetCustomersAlsoShoppedFor   3 distinct bodies across 3 products
#   getrecommendationsforyou     1 distinct body  (14,900 bytes, 12 tiles)
#   getrecentlyviewed            empty -- it reflects a session's own history
PRODUCT_PER_ITEM = ["/product/GetCustomersAlsoShoppedFor", "/Product/GetTab3"]
PRODUCT_ONCE = ["/product/getrecommendationsforyou", "/product/getrecentlyviewed",
                "/Product/GetTab1", "/Product/GetTab5"]

# The product page's tab panels are content fills too, and they were missed by
# the first inventory because `mp_productPage_more.js` builds their URL under the
# key `tabUrl:` rather than `url:` -- so a grep for `url:` found fifteen
# endpoints and not these. A search narrower than the thing it is searching for
# is the recurring bug of this whole run.
#
#   GetTab1   351 bytes, identical for every product      -> capture once
#   GetTab2   404 on the source; the loop skips index 2
#   GetTab3   2,370-19,986 bytes, product-specific        -> capture per product
#   GetTab4   404 on the source; the loop skips index 4
#   GetTab5   4,984 bytes, identical for every product    -> capture once
#
# Tab 3 is where the specifications and long description live, which is most of
# a product page's text. Without it the clone rendered 920 characters against
# the source's 7,134.
TAB_CONTAINERS = {"/Product/GetTab1": "#tab1", "/Product/GetTab3": "#tab3",
                  "/Product/GetTab5": "#tab5"}

# In-page fetch. Same-origin, so the clearance cookie rides along; `text()`
# because these return HTML fragments, not JSON.
FETCH = """async (url) => {
  try {
    const r = await fetch(url, {credentials: 'include',
                               headers: {'X-Requested-With': 'XMLHttpRequest'}});
    return {status: r.status, ct: r.headers.get('content-type') || '', body: await r.text()};
  } catch (e) { return {status: 0, ct: '', body: '', error: String(e).slice(0, 200)}; }
}"""

CHALLENGE = re.compile(r"just a moment|challenge-platform|cf-browser-verification", re.I)


def out_root() -> pathlib.Path:
    stamp = datetime.date.today().isoformat()
    return pathlib.Path("source-current") / f"{stamp}.fragments"


def store(path: pathlib.Path, body: str) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wb") as fh:
        fh.write(body.encode("utf-8"))
    return path.stat().st_size


def tiles(body: str) -> int:
    return len(re.findall(r"p_id=\d+", body))


def fetch_one(page, url: str) -> dict:
    got = page.evaluate(FETCH, url)
    body = got.get("body", "")
    # A challenge answered 200 is still a challenge. Saving one under the name
    # of a content fragment is how the asset fetcher nearly lost the site's
    # visual layer earlier in this run.
    got["challenge"] = bool(CHALLENGE.search(body[:4000])) and tiles(body) == 0
    got["tiles"] = tiles(body)
    got["bytes"] = len(body)
    return got


def probe(page) -> int:
    print("A fragment that is HTML with product links is what we want.\n")
    rows = []
    for path, container in HOME_ENDPOINTS:
        got = fetch_one(page, BASE + path)
        rows.append((path, got))
        print(f"  {path:42s} status={got['status']} bytes={got['bytes']:>7} "
              f"tiles={got['tiles']:>3} challenge={got['challenge']} -> {container}")
    for pid in ("39165", "2684", "4777"):
        for path, container in PRODUCT_ENDPOINTS:
            url = f"{BASE}{path}?p_id={pid}&cust_review="
            got = fetch_one(page, url)
            rows.append((f"{path}?p_id={pid}", got))
            print(f"  {path:32s} p_id={pid:<6} status={got['status']} "
                  f"bytes={got['bytes']:>7} tiles={got['tiles']:>3} "
                  f"challenge={got['challenge']}")
            time.sleep(0.25)
    # Are the product fragments actually product-specific? If two products
    # return identical bytes, one captured copy serves everybody and there is
    # no reason to fetch 3,859 of them.
    print()
    for path, _ in PRODUCT_ENDPOINTS:
        bodies = {}
        for pid in ("39165", "2684", "4777"):
            got = fetch_one(page, f"{BASE}{path}?p_id={pid}&cust_review=")
            bodies[pid] = got["body"]
        distinct = len(set(bodies.values()))
        print(f"  {path:42s} distinct bodies across 3 products: {distinct}/3"
              f"  {'-> product-specific' if distinct > 1 else '-> identical, capture once'}")
    return 0


def run(page, catalogue: pathlib.Path, limit: int | None, report: pathlib.Path,
        fresh: bool = False) -> int:
    # Resume, because this makes 3,859 requests to a live site and the run was
    # interrupted once at 2,946 with no way to pick it up. Re-fetching what is
    # already on disk is not a neutral cost here: every one of those is a real
    # request to the source.
    #
    # The root comes from the previous report rather than from today's date, so
    # a run that spans midnight continues into the directory it started in
    # instead of silently beginning a second, half-empty capture.
    tally = {"home": 0, "product": 0, "challenge": 0, "empty": 0, "failed": 0,
             "resumed": 0}
    index: dict[str, dict] = {}
    root = out_root()
    if not fresh and report.exists():
        previous = json.loads(report.read_text(encoding="utf-8"))
        root = pathlib.Path(previous.get("root") or root)
        index = dict(previous.get("fragments") or {})
        tally["resumed"] = len(index)
        print(f"resuming into {root}: {len(index)} fragments already captured")

    for path, container in HOME_ENDPOINTS:
        got = fetch_one(page, BASE + path)
        if got["challenge"]:
            tally["challenge"] += 1
            print(f"  CHALLENGE on {path} -- stopping, the clearance is gone")
            return 1
        if got["status"] != 200:
            tally["failed"] += 1
            print(f"  {path} answered {got['status']}")
            continue
        name = path.strip("/").replace("/", "_") + ".html.gz"
        store(root / "home" / name, got["body"])
        index[path] = {"file": f"home/{name}", "bytes": got["bytes"],
                       "tiles": got["tiles"], "container": container}
        tally["home"] += 1
        if not got["body"].strip():
            tally["empty"] += 1
        print(f"  home {path:38s} {got['bytes']:>7} bytes  {got['tiles']:>3} tiles")

    # The two constants, fetched once against one product.
    containers = dict(PRODUCT_ENDPOINTS)
    containers.update(TAB_CONTAINERS)
    for path in PRODUCT_ONCE:
        got = fetch_one(page, f"{BASE}{path}?p_id=39165&cust_review=")
        if got["status"] != 200:
            tally["failed"] += 1
            print(f"  {path} answered {got['status']}")
            continue
        name = path.strip("/").replace("/", "_") + ".html.gz"
        store(root / "shared" / name, got["body"])
        index[path] = {"file": f"shared/{name}", "bytes": got["bytes"],
                       "tiles": got["tiles"], "container": containers.get(path),
                       "scope": "same for every product"}
        print(f"  shared {path:36s} {got['bytes']:>7} bytes  {got['tiles']:>3} tiles")

    products = json.loads(catalogue.read_text(encoding="utf-8"))["products"]
    pids = [p["p_id"] for p in products]
    if limit:
        pids = pids[:limit]
    print(f"\n{len(pids)} products x {len(PRODUCT_PER_ITEM)} per-product endpoint")

    for n, pid in enumerate(pids, 1):
        for path in PRODUCT_PER_ITEM:
            container = containers.get(path)
            key = f"{path}?p_id={pid}"
            if key in index:
                continue
            got = fetch_one(page, f"{BASE}{path}?p_id={pid}&cust_review=")
            if got["challenge"]:
                tally["challenge"] += 1
                print(f"  CHALLENGE at product {n} -- stopping and keeping "
                      f"what is already on disk")
                _write(report, root, index, tally, stopped_early=True)
                return 1
            if got["status"] != 200:
                tally["failed"] += 1
                continue
            slug = path.strip("/").replace("/", "_")
            name = f"{slug}/{pid}.html.gz"
            store(root / "product" / name, got["body"])
            index[f"{path}?p_id={pid}"] = {
                "file": f"product/{name}", "bytes": got["bytes"],
                "tiles": got["tiles"], "container": container, "p_id": pid}
            tally["product"] += 1
            if not got["body"].strip():
                tally["empty"] += 1
        if n % 100 == 0:
            print(f"  {n}/{len(pids)} products  ({len(index)} fragments held, "
                  f"{tally['product']} new this run, {tally['empty']} empty, "
                  f"{tally['failed']} non-200)")
            _write(report, root, index, tally, stopped_early=False)

    _write(report, root, index, tally, stopped_early=False)
    print(f"\n{json.dumps(tally, indent=2)}")
    return 0


def _write(report: pathlib.Path, root: pathlib.Path, index: dict,
           tally: dict, stopped_early: bool) -> None:
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({
        "schema_version": "monoprice.fragments.v1",
        "root": str(root),
        "tally": tally,
        "stopped_early": stopped_early,
        "fragments": index,
    }, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe")
    r = sub.add_parser("run")
    r.add_argument("--catalogue", default="data/catalogue.json")
    r.add_argument("--limit", type=int)
    r.add_argument("--report", default="scope/fragments.json")
    r.add_argument("--fresh", action="store_true",
                   help="ignore what is already captured and start over")
    args = ap.parse_args()

    # Reuse the warm page. No new_page, no new_context: this tool exists partly
    # because the previous approach opened and closed a page per question.
    with attach(warm=True, page_index=0) as (_browser, _ctx, page):
        if args.cmd == "probe":
            return probe(page)
        return run(page, pathlib.Path(args.catalogue), args.limit,
                   pathlib.Path(args.report), fresh=args.fresh)


if __name__ == "__main__":
    raise SystemExit(main())
