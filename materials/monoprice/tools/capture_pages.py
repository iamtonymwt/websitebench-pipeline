"""Capture monoprice pages through the one long-lived browser.

Why this shape, since it is unusual:

www.monoprice.com answers plain HTTP clients with a Cloudflare challenge for
HTML *and* for /assets/, so every byte has to come through a browser. But the
site is server-rendered -- the product page's raw HTML already carries the title,
the price and the Add to Cart form -- so the browser does not have to *navigate*
to each page. It fetches them from inside an already-cleared context, which runs
at 2.4 pages/second instead of one navigation every few seconds.

That choice also avoids a trap the last two sites in this family paid for: a
settled post-hydration DOM contains elements the source never parsed as markup,
and freezing it re-executes them. Raw served HTML has no such problem. Pages that
genuinely need a rendered snapshot (to recover what a script assembles) are
captured separately with --mode render, and they are the exception.

Queue semantics, learned the hard way elsewhere:

* A page that answered is `done` with its **upstream status** recorded. A 404
  from the source and a 200 from the source are both `done`, and the difference
  is in the record, not in the label.
* Losing the network is a fact about *this machine*, not about a path. On
  repeated connection failures the run **stops and leaves the rest pending**
  rather than marking hundreds of paths `error` and quietly shrinking the
  frontier of every later run.
* Absent pages are classified by content. This site answers unknown products and
  unknown category paths with HTTP 200 and a full-looking body, so status code is
  not a usable filter.

    python3 tools/capture_pages.py frontier --sitemap <file> --out queue.json
    python3 tools/capture_pages.py run --queue queue.json --limit 500
    python3 tools/capture_pages.py status --queue queue.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import pathlib
import re
import sys
import time
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from browser_session import attach  # noqa: E402

ORIGIN = "https://www.monoprice.com"
SITE_ROOT = pathlib.Path(__file__).resolve().parent.parent

# From the source's own robots.txt, read 2026-09-04. Case-insensitive because the
# site serves both /cart and /Cart and both /myaccount and /MyAccount, and the
# rules name several of these spellings explicitly.
ROBOTS_DISALLOW = (
    "/myaccount", "/sslchkout", "/checkout", "/staticcontent", "/cart",
    "/productshareonblog", "/eform=e", "/productsavedlist", "/chat",
    "/productsavedlistupdate", "/twitter.com/",
)

# Tracking parameters the site hangs off product links. They change nothing about
# what is served, so a frontier that keeps them would capture the same product
# dozens of times under different names.
DROP_PARAMS = {
    "page", "page_type", "location_type", "start_date", "promo_type", "popup",
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "msclkid", "fbclid", "cjevent", "s_keyword",
}

SOFT_404_PRODUCT_TITLE = "products no longer available"
TRUE_404_TITLE = "httperror404"

# Every listing on this site can be refined by facet, sorted and paged, and each
# combination is its own URL. Harvesting them all does not converge: 120 captured
# pages had already produced 2,340 new URLs, 1,600 of them single-facet variants
# of categories we had just captured, and the next round would have multiplied
# them again.
#
# Dropping the parameters outright would be the other error -- it would erase the
# evidence that filtering, sorting and pagination exist at all, and those are
# controls the clone has to reproduce. So variants are kept, but *capped per base
# path*: enough to see what a filtered, sorted and second-page listing looks
# like, not one per combination. The cap is recorded in the queue, so what was
# left out is visible rather than silently missing.
VARIANT_CAP_PER_PATH = 3
VARIANT_PARAM_HINTS = ("_ufilter", "pgnum", "rows", "sort", "totalproducts",
                       "menudisstr", "cust_review")

# The per-listing cap was the wrong axis and the queue said so: it consumed 40
# pages per batch and added 86, because every one of the ~2,600 listings was
# allowed its own 3 variants. That ceiling is ~7,800 filtered listings, and the
# frontier grew faster than capture drained it.
#
# What the clone actually needs from a facet is the URL grammar and the shape of
# a filtered result -- not one example per department. So variants are capped
# globally *per facet type*: a dozen brand-filtered listings, a dozen colour
# filtered ones, a dozen second pages. That is ~150 pages instead of 7,800, it
# converges, and it covers strictly more facet *kinds* than the per-listing cap
# did, because that one spent its whole budget on whichever facets happened to
# appear on each page.
GLOBAL_VARIANT_CAPS: dict[str, int] = {
    "cust_review": 10,      # a tab already present on the product body
    "pgnum": 15,            # pagination
    "rows": 8,              # page size
    "sort": 8,
    "categorypath3_ufilter": 12,
    "freeshipping_ufilter": 8,
}
# Any other *_uFilter facet gets this budget, keyed by its own name, so a facet
# nobody anticipated still gets sampled instead of silently flooding or vanishing.
DEFAULT_FACET_CAP = 10


# --------------------------------------------------------------------------- #
# What gets kept
# --------------------------------------------------------------------------- #
# A page of this site is 440-650 KB of HTML, and the frontier is over 11,000
# pages. Keeping every body verbatim would be ~5.6 GB of evidence, which is not
# a reasonable thing to commit, and most of it would never be read: the clone
# freezes one page per family and serves the 5,500 products from a catalogue and
# a detail template.
#
# So bodies are stored gzipped, and product pages past a sample keep a
# structured extract instead of a body. The sample is not decoration -- the
# detail template is cut from a real captured product page, and the extras are
# what proves the template generalises.
#
# The rule that matters: an extract is only ever taken from a body we actually
# received. Nothing here reconstructs a page it did not fetch.

def body_path(page_dir: pathlib.Path) -> pathlib.Path:
    return page_dir / "dom.html.gz"


def write_body(page_dir: pathlib.Path, html: str) -> int:
    raw = html.encode("utf-8", "replace")
    path = body_path(page_dir)
    with gzip.open(path, "wb", compresslevel=6) as fh:
        fh.write(raw)
    return path.stat().st_size


def read_body(page_dir: pathlib.Path) -> str | None:
    """Read a captured body, whichever form it was stored in."""
    gz = page_dir / "dom.html.gz"
    if gz.exists():
        with gzip.open(gz, "rb") as fh:
            return fh.read().decode("utf-8", "replace")
    plain = page_dir / "dom.html"
    if plain.exists():
        return plain.read_text(encoding="utf-8", errors="replace")
    return None


_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S)


def extract_product(html: str) -> dict | None:
    """Pull the structured record a product page publishes about itself.

    Read from the page's own schema.org blocks rather than from scraped markup.
    That is a deliberate choice: field names invented by the reader are how the
    last site produced a 531-row table of documents that all pointed nowhere.
    """
    blocks = []
    for m in _LD_RE.finditer(html):
        try:
            blocks.append(json.loads(m.group(1).strip()))
        except (json.JSONDecodeError, ValueError):
            continue
    product = next((b for b in blocks if isinstance(b, dict)
                    and b.get("@type") == "Product"), None)
    if product is None:
        return None
    crumbs = next((b for b in blocks if isinstance(b, dict)
                   and b.get("@type") == "BreadcrumbList"), None)
    trail = []
    if crumbs:
        for item in crumbs.get("itemListElement") or []:
            node = item.get("item") or {}
            if node.get("name"):
                trail.append({"name": node["name"], "url": node.get("@id")})
    return {"product": product, "breadcrumbs": trail,
            "jsonld_types": [b.get("@type") for b in blocks if isinstance(b, dict)]}


# --------------------------------------------------------------------------- #
# URL handling
# --------------------------------------------------------------------------- #

def disallowed(path: str) -> bool:
    p = path.lower()
    return any(p == d or p.startswith(d.rstrip("/") + "/") or p.startswith(d)
               for d in ROBOTS_DISALLOW)


def canonical(url: str) -> str | None:
    """Normalise to the one URL this page should be captured under, or None."""
    try:
        u = urllib.parse.urlsplit(url)
    except ValueError:
        return None
    if u.scheme not in ("http", "https", ""):
        return None
    host = (u.netloc or "www.monoprice.com").lower()
    if host in ("monoprice.com", ""):
        host = "www.monoprice.com"
    if host != "www.monoprice.com":
        return None
    path = u.path or "/"
    # The site serves /Product and /product, /Category and /category. They are
    # the same page; capturing both would double the frontier and produce two
    # ids for one entity.
    lowered = path.lower()
    if lowered.startswith(("/product", "/category", "/myaccount", "/cart",
                           "/search", "/pages", "/home", "/p/")):
        path = lowered
    if disallowed(path):
        return None
    keep = [(k, v) for k, v in urllib.parse.parse_qsl(u.query, keep_blank_values=False)
            if k.lower() not in DROP_PARAMS]
    keep.sort()
    query = urllib.parse.urlencode(keep)
    return urllib.parse.urlunsplit(("https", "www.monoprice.com", path, query, ""))


def is_variant(url: str) -> bool:
    """A refinement of a listing (facet, sort, page) rather than a page of its own."""
    q = urllib.parse.urlsplit(url).query
    if not q:
        return False
    keys = {k.lower() for k, _ in urllib.parse.parse_qsl(q)}
    # p_id and keyword identify an entity; everything else refines a listing.
    if keys <= {"p_id", "keyword"}:
        return False
    return any(any(h in k for h in VARIANT_PARAM_HINTS) for k in keys)


def base_path_of(url: str) -> str:
    u = urllib.parse.urlsplit(url)
    pid = dict(urllib.parse.parse_qsl(u.query)).get("p_id")
    return f"{u.path}?p_id={pid}" if pid else u.path


def global_cap_key(url: str) -> str | None:
    """Which facet-type budget this variant draws from, if any."""
    keys = {k.lower() for k, _ in
            urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query)}
    for name in GLOBAL_VARIANT_CAPS:
        if name in keys:
            return name
    for k in sorted(keys):
        if k.endswith("_ufilter"):
            return k
    return None


def cap_for(key: str) -> int:
    return GLOBAL_VARIANT_CAPS.get(key, DEFAULT_FACET_CAP)


def slug_for(url: str) -> str:
    """A filesystem name that stays readable and never collides."""
    u = urllib.parse.urlsplit(url)
    base = (u.path.strip("/") or "index")
    if u.query:
        base = f"{base}__{u.query}"
    base = re.sub(r"[^A-Za-z0-9._=-]+", "-", base).strip("-")[:120] or "index"
    digest = hashlib.sha256(url.encode()).hexdigest()[:10]
    return f"{base}.{digest}"


def classify(url: str, status: int, html: str) -> str:
    """What this response actually is. Status code alone cannot tell us."""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    title = re.sub(r"\s+", " ", (m.group(1) if m else "")).strip().lower()
    if "just a moment" in title:
        return "challenge"
    if TRUE_404_TITLE in title.replace(" ", ""):
        return "not-found"
    if SOFT_404_PRODUCT_TITLE in title:
        return "absent-product"
    path = urllib.parse.urlsplit(url).path
    if path.startswith(("/category/", "/p/cat")):
        # A listing with no products at all. Note what this is NOT: it is not
        # evidence that the path is absent. The source renders an invented path
        # (/category/nope/nope/nope) and a real-but-empty department
        # (/category/audio-video/speakers/bluetooth-speakers, which is in its own
        # sitemap) with the identical body -- HawkSearch's "We were unable to
        # find search results for ..." page, 516KB, title built from the slug.
        # The source draws no distinction, so neither can we, and calling these
        # "absent" would throw away the site's own empty-listing state, which is
        # exactly the kind of state the clone needs to reproduce.
        if not re.search(r"p_id=\d+", html):
            return "empty-listing"
    if status >= 500:
        return "server-error"
    if status == 404:
        return "not-found"
    if status != 200:
        return f"status-{status}"
    return "content"


# --------------------------------------------------------------------------- #
# Frontier
# --------------------------------------------------------------------------- #

def build_frontier(sitemap_path: pathlib.Path, extra: list[str]) -> dict:
    raw = sitemap_path.read_text(encoding="utf-8", errors="replace")
    locs = re.findall(r"<loc>([^<]+)</loc>", raw)
    urls: dict[str, str] = {}
    skipped_disallowed = 0
    skipped_offsite = 0
    for loc in locs:
        loc = loc.replace("&amp;", "&")
        c = canonical(loc)
        if c is None:
            if disallowed(urllib.parse.urlsplit(loc).path or "/"):
                skipped_disallowed += 1
            else:
                skipped_offsite += 1
            continue
        urls[c] = "sitemap"
    for u in extra:
        c = canonical(u)
        if c:
            urls.setdefault(c, "seed")
    return {
        "schema_version": "monoprice.capture-queue.v1",
        "origin": ORIGIN,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "sitemap_locs": len(locs),
        "skipped_robots_disallowed": skipped_disallowed,
        "skipped_offsite_or_unparsable": skipped_offsite,
        "entries": {u: {"state": "pending", "discovered_by": src} for u, src in sorted(urls.items())},
    }


# --------------------------------------------------------------------------- #
# Capture
# --------------------------------------------------------------------------- #

BULK = r"""async ({urls, conc}) => {
  const out = [];
  let i = 0;
  async function worker() {
    while (i < urls.length) {
      const url = urls[i++];
      const t0 = performance.now();
      try {
        const r = await fetch(url, {cache: 'no-store', redirect: 'follow'});
        const body = await r.text();
        out.push({url, status: r.status, finalUrl: r.url, body,
                  ms: Math.round(performance.now() - t0)});
      } catch (e) {
        out.push({url, error: String(e).slice(0, 200),
                  ms: Math.round(performance.now() - t0)});
      }
    }
  }
  await Promise.all(Array.from({length: conc}, worker));
  return out;
}"""


def run_capture(queue_path: pathlib.Path, out_root: pathlib.Path, limit: int,
                concurrency: int, batch: int, harvest: bool,
                full_product_sample: int) -> int:
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    entries: dict[str, dict] = queue["entries"]
    pending = [u for u, e in entries.items() if e["state"] == "pending"]
    if limit:
        pending = pending[:limit]
    if not pending:
        print("nothing pending")
        return 0

    out_root.mkdir(parents=True, exist_ok=True)
    done = failed = challenged = 0
    consecutive_network_failures = 0
    extract_failures: list[str] = []
    variants_capped: dict[str, int] = {}
    global_counts: dict[str, int] = {}
    for u, e in entries.items():
        if e.get("discovered_by") == "harvest-variant":
            gkey = global_cap_key(u) or "(unclassified-variant)"
            global_counts[gkey] = global_counts.get(gkey, 0) + 1
    # Resume-safe: count the product bodies already on disk rather than starting
    # the sample over on every invocation.
    product_bodies_kept = sum(
        1 for u, e in entries.items()
        if e.get("state") == "done" and e.get("body_retained")
        and e.get("classification") == "content"
        and urllib.parse.urlsplit(u).path.startswith("/product"))
    started = time.time()

    def save() -> None:
        queue_path.write_text(json.dumps(queue, indent=1) + "\n", encoding="utf-8")

    with attach() as (_browser, _context, page):
        for start in range(0, len(pending), batch):
            chunk = pending[start:start + batch]
            try:
                rows = page.evaluate(BULK, {"urls": chunk, "conc": concurrency})
            except Exception as exc:  # noqa: BLE001
                print(f"batch failed to run: {exc.__class__.__name__}: {exc}")
                print("leaving the rest pending; this is about this machine, "
                      "not about these paths")
                save()
                return 2

            batch_network_failures = 0
            for row in rows:
                url = row["url"]
                entry = entries[url]
                if "error" in row:
                    batch_network_failures += 1
                    entry["last_error"] = row["error"]
                    # deliberately left `pending`
                    continue
                html = row["body"]
                kind = classify(url, row["status"], html)
                if kind == "challenge":
                    challenged += 1
                    entry["last_error"] = "cloudflare challenge"
                    continue
                slug = slug_for(url)
                page_dir = out_root / slug
                page_dir.mkdir(parents=True, exist_ok=True)

                is_product = urllib.parse.urlsplit(url).path.startswith("/product")
                keep_body = (not is_product) or kind != "content" or \
                    (product_bodies_kept < full_product_sample)

                meta = {
                    "url": url,
                    "final_url": row.get("finalUrl"),
                    "upstream_status": row["status"],
                    "classification": kind,
                    "bytes": len(html),
                    "sha256": hashlib.sha256(html.encode("utf-8", "replace")).hexdigest(),
                    "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                    "fetch_ms": row["ms"],
                    "mode": "raw-served-html",
                    "body_retained": keep_body,
                }
                if keep_body:
                    meta["stored_bytes"] = write_body(page_dir, html)
                    if is_product and kind == "content":
                        product_bodies_kept += 1
                if is_product and kind == "content":
                    record = extract_product(html)
                    if record is None:
                        # A product page that publishes no schema.org Product is
                        # not a silent skip: without a body we would have kept
                        # nothing at all about it.
                        meta["extract_error"] = "no schema.org Product block"
                        if not keep_body:
                            meta["stored_bytes"] = write_body(page_dir, html)
                            meta["body_retained"] = True
                        extract_failures.append(url)
                    else:
                        (page_dir / "extract.json").write_text(
                            json.dumps(record, indent=2) + "\n", encoding="utf-8")
                        meta["extract"] = "schema.org Product + BreadcrumbList"

                (page_dir / "fetch.json").write_text(json.dumps(meta, indent=2) + "\n",
                                                     encoding="utf-8")
                entry.update({"state": "done", "classification": kind,
                              "upstream_status": row["status"], "slug": slug,
                              "bytes": len(html), "body_retained": meta["body_retained"]})
                entry.pop("last_error", None)
                done += 1

                if harvest and kind == "content":
                    for href in re.findall(r'href="([^"]{1,400})"', html):
                        c = canonical(urllib.parse.urljoin(url, href.replace("&amp;", "&")))
                        if not c or c in entries:
                            continue
                        if is_variant(c):
                            gkey = global_cap_key(c) or "(unclassified-variant)"
                            if global_counts.get(gkey, 0) >= cap_for(gkey):
                                variants_capped[gkey] = variants_capped.get(gkey, 0) + 1
                                continue
                            global_counts[gkey] = global_counts.get(gkey, 0) + 1
                            entries[c] = {"state": "pending",
                                          "discovered_by": "harvest-variant"}
                        else:
                            entries[c] = {"state": "pending", "discovered_by": "harvest"}

            if batch_network_failures == len(chunk):
                consecutive_network_failures += 1
            else:
                consecutive_network_failures = 0
            if consecutive_network_failures >= 2:
                print("two consecutive all-failed batches -- stopping and leaving "
                      "everything pending. Fix the network, then rerun; nothing "
                      "has been marked error.")
                save()
                return 2

            failed += batch_network_failures
            save()
            rate = done / max(0.001, time.time() - started)
            remaining = sum(1 for e in entries.values() if e["state"] == "pending")
            print(f"[{done:6d} done] batch {start // batch + 1} "
                  f"net-fail={batch_network_failures} challenged={challenged} "
                  f"{rate:.2f} pages/s  pending={remaining}")

    save()
    print(json.dumps({
        "done": done,
        "network_failures": failed,
        "challenged": challenged,
        "product_bodies_kept": product_bodies_kept,
        "product_extract_failures": len(extract_failures),
        "product_extract_failure_examples": extract_failures[:10],
        "variant_urls_kept": sum(global_counts.values()),
        "variant_urls_kept_by_facet": dict(sorted(global_counts.items())),
        "variant_urls_dropped_by_cap": sum(variants_capped.values()),
        "seconds": round(time.time() - started, 1),
    }, indent=2))
    if variants_capped:
        # Never a silent truncation: a bounded frontier that does not say what it
        # bounded reads exactly like a complete one.
        queue["variant_cap"] = {
            "caps_per_facet_type": {**GLOBAL_VARIANT_CAPS,
                                    "(any other *_uFilter)": DEFAULT_FACET_CAP},
            "kept_by_facet": dict(sorted(global_counts.items())),
            "dropped_by_facet": dict(sorted(variants_capped.items(),
                                            key=lambda kv: -kv[1])),
            "dropped_total": sum(variants_capped.values()),
        }
        save()
        print(f"NOTE: {sum(variants_capped.values())} facet/sort/page variant "
              f"URLs were left out by the per-facet caps; "
              f"{sum(global_counts.values())} were kept across "
              f"{len(global_counts)} facet types. Recorded in the queue under "
              "'variant_cap'.")
    if extract_failures:
        print(f"NOTE: {len(extract_failures)} product pages published no "
              "schema.org Product block; their full bodies were retained instead "
              "so nothing was lost. They need a second reader.")
    return 0


def reclassify(queue_path: pathlib.Path, out_root: pathlib.Path) -> int:
    """Re-run classify() over already-captured bodies. No network, no browser.

    The classification rule is the one part of capture most likely to be wrong on
    a first pass, and refetching 10k pages to correct a label would be absurd.
    """
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    changed: dict[str, int] = {}
    for url, entry in queue["entries"].items():
        if entry.get("state") != "done" or not entry.get("slug"):
            continue
        page_dir = out_root / entry["slug"]
        html = read_body(page_dir)
        if html is None:
            if entry.get("body_retained") is False:
                # Intentionally not retained; its classification came from the
                # body we did receive and is not re-derivable. Leave it alone
                # rather than resetting a captured page to pending.
                continue
            entry["state"] = "pending"
            entry["last_error"] = "captured body is missing from disk"
            continue
        kind = classify(url, entry.get("upstream_status", 200), html)
        if kind != entry.get("classification"):
            changed[f"{entry.get('classification')} -> {kind}"] = \
                changed.get(f"{entry.get('classification')} -> {kind}", 0) + 1
            entry["classification"] = kind
            meta_path = page_dir / "fetch.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                meta["classification"] = kind
                meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    queue_path.write_text(json.dumps(queue, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"changed": changed}, indent=2))
    return 0


def status(queue_path: pathlib.Path) -> int:
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    states: dict[str, int] = {}
    kinds: dict[str, int] = {}
    for e in queue["entries"].values():
        states[e["state"]] = states.get(e["state"], 0) + 1
        if e.get("classification"):
            kinds[e["classification"]] = kinds.get(e["classification"], 0) + 1
    print(json.dumps({
        "total": len(queue["entries"]),
        "states": dict(sorted(states.items())),
        "classifications": dict(sorted(kinds.items(), key=lambda kv: -kv[1])),
        "sitemap_locs": queue.get("sitemap_locs"),
        "skipped_robots_disallowed": queue.get("skipped_robots_disallowed"),
    }, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("frontier")
    f.add_argument("--sitemap", required=True)
    f.add_argument("--out", required=True)
    f.add_argument("--seed", action="append", default=[])

    r = sub.add_parser("run")
    r.add_argument("--queue", required=True)
    r.add_argument("--out-root", default=None)
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--concurrency", type=int, default=4,
                   help="measured optimum; higher does not help, the server paces us")
    r.add_argument("--batch", type=int, default=40)
    r.add_argument("--no-harvest", action="store_true",
                   help="do not add newly discovered links to the queue")
    r.add_argument("--full-product-sample", type=int, default=600,
                   help="how many product pages keep their full body; the rest "
                        "keep a structured extract. The detail template is cut "
                        "from one of these and generalised against the others.")

    s = sub.add_parser("status")
    s.add_argument("--queue", required=True)

    rc = sub.add_parser("reclassify")
    rc.add_argument("--queue", required=True)
    rc.add_argument("--out-root", default=None)

    args = ap.parse_args()

    if args.cmd == "frontier":
        q = build_frontier(pathlib.Path(args.sitemap), args.seed)
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(q, indent=1) + "\n", encoding="utf-8")
        print(json.dumps({k: v for k, v in q.items() if k != "entries"}, indent=2))
        print(f"entries: {len(q['entries'])}")
        return 0
    if args.cmd == "status":
        return status(pathlib.Path(args.queue))

    today = dt.date.today().isoformat()
    out_root = pathlib.Path(args.out_root) if args.out_root else \
        SITE_ROOT / "source-current" / f"{today}.browser-fetch"
    if args.cmd == "reclassify":
        # Reclassify must read the directory the capture actually wrote, which is
        # not necessarily today's: a run that crosses midnight, or a rerun the
        # next day, would otherwise silently reclassify an empty directory and
        # report success. Pick the capture directory with the most pages.
        if not args.out_root:
            roots = sorted((SITE_ROOT / "source-current").glob("*"),
                           key=lambda p: sum(1 for _ in p.glob("*/dom.html")))
            if not roots or not any(roots[-1].glob("*/dom.html")):
                raise SystemExit("no capture directory with pages in it")
            out_root = roots[-1]
        print(f"reclassifying from {out_root}")
        return reclassify(pathlib.Path(args.queue), out_root)
    return run_capture(pathlib.Path(args.queue), out_root, args.limit,
                       args.concurrency, args.batch, not args.no_harvest,
                       args.full_product_sample)


if __name__ == "__main__":
    raise SystemExit(main())
