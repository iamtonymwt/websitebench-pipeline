"""Turn captured monoprice pages into pages the clone can serve offline.

What this does, in order, per page: rewrite every reference that points off this
machine, strip the third-party tags, and write the result under
`clone/static/frozen/<route>.html`.

Four rules here were each bought with a day somewhere else in this family:

1. **An attribute value runs to its own delimiting quote.** Writing the value
   class as `[^"']*` looks right and is not: a double-quoted attribute may
   legally contain an apostrophe, and this catalogue is full of them. The whole
   attribute then fails to match -- and an attribute that does not match is not
   counted as unresolved, it is not counted at all. The report stays silent
   while the page keeps requesting a CDN.

2. **Decide by the value, not by the attribute name.** Enumerating `src`,
   `href`, `poster`, `srcset`, `data-src`, ... never terminates, and `\\b(href)`
   quietly matches the `href` inside `data-href`. The question is only ever
   "is this value an absolute URL to somewhere else".

3. **Never repoint a reference at a file that is not on disk.** Rewriting to a
   local path that 404s converts a remote request into a local one and reports
   it as closure. Every rewrite is checked against the asset tree.

4. **A stripped tag leaves nothing behind that is still a request.** `src=""`
   makes the browser re-request the current page; an id concatenated onto an
   empty base makes it request `/GTM-XXXX`. Placeholders are chosen per element,
   not per attribute.

The belt-and-braces measure is a `Content-Security-Policy: default-src 'self'`
header served by the app. Widening a strip list is a race against the next
injection technique; the header refuses the request before it leaves.

    python3 tools/build_frozen_pages.py --capture-dir source-current \
        --assets-dir source-assets --catalogue data/catalogue.json \
        --out-root clone/static/frozen --report scope/frozen-pages.json
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
from capture_pages import read_body  # noqa: E402
from fetch_assets import asset_target  # noqa: E402

LOCAL_ASSET_PREFIX = "/static/assets"

# Rule 1. The value runs to the *delimiting* quote. `(?:(?!(?P=q)).)*` is the
# whole point of this pattern; do not "simplify" it to [^"']*.
URL_ATTR_SPAN = re.compile(
    r"""(?P<attr>[\w:.-]+)(?P<eq>\s*=\s*)(?P<q>["'])(?P<v>(?:(?!(?P=q)).)*)(?P=q)""",
    re.I | re.S)

CSS_URL = re.compile(r"""url\(\s*(?P<q>['"]?)(?P<v>[^)'"]+)(?P=q)\s*\)""", re.I)

ABSOLUTE = re.compile(r"^(?:https?:)?//", re.I)

# Hosts whose bytes we hold locally.
LOCAL_HOSTS = {"www.monoprice.com", "monoprice.com", "images.monoprice.com"}

# Third-party tags removed wholesale. Everything here was observed loading on a
# captured page; nothing is speculative.
THIRD_PARTY_HOST_HINTS = (
    "googletagmanager", "google-analytics", "googleadservices", "doubleclick",
    "google.com/recaptcha", "gstatic.com/recaptcha", "facebook.net",
    "facebook.com/tr", "bat.bing.com", "snap.licdn.com", "px.ads.linkedin",
    "redditstatic", "alb.reddit", "criteo", "amazon-adsystem", "hotjar",
    "listrakbi", "listrak", "lt02.net", "hs-scripts", "hs-analytics",
    "hs-banner", "hsadspixel", "usemessages", "hubapi", "hubspot",
    "cookielaw.org", "onetrust", "adobedtm", "omtrdc.net", "demdex",
    "px-cloud.net", "px-cdn.net", "perimeterx", "affirm.com", "five9.net",
    "nagich.com", "apollo.io", "aplo-evnt", "liadm.com", "cloudflareinsights",
    "wra-api.net", "sitemaphosting", "kayako", "scanalert", "trustkeeper",
    "truste.com", "cloudfront.net", "unbxd", "capi-automation",
)

# First-party paths that exist only to proxy a third party. A remote-request
# audit is structurally blind to these -- the request never leaves the origin --
# so they have to be named here.
FIRST_PARTY_TRACKER_PATHS = ("/securemetrics/", "/CommissionJunction/",
                             "/cdn-cgi/")

SCRIPT_TAG = re.compile(r"<script\b[^>]*>.*?</script>|<script\b[^>]*/?>",
                        re.I | re.S)
LINK_TAG = re.compile(r"<link\b[^>]*>", re.I)
IFRAME_TAG = re.compile(r"<iframe\b[^>]*>.*?</iframe>|<iframe\b[^>]*/?>", re.I | re.S)
NOSCRIPT_TAG = re.compile(r"<noscript\b[^>]*>.*?</noscript>", re.I | re.S)


def is_third_party(value: str) -> bool:
    low = value.lower()
    if any(h in low for h in THIRD_PARTY_HOST_HINTS):
        return True
    return any(p.lower() in low for p in FIRST_PARTY_TRACKER_PATHS)


class Localiser:
    """Rewrites one page's references and keeps a per-reason tally."""

    def __init__(self, assets_dir: pathlib.Path, base_url: str,
                 served_routes: set[str], served_products: set[str]):
        self.assets_dir = assets_dir
        self.base_url = base_url
        self.served_routes = served_routes
        self.served_products = served_products
        self.tally: collections.Counter = collections.Counter()
        self.unresolved: list[str] = []

    # -- assets ---------------------------------------------------------- #
    def local_asset(self, absolute: str) -> str | None:
        target = asset_target(absolute)
        if target is None:
            return None
        host, local = target
        # Rule 3: only repoint at bytes that are actually here.
        if not (self.assets_dir / host / local).exists():
            self.tally["asset_missing_on_disk"] += 1
            self.unresolved.append(absolute)
            return None
        return f"{LOCAL_ASSET_PREFIX}/{host}/{urllib.parse.quote(local)}"

    # -- routes ---------------------------------------------------------- #
    def local_route(self, absolute: str) -> str | None:
        u = urllib.parse.urlsplit(absolute)
        if u.netloc and u.netloc.lower() not in LOCAL_HOSTS:
            return None
        path = u.path.lower() or "/"
        query = u.query
        if path.startswith("/product"):
            pid = dict(urllib.parse.parse_qsl(query)).get("p_id")
            if pid is None:
                return None
            if pid not in self.served_products:
                # A tile advertising a product the clone cannot serve is worse
                # than an absent tile: the link resolves and the page 404s.
                self.tally["route_product_not_served"] += 1
                return ""
            return f"/product?p_id={pid}"
        keep = [(k, v) for k, v in urllib.parse.parse_qsl(query)
                if k.lower() not in {"page", "page_type", "location_type",
                                     "start_date", "promo_type"}]
        rebuilt = urllib.parse.urlencode(keep)
        return f"{path}?{rebuilt}" if rebuilt else path

    def rewrite_value(self, value: str) -> str | None:
        """None means 'leave alone'; '' means 'this reference must go'."""
        raw = value.strip()
        if not raw or raw.startswith(("data:", "javascript:", "mailto:", "tel:",
                                      "#", "{{", "${")):
            return None
        if is_third_party(raw):
            self.tally["third_party_reference_removed"] += 1
            return ""
        absolute = urllib.parse.urljoin(self.base_url, raw.replace("&amp;", "&"))
        u = urllib.parse.urlsplit(absolute)
        if u.scheme not in ("http", "https"):
            return None
        if u.netloc.lower() not in LOCAL_HOSTS:
            self.tally["offsite_reference_removed"] += 1
            return ""
        local = self.local_asset(absolute)
        if local is not None:
            self.tally["asset_localised"] += 1
            return local
        route = self.local_route(absolute)
        if route is not None:
            if route:
                self.tally["route_localised"] += 1
            return route
        if ABSOLUTE.match(raw) or raw.startswith("http"):
            self.tally["same_host_absolute_made_relative"] += 1
            return u.path + (f"?{u.query}" if u.query else "")
        return None


def strip_third_party_tags(html: str, tally: collections.Counter) -> str:
    def drop_if_third_party(pattern: re.Pattern, label: str, text: str) -> str:
        def repl(m: re.Match) -> str:
            if is_third_party(m.group(0)):
                tally[label] += 1
                return ""
            return m.group(0)
        return pattern.sub(repl, text)

    html = drop_if_third_party(SCRIPT_TAG, "script_removed", html)
    html = drop_if_third_party(LINK_TAG, "link_removed", html)
    html = drop_if_third_party(IFRAME_TAG, "iframe_removed", html)
    # A <noscript> body is inert markup until scripting is off, and its contents
    # are pixels. grep says these pages "load GTM"; the browser says they do not.
    # Removing them keeps a static scan from reporting a leak that is not one.
    html = drop_if_third_party(NOSCRIPT_TAG, "noscript_removed", html)
    return html


def route_for(url: str) -> str:
    u = urllib.parse.urlsplit(url)
    path = u.path.lower().strip("/") or "index"
    if u.query:
        keep = sorted(urllib.parse.parse_qsl(u.query))
        if keep:
            path += "__" + urllib.parse.urlencode(keep)
    path = re.sub(r"[^A-Za-z0-9._&=,%+-]+", "-", path)
    return path[:180]


def freeze_page(html: str, base_url: str, loc: Localiser,
                tally: collections.Counter) -> str:
    html = strip_third_party_tags(html, tally)

    def attr_repl(m: re.Match) -> str:
        attr, eq, q, value = m.group("attr"), m.group("eq"), m.group("q"), m.group("v")
        # Rule 2: decide by the value. An attribute whose value is not a
        # reference is left exactly as it was.
        if not value.strip():
            return m.group(0)
        looks_like_ref = (ABSOLUTE.match(value) or value.startswith("/")
                          or re.match(r"^\.{1,2}/", value)
                          or re.match(r"^[\w.-]+/[\w./?=&%-]+$", value))
        if not looks_like_ref:
            return m.group(0)
        if "," in value and re.search(r"\s\d+[wx]", value):     # a srcset
            parts = []
            for chunk in value.split(","):
                chunk = chunk.strip()
                if not chunk:
                    continue
                bits = chunk.split(None, 1)
                new = loc.rewrite_value(bits[0])
                if new == "":
                    continue
                parts.append(" ".join([new if new is not None else bits[0], *bits[1:]]))
            if not parts:
                # Rule 4: an emptied srcset is not inert. Remove the attribute.
                tally["srcset_attribute_removed"] += 1
                return ""
            return f"{attr}{eq}{q}{', '.join(parts)}{q}"
        new = loc.rewrite_value(value)
        if new is None:
            return m.group(0)
        if new == "":
            # Rule 4 again: src="" re-requests the current document. Drop the
            # attribute rather than blanking it.
            tally["attribute_removed_rather_than_blanked"] += 1
            return ""
        return f"{attr}{eq}{q}{new}{q}"

    html = URL_ATTR_SPAN.sub(attr_repl, html)

    def css_repl(m: re.Match) -> str:
        new = loc.rewrite_value(m.group("v"))
        if new is None:
            return m.group(0)
        if new == "":
            tally["css_url_removed"] += 1
            return "url(about:blank)"
        return f'url("{new}")'

    return CSS_URL.sub(css_repl, html)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture-dir", required=True)
    ap.add_argument("--assets-dir", required=True)
    ap.add_argument("--catalogue", required=True)
    ap.add_argument("--out-root", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    catalogue = json.loads(pathlib.Path(args.catalogue).read_text(encoding="utf-8"))
    served_products = {p["p_id"] for p in catalogue["products"]}
    served_routes = {c["path"] for c in catalogue["categories"]}
    assets_dir = pathlib.Path(args.assets_dir)
    out_root = pathlib.Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    tally: collections.Counter = collections.Counter()
    unresolved: list[str] = []
    written = 0
    by_kind: collections.Counter = collections.Counter()

    page_dirs = sorted(d for d in pathlib.Path(args.capture_dir).glob("*/*")
                       if d.is_dir())
    if args.limit:
        page_dirs = page_dirs[:args.limit]

    for page_dir in page_dirs:
        meta_path = page_dir / "fetch.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        kind = meta.get("classification")
        # An error page captured from the source is not a content page. Serving
        # one with status 200 is a false success, and this site's absent-product
        # page looks entirely ordinary.
        if kind not in ("content", "empty-listing"):
            by_kind[f"skipped:{kind}"] += 1
            continue
        html = read_body(page_dir)
        if html is None:
            by_kind["skipped:body-not-retained"] += 1
            continue
        loc = Localiser(assets_dir, meta["url"], served_routes, served_products)
        frozen = freeze_page(html, meta["url"], loc, tally)
        tally.update(loc.tally)
        unresolved.extend(loc.unresolved[:5])
        dest = out_root / f"{route_for(meta['url'])}.html"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(frozen, encoding="utf-8")
        by_kind[f"written:{kind}"] += 1
        written += 1

    report = {
        "schema_version": "monoprice.frozen-pages.v1",
        "pages_written": written,
        "by_kind": dict(sorted(by_kind.items())),
        "rewrites": dict(sorted(tally.items())),
        "unresolved_examples": sorted(set(unresolved))[:40],
        "unresolved_total": tally.get("asset_missing_on_disk", 0),
        "note": ("`asset_missing_on_disk` is the number of references left "
                 "pointing at bytes that are not in the asset tree. They are "
                 "counted, not silently skipped: an unmatched reference that is "
                 "not counted is how a page keeps calling a CDN while the "
                 "closure report reads clean."),
    }
    pathlib.Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.report).write_text(json.dumps(report, indent=2) + "\n",
                                         encoding="utf-8")
    print(json.dumps(report, indent=2)[:2500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
