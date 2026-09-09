"""The monoprice offline clone.

Three kinds of route, in the order they are tried:

1. **A frozen page.** 5,980 captured pages, stored gzipped and served with
   `Content-Encoding: gzip` -- the bytes go out untouched, which is why storing
   them compressed costs nothing at request time. These are the source's own
   served markup, localised.
2. **A page built from the catalogue.** 3,289 product pages kept a structured
   extract rather than a body, and they are rendered into a template cut from a
   real captured product page.
3. **The source's own not-found page**, for anything else.

Things worth knowing before changing this file:

* **`/cart`, `/Checkout` and `/myaccount` are written here, not captured.** All
  three are under robots Disallow rules on the source, so no evidence of them
  exists or will. They live in the source's own page shell and say plainly that
  payment settles against a local sandbox.
* **An absent product answers 200 on the source**, with the title "Products no
  longer Available". The clone reproduces that rather than answering 404,
  because that is what the source does. 1,906 product ids are in this state.
* **The search type-ahead is served from here.** On the source it is a
  client-side call to Unbxd that fires on every keystroke -- a remote request no
  page-load audit can see. The third-party script is stripped and this endpoint
  replaces it.
* **A JSON 404 is not the same as an empty 200.** Where a service cannot be
  reproduced, this app answers 404 with a JSON body so a caller takes the error
  branch it already has. Answering `{}` with status 200 tells the caller it
  succeeded, and it then reads fields that are not there.
"""

from __future__ import annotations

import functools
import gzip
import hashlib
import json
import pathlib
import re
import secrets
import sqlite3
import sys
import urllib.parse
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

CLONE_DIR = pathlib.Path(__file__).resolve().parent
SITE_DIR = CLONE_DIR.parent
FROZEN_ROOT = CLONE_DIR / "static" / "frozen"
ASSET_ROOT = SITE_DIR / "source-assets"
CATALOGUE_PATH = SITE_DIR / "data" / "catalogue.json"

sys.path.insert(0, str(CLONE_DIR))
import commerce  # noqa: E402
from backend.site_backend_integration import open_site_services  # noqa: E402

SITE_ID = "monoprice"
DISPLAY_NAME = "Monoprice"

app = FastAPI(title=DISPLAY_NAME)

_state: dict[str, Any] = {"ready": False}


# --------------------------------------------------------------------------- #
# Schema and seed
# --------------------------------------------------------------------------- #

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
  p_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  brand TEXT,
  description TEXT,
  sku TEXT,
  gtin14 TEXT,
  price REAL,
  currency TEXT,
  availability TEXT,
  rating_value TEXT,
  rating_count TEXT,
  review_count TEXT,
  url_path TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS product_images (
  p_id TEXT NOT NULL,
  position INTEGER NOT NULL,
  url TEXT NOT NULL,
  PRIMARY KEY (p_id, position)
);
CREATE TABLE IF NOT EXISTS categories (
  path TEXT PRIMARY KEY,
  name TEXT,
  kind TEXT,
  level INTEGER,
  parent TEXT
);
CREATE TABLE IF NOT EXISTS product_categories (
  p_id TEXT NOT NULL,
  category_path TEXT NOT NULL,
  evidence TEXT NOT NULL,
  position INTEGER,
  PRIMARY KEY (p_id, category_path)
);
CREATE INDEX IF NOT EXISTS idx_pc_category ON product_categories(category_path);
CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);

CREATE TABLE IF NOT EXISTS carts (
  cart_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cart_lines (
  cart_id TEXT NOT NULL,
  p_id TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  PRIMARY KEY (cart_id, p_id)
);
-- No column here can hold a card number, a CVV or an expiry. The boundary is
-- in the schema rather than in a comment promising not to store payment data.
CREATE TABLE IF NOT EXISTS orders (
  order_id TEXT PRIMARY KEY,
  cart_id TEXT NOT NULL,
  placed_at TEXT NOT NULL,
  total_minor INTEGER NOT NULL,
  currency TEXT NOT NULL,
  ship_name TEXT,
  ship_city TEXT,
  ship_state TEXT,
  ship_postal TEXT
);
CREATE TABLE IF NOT EXISTS order_lines (
  order_id TEXT NOT NULL,
  p_id TEXT NOT NULL,
  name TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  unit_price REAL NOT NULL,
  PRIMARY KEY (order_id, p_id)
);
"""


def seed_catalogue(connection: sqlite3.Connection) -> dict[str, int]:
    connection.executescript(SCHEMA)
    already = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    if already:
        return {"products": already, "seeded": 0}
    catalogue = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))

    products = catalogue["products"]
    connection.executemany(
        "INSERT OR REPLACE INTO products (p_id,name,brand,description,sku,gtin14,"
        "price,currency,availability,rating_value,rating_count,review_count,url_path)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(p["p_id"], p["name"], p["brand"], p["description"], p["sku"],
          p["gtin14"], p["price"], p["currency"], p["availability"],
          p["rating_value"], p["rating_count"], p["review_count"], p["url_path"])
         for p in products])
    connection.executemany(
        "INSERT OR REPLACE INTO product_images (p_id,position,url) VALUES (?,?,?)",
        [(p["p_id"], i, u) for p in products for i, u in enumerate(p["images"])])
    connection.executemany(
        "INSERT OR REPLACE INTO categories (path,name,kind,level,parent)"
        " VALUES (?,?,?,?,?)",
        [(c["path"], c.get("name"), c.get("kind"), c.get("level"), c.get("parent"))
         for c in catalogue["categories"]])
    # The relation is written once with its evidence kept. A membership seen only
    # on a listing page is the only record that the product belongs there.
    connection.executemany(
        "INSERT OR REPLACE INTO product_categories (p_id,category_path,evidence,"
        "position) VALUES (?,?,?,?)",
        [(m["p_id"], m["category_path"], m["evidence"], m.get("position"))
         for m in catalogue["product_categories"]])
    return {"products": len(products),
            "categories": len(catalogue["categories"]),
            "memberships": len(catalogue["product_categories"]),
            "seeded": len(products)}


# --------------------------------------------------------------------------- #
# Frozen pages
# --------------------------------------------------------------------------- #

def load_route_map() -> dict[str, str]:
    path = FROZEN_ROOT / "route-map.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))["routes"]
    out: dict[str, str] = {}
    for url, route in raw.items():
        u = urllib.parse.urlsplit(url)
        key = canonical_request_key(u.path, u.query)
        out[key] = route
    return out


def canonical_request_key(path: str, query: str) -> str:
    """One key for the URL forms that name the same page.

    The source serves `/product` and `/product/index`, `/Category` and
    `/category`, and hangs tracking parameters off product links. All of those
    have to arrive at one frozen file, or a link that works on the source 404s
    here.
    """
    p = path.lower() or "/"
    if p == "/product/index":
        p = "/product"
    keep = [(k, v) for k, v in urllib.parse.parse_qsl(query)
            if k.lower() not in {"page", "page_type", "location_type",
                                 "start_date", "promo_type", "popup", "seq",
                                 "utm_source", "utm_medium", "utm_campaign",
                                 "utm_term", "utm_content", "gclid", "msclkid",
                                 "fbclid", "cjevent"}]
    keep.sort()
    return p + ("?" + urllib.parse.urlencode(keep) if keep else "")


def frozen_response(route: str, status: int = 200,
                    accept_encoding: str = "") -> Response | None:
    """Serve the stored bytes, compressed only if the caller said it can decode.

    Sending `Content-Encoding: gzip` unconditionally is wrong and it bit
    immediately: any client that does not advertise gzip -- a plain urllib
    request, a checker, a script -- receives compressed bytes it will not
    decompress, and every assertion about page content then reads a binary blob.
    It looked like the pages were empty.
    """
    path = FROZEN_ROOT / f"{route}.html.gz"
    if not path.exists():
        return None
    raw = path.read_bytes()
    if "gzip" in (accept_encoding or "").lower():
        return Response(content=raw, status_code=status,
                        media_type="text/html; charset=utf-8",
                        headers={"Content-Encoding": "gzip",
                                 "Vary": "Accept-Encoding"})
    return Response(content=gzip.decompress(raw), status_code=status,
                    media_type="text/html; charset=utf-8",
                    headers={"Vary": "Accept-Encoding"})


def frozen_text(route: str) -> str | None:
    path = FROZEN_ROOT / f"{route}.html.gz"
    if not path.exists():
        return None
    with gzip.open(path, "rb") as fh:
        return fh.read().decode("utf-8", "replace")


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #

@app.on_event("startup")
def startup() -> None:
    backend, auth = open_site_services()
    with backend.lifecycle.connection(transaction=True) as connection:
        summary = seed_catalogue(connection)
    _state.update({"backend": backend, "auth": auth,
                   "routes": load_route_map(), "seed": summary, "ready": True})
    # Startup log, not the health response: useful to a person, invisible to the
    # contract.
    print(f"monoprice clone ready: {len(_state['routes'])} frozen routes, "
          f"{summary.get('products')} products", flush=True)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    # The reliable measure, rather than widening a strip list forever: the
    # browser refuses the request before it leaves the machine. A guard that
    # runs after insertion is not a guard -- the request is already out.
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; font-src 'self' data:; "
        "frame-src 'none'; connect-src 'self'; form-action 'self'"
    )
    response.headers["Referrer-Policy"] = "same-origin"
    return response


@app.get("/__websitebench/health")
def health() -> JSONResponse:
    """Exactly `{"status": "ok"}` -- the deployment ABI says so.

    This carried site_id, frozen_routes and catalogue counts, which was useful
    for me and wrong for the contract: a candidate rebuilding this site from the
    benchmark would not emit them, and extra keys here are a trace of the copy in
    the one response the harness compares. The counts are printed at startup
    instead, where they help without being part of the interface.
    """
    if not _state.get("ready"):
        return JSONResponse({"status": "starting"}, status_code=503)
    return JSONResponse({"status": "ok"})


def connection():
    return _state["backend"].lifecycle.connection()


# --------------------------------------------------------------------------- #
# Assets
# --------------------------------------------------------------------------- #

MEDIA_TYPES = {
    ".css": "text/css", ".js": "application/javascript", ".json": "application/json",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
    ".ico": "image/x-icon", ".woff": "font/woff", ".woff2": "font/woff2",
    ".ttf": "font/ttf", ".otf": "font/otf", ".eot": "application/vnd.ms-fontobject",
    ".mp4": "video/mp4", ".webm": "video/webm", ".pdf": "application/pdf",
}


@app.get("/static/assets/{full_path:path}")
def serve_asset(full_path: str) -> Response:
    # Decode before touching the filesystem. The bytes were stored under their
    # decoded names precisely so that this lookup finds them; leaving an escape
    # in the name is how a file can exist, be referenced correctly, and 404.
    decoded = urllib.parse.unquote(full_path)
    candidate = (ASSET_ROOT / decoded).resolve()
    if not str(candidate).startswith(str(ASSET_ROOT.resolve())):
        return JSONResponse({"error": "not found"}, status_code=404)
    if not candidate.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    suffix = candidate.suffix.lower()
    return Response(content=candidate.read_bytes(),
                    media_type=MEDIA_TYPES.get(suffix, "application/octet-stream"),
                    headers={"Cache-Control": "public, max-age=3600"})


# The source's own asset paths, served where the source serves them.
#
# This is not a convenience. RequireJS and the loader at /src/index.js build
# their URLs at run time, so no rewriting can reach them -- `/Scripts/Footer.js`
# appears in no page's markup and every page requests it. Serving these paths
# directly means the runtime injection works untouched, and it is also more
# faithful: the clone answers the same URLs the source does.
@app.get("/assets/{full_path:path}")
@app.get("/Scripts/{full_path:path}")
@app.get("/src/{full_path:path}")
@app.get("/Content/{full_path:path}")
@app.get("/cf-fonts/{full_path:path}")
def serve_first_party_asset(full_path: str, request: Request) -> Response:
    prefix = request.url.path.split("/")[1]
    return serve_asset(f"www.monoprice.com/{prefix}/{full_path}")


# The image host's own paths, answered from the image tree.
#
# Some image URLs are assembled at run time from a base that no rewrite reaches,
# and the browser then asks this origin for `/cms_images/...` root-relative. The
# runtime audit found them as same-origin 404s -- a class of failure that belongs
# to no other gate, since they neither leave the machine nor appear as links.
# Answering the source's own paths costs nothing and removes the whole class.
@app.get("/cms_images/{full_path:path}")
@app.get("/mp/{full_path:path}")
@app.get("/productlargeimages/{full_path:path}")
@app.get("/productmediumimages/{full_path:path}")
@app.get("/productsmallimages/{full_path:path}")
@app.get("/buttons/{full_path:path}")
@app.get("/backgrounds/{full_path:path}")
@app.get("/images/{full_path:path}")
@app.get("/medialibrary/{full_path:path}")
def serve_image_host_path(full_path: str, request: Request) -> Response:
    prefix = request.url.path.split("/")[1]
    return serve_asset(f"images.monoprice.com/{prefix}/{full_path}")


# --------------------------------------------------------------------------- #
# The mini-cart the header asks for on every page
# --------------------------------------------------------------------------- #

def minicart_payload(request: Request) -> dict[str, Any]:
    """The mini-cart, in the shape the site's own script reads.

    This used to return an HTML fragment. That was a guess, and the guess broke
    the Add to Cart button. minicart.js does:

        jQuery.post('/Cart', {p_id, qty})
          .then(() => jQuery.getJSON('/cart/minicart'))
          .then(results => { MPI.ee.cacheCartItems(results.items);
                             render(results); })

    `getJSON` on an HTML body rejects, so the chain stopped after the POST: the
    item was added and nothing else happened -- no mini-cart update, no
    navigation. The four keys below (`items`, `itemCount`, `subTotal`,
    `miniCart`) are the four the caller reads, and the per-item field names come
    from CART_ITEM_FIELDS in the site's own enhanced-ecommerce.js. None of it is
    invented: a shaped response is only safe when the shape was read out of the
    caller's code.
    """
    cart_id = cart_id_from(request)
    lines = cart_lines(cart_id) if cart_id else []
    items = []
    for line in lines:
        image = None
        with connection() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT url FROM product_images WHERE p_id = ? ORDER BY position "
                "LIMIT 1", (line["p_id"],)).fetchone()
        if row:
            image = local_image_url(row["url"])
        items.append({
            "uid": line["p_id"],
            "id": line["p_id"],
            "productID": line["p_id"],
            "name": line["name"],
            "brand": "Monoprice",
            "price": line["price"],
            "quantity": line["quantity"],
            "productImageUrl": image or "",
            "productPageUrl": f"/product?p_id={line['p_id']}",
            "discountedPriceTotal": line["line_total"],
        })
    count = sum(line["quantity"] for line in lines)
    total = round(sum(line["line_total"] for line in lines), 2)
    currency = lines[0]["currency"] if lines else "USD"
    return {"items": items, "itemCount": count,
            "subTotal": commerce.money(total, currency),
            "miniCart": commerce.minicart_fragment(lines, count, total, currency)}


@app.get("/cart/minicart")
def minicart(request: Request) -> JSONResponse:
    return JSONResponse(minicart_payload(request))


@app.post("/cart/minicart")
async def minicart_remove_line(request: Request) -> JSONResponse:
    """Removing a line. The script posts `ca_idx=<cart item id>` to this path.

    Same path for read and remove is the site's own arrangement, read from
    minicart.js rather than chosen here.
    """
    form = await request.form()
    target = (form.get("ca_idx") or form.get("p_id") or "").strip()
    cart_id = cart_id_from(request)
    if cart_id and target:
        with _state["backend"].lifecycle.connection(transaction=True) as conn:
            conn.execute("DELETE FROM cart_lines WHERE cart_id=? AND p_id=?",
                         (cart_id, target))
    return JSONResponse(minicart_payload(request))


@app.post("/minicart/removeitem")
async def minicart_remove(request: Request) -> JSONResponse:
    form = await request.form()
    target = (form.get("p_id") or form.get("ca_idx") or "").strip()
    cart_id = cart_id_from(request)
    if cart_id and target:
        with _state["backend"].lifecycle.connection(transaction=True) as conn:
            conn.execute("DELETE FROM cart_lines WHERE cart_id=? AND p_id=?",
                         (cart_id, target))
    return JSONResponse(minicart_payload(request))


# --------------------------------------------------------------------------- #
# Search and the type-ahead that replaces Unbxd
# --------------------------------------------------------------------------- #

# The facet sidebar's links are real and they were being ignored.
#
# Every filter link on a search page carries its selection in the query string:
#
#   /search/index?keyword=hdmi%20cable&v_master_Length_uFilter=6ft&TotalProducts=224
#
# 54 distinct facet parameters appear across the captured pages. The handler read
# only `keyword`, so following a "6ft" filter re-rendered the identical 316
# results under a heading that said the results were filtered. That is worse than
# an obviously dead link: the page looks like it worked.
#
# Two conventions of the source's own, both taken from the captured URLs rather
# than assumed: `&` is written as ` mand ` inside a value ("AV mand Computer
# Adapters"), and several values in one facet are comma-separated and mean OR.
CATEGORY_FACET = re.compile(r"^categorypath\d+_ufilter$", re.I)


def decode_facet_value(value: str) -> str:
    """`AV mand Computer Adapters` is how the source writes an ampersand."""
    return value.replace(" mand ", " & ").strip()


def selected_facets(params) -> list[tuple[str, list[str]]]:
    out = []
    for key in params.keys():
        if not key.lower().endswith("_ufilter"):
            continue
        values = [decode_facet_value(v)
                  for raw in params.getlist(key)
                  for v in raw.split(",") if v.strip()]
        if values:
            out.append((key, values))
    return out


def products_in_categories(conn: sqlite3.Connection, names: list[str]) -> set[str]:
    """p_ids whose category name matches any of these facet values."""
    lowered = [n.lower() for n in names]
    marks = ",".join("?" for _ in lowered)
    rows = conn.execute(
        "SELECT DISTINCT pc.p_id FROM product_categories pc "
        "JOIN categories c ON c.path = pc.category_path "
        f"WHERE LOWER(c.name) IN ({marks})", lowered).fetchall()
    return {r[0] for r in rows}


def matches_facets(row: sqlite3.Row, facets: list[tuple[str, list[str]]],
                   category_members: dict[str, set[str]]) -> bool:
    for key, values in facets:
        if CATEGORY_FACET.match(key):
            if row["p_id"] not in category_members.get(key, set()):
                return False
            continue
        if key.lower() == "v_brand_name_ufilter":
            brand = (row["brand"] or "").lower()
            if not any(v.lower() == brand for v in values):
                return False
            continue
        # Every other facet -- Length, Color, Wattage, Gauge, Connector -- is an
        # attribute the catalogue does not carry as a field. It is carried in the
        # product name, which is where the variant map reads it from too.
        #
        # Matched on a token boundary, not as a substring: `6ft` is inside
        # `16ft`, so a plain `in` test kept 23 of 24 results for a Length=6ft
        # filter and the narrowing looked real while being almost meaningless.
        # Same shape as the vendor-name substring that deleted first-party code
        # in the freezer -- match the thing, not text containing it.
        name = row["name"].lower()
        if not any(FACET_VALUE_BOUNDARY(v).search(name) for v in values):
            return False
    return True


@functools.lru_cache(maxsize=2048)
def FACET_VALUE_BOUNDARY(value: str) -> re.Pattern:  # noqa: N802
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(value.lower())
                      + r"(?![A-Za-z0-9])")


# 24 per page, because that is what the source serves. Counted on a frozen
# category listing, which is the source's own markup: 25 distinct products, the
# 25th being chrome. The clone was returning 48 and the search page then rendered
# 35,569 characters against the source's 13,299 and stood 12,854px tall against
# 6,917 -- a page that is twice as long as the original is as wrong as one that
# is half as long, and the visible-content audit flags both because it compares
# ratios in each direction.
SEARCH_PAGE_SIZE = 24


# The sort control was inert, and the page-size control with it.
#
# Both are `<select>` elements whose options carry the whole query string, and
# the page's own inline `js_sort` navigates to it:
#
#   <select name="itemsort" onchange="js_sort(this,1)">
#     <option data-url="keyword=hdmi cable&sort=sellingPrice asc&TotalProducts=224">
#   function js_sort(forms, type) {
#     var Domain = "/search/index";
#     location.href = Domain + "?" + $('option:selected', forms).attr('data-url');
#   }
#
# So selecting a sort produced a perfectly good URL that this handler read
# `keyword` out of and nothing else -- the page reloaded, looked identical, and
# the control appeared broken. Same shape as the facets, found the same way: by
# someone using the page.
#
# The clause is chosen from this table, never built from the parameter. The
# values are the source's own strings, read off the options it serves.
SORT_CLAUSES = {
    "": None,                                            # Best Match
    "title asc": "name COLLATE NOCASE ASC",
    "sellingprice asc": "price IS NULL, price ASC",
    "sellingprice desc": "price IS NULL, price DESC",
    "rating_count desc,sort_rating desc":
        "CAST(COALESCE(rating_count,'0') AS INTEGER) DESC, "
        "CAST(COALESCE(rating_value,'0') AS REAL) DESC",
    # No first_instock_date in the catalogue -- the source's own sort is
    # `first_instock_date desc,sku desc`, so the sku half is reproduced and the
    # date half is not. Recorded rather than faked with a random order.
    "first_instock_date desc,sku desc": "CAST(p_id AS INTEGER) DESC",
}
# The page-size control offers exactly these.
PAGE_SIZE_CHOICES = (25, 50, 75, 100)

# Sorting a frozen listing.
#
# A category page is served as captured, so choosing a sort on it changed
# nothing -- the dropdown still read "Best Match" and the products kept their
# original order. The search page could sort because it renders per request;
# the category page cannot, so its rows are permuted here instead.
#
# This only moves existing markup. Each result row is an innermost `<tr>` that
# names exactly one product; the rows are reordered and written back into the
# same slots, so every class, style and attribute the source served is
# preserved and only the sequence changes.
#
# The row finder is duplicated from tools/extract_search_template.py on purpose.
# `clone/` has to stand alone to be deployed, so it cannot import from `tools/`.
# Both copies use the same rule -- walk tag depth, keep rows containing no
# nested row -- and both exist because a non-greedy `<tr>.*?</tr>` can start on
# an outer layout row and swallow the results container.
TR_TAG = re.compile(r"<(/?)tr\b[^>]*>", re.I)
ROW_PRODUCT = re.compile(r'href="/product\?p_id=(\d+)"')

SORT_KEYS = {
    "title asc": ("name", False),
    "sellingprice asc": ("price", False),
    "sellingprice desc": ("price", True),
    "rating_count desc,sort_rating desc": ("rating", True),
    "first_instock_date desc,sku desc": ("pid", True),
}


def listing_rows(html: str) -> list[tuple[int, int, str]]:
    """(start, end, p_id) for each innermost row naming exactly one product."""
    rows: list[tuple[int, int, str]] = []
    stack: list[int] = []
    for m in TR_TAG.finditer(html):
        if not m.group(1):
            stack.append(m.start())
        elif stack:
            start = stack.pop()
            block = html[start:m.end()]
            if len(re.findall(r"<tr\b", block, re.I)) != 1:
                continue
            ids = set(ROW_PRODUCT.findall(block))
            if len(ids) == 1:
                rows.append((start, m.end(), ids.pop()))
    rows.sort()
    return rows


def _sort_values(p_ids: list[str]) -> dict[str, tuple]:
    if not p_ids:
        return {}
    marks = ",".join("?" for _ in p_ids)
    with connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT p_id, name, price, rating_count FROM products "
            f"WHERE p_id IN ({marks})", p_ids).fetchall()
    return {r["p_id"]: (r["name"] or "", r["price"],
                        int(r["rating_count"] or 0)) for r in rows}


def reorder_frozen_listing(html: str, raw_sort: str) -> str:
    """Permute a captured listing's rows, or return it untouched."""
    key = " ".join((raw_sort or "").lower().split())
    field_desc = SORT_KEYS.get(key)
    if field_desc is None:
        return html
    field, descending = field_desc
    rows = listing_rows(html)
    if len(rows) < 2:
        return html

    values = _sort_values([pid for _, _, pid in rows])

    def sort_key(entry: tuple[int, int, str]):
        name, price, rating = values.get(entry[2], ("", None, 0))
        if field == "price":
            # A product with no price sorts last either way, rather than
            # sorting as zero and heading the "cheapest first" list.
            return (price is None, price if price is not None else 0.0)
        if field == "name":
            return (False, name.lower())
        if field == "rating":
            return (False, rating)
        return (False, int(entry[2]) if entry[2].isdigit() else 0)

    ordered = sorted(rows, key=sort_key, reverse=descending)
    # `reverse` would also flip the "missing value last" flag, so put those
    # back at the end explicitly.
    if descending and field == "price":
        present = [r for r in ordered if values.get(r[2], ("", None, 0))[1] is not None]
        missing = [r for r in ordered if values.get(r[2], ("", None, 0))[1] is None]
        ordered = present + missing

    pieces: list[str] = []
    cursor = 0
    for slot, source in zip(rows, ordered):
        start, end, _ = slot
        pieces.append(html[cursor:start])
        pieces.append(html[source[0]:source[1]])
        cursor = end
    pieces.append(html[cursor:])
    return "".join(pieces)


SORT_OPTION = re.compile(
    r"""(<option\b[^>]*\bdata-url\s*=\s*"[^"]*?sort=(?P<sort>[^&"]*)[^"]*"[^>]*>)""",
    re.I)


def mark_selected_sort(html: str, raw_sort: str) -> str:
    """Show the chosen sort in the dropdown instead of Best Match."""
    wanted = urllib.parse.unquote_plus(raw_sort or "").strip().lower()

    def repl(m: re.Match) -> str:
        tag = re.sub(r"\s+selected(?:\s*=\s*\"[^\"]*\")?", "", m.group(1), flags=re.I)
        value = urllib.parse.unquote_plus(m.group("sort")).strip().lower()
        if value == wanted:
            tag = tag[:-1].rstrip() + " selected>"
        return tag

    return SORT_OPTION.sub(repl, html)


def sort_clause(raw: str) -> str | None:
    return SORT_CLAUSES.get(" ".join((raw or "").lower().split()))


def page_size(raw: str) -> int:
    try:
        wanted = int(raw)
    except (TypeError, ValueError):
        return SEARCH_PAGE_SIZE
    return wanted if wanted in PAGE_SIZE_CHOICES else SEARCH_PAGE_SIZE


def search_products(term: str, limit: int = SEARCH_PAGE_SIZE,
                    facets: list[tuple[str, list[str]]] | None = None,
                    order_by: str | None = None
                    ) -> list[sqlite3.Row]:
    if not term.strip():
        return []
    like = f"%{term.strip()}%"
    # Facets are applied before the limit. Filtering the first 48 rows would make
    # a narrow facet return almost nothing for reasons that have nothing to do
    # with the facet.
    # Only facets need a wider fetch, because they are applied in Python after
    # the query. Ordering happens in SQL, so `LIMIT limit` already returns the
    # correct top N -- widening the fetch for it and forgetting to truncate is
    # what made a sorted search return 198 results where an unsorted one
    # returned 24.
    fetch = limit if not facets else max(limit * 20, 600)
    # Relevance is the default and is the source's "Best Match": an exact prefix
    # first, then shorter names. An explicit sort replaces it entirely.
    ordering = order_by or ("CASE WHEN name LIKE ? THEN 0 ELSE 1 END, "
                            "LENGTH(name), name")
    params: list = [like, term.strip(), like]
    if order_by is None:
        params.append(f"{term.strip()}%")
    params.append(fetch)
    with connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT p_id, name, brand, price, currency, rating_count, rating_value "
            "FROM products WHERE name LIKE ? OR sku = ? OR brand LIKE ? "
            f"ORDER BY {ordering} LIMIT ?", params).fetchall()
        if not facets:
            return rows[:limit]
        category_members = {
            key: products_in_categories(conn, values)
            for key, values in facets if CATEGORY_FACET.match(key)}
    kept = [r for r in rows if matches_facets(r, facets, category_members)]
    return kept[:limit]


SEARCH_TEMPLATE_PATH = CLONE_DIR / "static" / "search-template.json"


@app.get("/search/index")
def search_page(request: Request) -> Response:
    """Results rendered into the source's own results table.

    The grid markup is a `<tr>` cut from a captured search page, not markup
    written here. Inventing class names would produce a page the real stylesheet
    does not style -- which is how an earlier site in this family shipped three
    page types with no layout at all while every gate stayed green.
    """
    template = _state.get("search_template")
    if template is None:
        if not SEARCH_TEMPLATE_PATH.exists():
            return JSONResponse(
                {"error": "search template has not been built",
                 "fix": "run tools/extract_search_template.py"}, status_code=500)
        template = json.loads(SEARCH_TEMPLATE_PATH.read_text(encoding="utf-8"))
        _state["search_template"] = template

    keyword = (request.query_params.get("keyword") or "").strip()
    facets = selected_facets(request.query_params)
    ordering = sort_clause(request.query_params.get("sort") or "")
    size = page_size(request.query_params.get("rows") or "")
    rows = (search_products(keyword, limit=size, facets=facets, order_by=ordering)
            if keyword else [])
    truncate_at = template.get("name_truncate_at")

    tiles = []
    for row in rows:
        with connection() as conn:
            conn.row_factory = sqlite3.Row
            image_row = conn.execute(
                "SELECT url FROM product_images WHERE p_id = ? ORDER BY position "
                "LIMIT 1", (row["p_id"],)).fetchone()
        local = local_image_url(image_row["url"]) if image_row else None
        name = row["name"]
        # The source truncates long titles in the results table. Reproducing the
        # truncation is part of reproducing the page.
        if truncate_at and len(name) > truncate_at:
            name = name[:truncate_at]
        tile = (template["tile"]
                .replace("@@WB_TILE_NAME@@", html_escape(name))
                .replace("@@WB_TILE_PID@@", html_escape(row["p_id"]))
                .replace("@@WB_TILE_PRICE@@",
                         f"{row['price']:.2f}" if row["price"] is not None else "")
                .replace("@@WB_TILE_IMAGE@@", html_escape(
                    local or "/static/assets/images.monoprice.com/"
                             "assets/images/loading-img.gif")))
        tiles.append(tile)

    page = (template["page"]
            .replace("@@WB_RESULTS@@", "".join(tiles))
            .replace("@@WB_QUERY@@_ENC", urllib.parse.quote(keyword, safe=""))
            .replace("@@WB_QUERY@@_PLUS", urllib.parse.quote_plus(keyword))
            .replace("@@WB_QUERY@@_UPPER", html_escape(keyword.upper()))
            .replace("@@WB_QUERY@@", html_escape(keyword)))
    page = choose_results_container(page, bool(tiles))
    return Response(content=page, media_type="text/html; charset=utf-8")


# HawkSearch hides both result containers in the served markup and lets its
# hosted script reveal the right one. The freezer makes that choice for a frozen
# listing, but a search page is assembled here per query, so the choice has to
# be made here too -- from the one thing the freezer cannot know, which is
# whether *this* query matched anything.
#
# Skipping this was how the clone showed a blank page for `hdmi cable` while
# holding 316 matching product links in the DOM.
_EXISTRESULT = re.compile(
    r"""(<div\b[^>]*\bid\s*=\s*["']existresult["'][^>]*>)""", re.I)
_NORESULT = re.compile(
    r"""(<div\b[^>]*\bid\s*=\s*["']noresult["'][^>]*>)""", re.I)
_DISPLAY = re.compile(r"display\s*:\s*(?:none|block)\s*;?", re.I)


def choose_results_container(page: str, has_results: bool) -> str:
    """Show the results table, or the source's own empty state -- never both."""
    def set_display(pattern: re.Pattern, visible: bool, html: str) -> str:
        want = "display: block;" if visible else "display: none;"
        return pattern.sub(lambda m: _DISPLAY.sub(want, m.group(1)), html, count=1)

    page = set_display(_EXISTRESULT, has_results, page)
    return set_display(_NORESULT, not has_results, page)


@app.get("/api/suggest")
def suggest(q: str = "") -> JSONResponse:
    """The offline replacement for the source's Unbxd type-ahead.

    On the source this is a cross-origin request on every keystroke. It is
    invisible to a page-load audit -- nothing fires until someone types -- which
    is exactly why it needs an endpoint here rather than a note in a report.
    """
    term = (q or "").strip()
    if len(term) < 2:
        return JSONResponse({"query": term, "suggestions": []})
    with connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT p_id, name, price, currency FROM products WHERE name LIKE ? "
            "ORDER BY LENGTH(name), name LIMIT 8", (f"%{term}%",)).fetchall()
    return JSONResponse({
        "query": term,
        "suggestions": [{"name": r["name"], "p_id": r["p_id"],
                         "price": r["price"], "currency": r["currency"],
                         "url": f"/product?p_id={r['p_id']}"} for r in rows],
    })


# --------------------------------------------------------------------------- #
# Product detail, rendered from the template for products with no frozen page
# --------------------------------------------------------------------------- #

DETAIL_TEMPLATE_PATH = CLONE_DIR / "static" / "detail-template.html"
TEMPLATE_IMAGE_SLOTS = 4          # what the donor page had


def local_image_url(url: str) -> str | None:
    """The clone path for a source image, or None when the bytes are not here.

    Returning a path for a file we do not hold would turn a missing picture into
    a local 404 and let the closure report call it resolved.
    """
    split = urllib.parse.urlsplit(url)
    host = split.netloc.lower()
    if host not in ("images.monoprice.com", "www.monoprice.com"):
        return None
    local = urllib.parse.unquote(split.path.lstrip("/"))
    if not (ASSET_ROOT / host / local).is_file():
        return None
    return f"/static/assets/{host}/{urllib.parse.quote(local)}"


def render_product(row: sqlite3.Row) -> Response:
    template = _state.get("detail_template")
    if template is None:
        if not DETAIL_TEMPLATE_PATH.exists():
            return JSONResponse(
                {"error": "product detail template has not been built",
                 "fix": "run tools/extract_detail_template.py"}, status_code=500)
        template = DETAIL_TEMPLATE_PATH.read_text(encoding="utf-8")
        _state["detail_template"] = template

    with connection() as conn:
        conn.row_factory = sqlite3.Row
        images = [r["url"] for r in conn.execute(
            "SELECT url FROM product_images WHERE p_id = ? ORDER BY position",
            (row["p_id"],)).fetchall()]

    resolved = [u for u in (local_image_url(i) for i in images) if u]
    if not resolved:
        # No usable picture. Fall back to whatever the donor page used, rather
        # than leaving an empty src -- an empty src makes the browser re-request
        # the current document.
        resolved = ["/static/assets/images.monoprice.com/assets/images/loading-img.gif"]

    markup = template
    for index in range(TEMPLATE_IMAGE_SLOTS):
        # A slot beyond this product's image count reuses the last real image.
        # Leaving the token in place would print "@@WB_IMAGE_3@@" as a URL.
        chosen = resolved[index] if index < len(resolved) else resolved[-1]
        markup = markup.replace(f"@@WB_IMAGE_{index}@@", html_escape(chosen))

    markup = markup.replace("@@WB_DESCRIPTION@@", html_escape(row["description"] or ""))
    markup = markup.replace("@@WB_NAME@@", html_escape(row["name"]))
    markup = markup.replace("@@WB_PRICE@@",
                            f"{row['price']:.2f}" if row["price"] is not None else "")
    markup = markup.replace("@@WB_GTIN@@", html_escape(row["gtin14"] or ""))
    markup = markup.replace("@@WB_SKU@@", html_escape(row["sku"] or row["p_id"]))
    markup = markup.replace("@@WB_PID@@", html_escape(row["p_id"]))
    markup = markup.replace("@@WB_BRAND@@", html_escape(row["brand"] or ""))
    return Response(content=markup, media_type="text/html; charset=utf-8")


def html_escape(value: str) -> str:
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# --------------------------------------------------------------------------- #
# Cart and checkout -- written here, because the source forbids capturing them
# --------------------------------------------------------------------------- #

CART_COOKIE = "wb_cart"


def cart_id_from(request: Request) -> str | None:
    return request.cookies.get(CART_COOKIE)


def ensure_cart(request: Request) -> str:
    existing = cart_id_from(request)
    if existing:
        with connection() as conn:
            if conn.execute("SELECT 1 FROM carts WHERE cart_id = ?",
                            (existing,)).fetchone():
                return existing
    new_id = secrets.token_hex(16)
    with _state["backend"].lifecycle.connection(transaction=True) as conn:
        conn.execute("INSERT INTO carts (cart_id, created_at) VALUES (?, datetime('now'))",
                     (new_id,))
    return new_id


def cart_lines(cart_id: str) -> list[dict[str, Any]]:
    with connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT l.p_id, l.quantity, p.name, p.price, p.currency "
            "FROM cart_lines l JOIN products p ON p.p_id = l.p_id "
            "WHERE l.cart_id = ? ORDER BY p.name", (cart_id,)).fetchall()
    return [{"p_id": r["p_id"], "quantity": r["quantity"], "name": r["name"],
             "price": r["price"] or 0.0, "currency": r["currency"] or "USD",
             "line_total": round((r["price"] or 0.0) * r["quantity"], 2)}
            for r in rows]


@app.post("/cart")
@app.post("/cart/index")
async def cart_add(request: Request) -> Response:
    form = await request.form()
    pid = (form.get("p_id") or "").strip()
    try:
        qty = max(1, int(form.get("qty") or 1))
    except (TypeError, ValueError):
        qty = 1
    cart_id = ensure_cart(request)
    with connection() as conn:
        known = conn.execute("SELECT 1 FROM products WHERE p_id = ?", (pid,)).fetchone()
    if known:
        with _state["backend"].lifecycle.connection(transaction=True) as conn:
            conn.execute(
                "INSERT INTO cart_lines (cart_id, p_id, quantity) VALUES (?,?,?) "
                "ON CONFLICT(cart_id, p_id) DO UPDATE SET quantity = quantity + ?",
                (cart_id, pid, qty, qty))
    response = RedirectResponse("/cart", status_code=303)
    response.set_cookie(CART_COOKIE, cart_id, httponly=True, samesite="lax")
    return response


@app.get("/cart")
@app.get("/cart/index")
def cart_view(request: Request) -> Response:
    cart_id = cart_id_from(request)
    lines = cart_lines(cart_id) if cart_id else []
    return Response(content=commerce.cart_page(lines),
                    media_type="text/html; charset=utf-8")


# --------------------------------------------------------------------------- #
# Checkout
# --------------------------------------------------------------------------- #

@app.post("/cart/update")
async def cart_update(request: Request) -> Response:
    form = await request.form()
    pid = (form.get("p_id") or "").strip()
    try:
        qty = int(form.get("qty") or 0)
    except (TypeError, ValueError):
        qty = 0
    cart_id = cart_id_from(request)
    if cart_id and pid:
        with _state["backend"].lifecycle.connection(transaction=True) as conn:
            if qty <= 0:
                conn.execute("DELETE FROM cart_lines WHERE cart_id=? AND p_id=?",
                             (cart_id, pid))
            else:
                conn.execute("UPDATE cart_lines SET quantity=? WHERE cart_id=? "
                             "AND p_id=?", (qty, cart_id, pid))
    return RedirectResponse("/cart", status_code=303)


@app.post("/cart/remove")
async def cart_remove(request: Request) -> Response:
    form = await request.form()
    pid = (form.get("p_id") or "").strip()
    cart_id = cart_id_from(request)
    if cart_id and pid:
        with _state["backend"].lifecycle.connection(transaction=True) as conn:
            conn.execute("DELETE FROM cart_lines WHERE cart_id=? AND p_id=?",
                         (cart_id, pid))
    return RedirectResponse("/cart", status_code=303)


def sandbox_scenarios() -> list[dict[str, Any]]:
    return list(_state["backend"].config.payments["local_sandbox"]["scenarios"])


@app.get("/checkout")
def checkout_view(request: Request) -> Response:
    cart_id = cart_id_from(request)
    lines = cart_lines(cart_id) if cart_id else []
    return Response(content=commerce.checkout_page(lines, sandbox_scenarios()),
                    media_type="text/html; charset=utf-8")


@app.post("/checkout")
async def checkout_submit(request: Request) -> Response:
    form = await request.form()
    cart_id = cart_id_from(request)
    lines = cart_lines(cart_id) if cart_id else []
    if not lines:
        return Response(content=commerce.checkout_page([], sandbox_scenarios()),
                        media_type="text/html; charset=utf-8")

    total = round(sum(line["line_total"] for line in lines), 2)
    total_minor = int(round(total * 100))
    currency = lines[0]["currency"]
    scenario = (form.get("scenario") or "sandbox-approved").strip()
    payments = _state["backend"].payments
    reference = secrets.token_hex(8)

    # The backend requires the fingerprint to be a sha256 hex digest; it binds
    # an approval to an exact cart state so an approval for one basket cannot be
    # spent on another.
    fingerprint = hashlib.sha256(
        json.dumps([[line["p_id"], line["quantity"], line["price"]]
                    for line in lines] + [total_minor, currency],
                   sort_keys=True).encode()).hexdigest()
    intent = payments.create_intent(
        owner=f"cart:{cart_id}", amount_minor=total_minor, currency=currency,
        fingerprint=fingerprint, idempotency_key=f"intent-{reference}")
    outcome = payments.attempt(
        flow_id=intent["flow_id"], owner=f"cart:{cart_id}",
        amount_minor=total_minor, currency=currency, fingerprint=fingerprint,
        scenario_id=scenario, idempotency_key=f"attempt-{reference}")

    # The backend reports `status: "APPROVED"`. An earlier version read
    # `outcome["outcome"]`, a key that does not exist -- so `.get` returned None,
    # every payment compared unequal to "approved", and every purchase silently
    # took the declined branch. The field name was guessed instead of read.
    status = str(outcome.get("status", "")).upper()
    if status != "APPROVED":
        # A declined payment places no order and leaves the cart holding the
        # goods. Emptying it here would make a failed purchase look like a
        # successful one to everything downstream.
        note = ("The payment was declined by the sandbox. No order was placed "
                "and your cart is unchanged." if status == "DECLINED"
                else "The payment could not be completed. Please try again; "
                     "your cart is unchanged.")
        return Response(content=commerce.checkout_page(
            lines, sandbox_scenarios(), message=note),
            media_type="text/html; charset=utf-8", status_code=200)

    order_id = f"MP{reference.upper()}"
    with _state["backend"].lifecycle.connection(transaction=True) as conn:
        # Consume the approval inside the same transaction that writes the order.
        # An approval that is not consumed can be spent twice: two submissions of
        # the same approved checkout would place two orders.
        payments.consume_approval(
            conn, flow_id=intent["flow_id"], owner=f"cart:{cart_id}",
            amount_minor=total_minor, currency=currency, fingerprint=fingerprint)
        conn.execute(
            "INSERT INTO orders (order_id,cart_id,placed_at,total_minor,currency,"
            "ship_name,ship_city,ship_state,ship_postal) "
            "VALUES (?,?,datetime('now'),?,?,?,?,?,?)",
            (order_id, cart_id, total_minor, currency,
             (form.get("ship_name") or "").strip(),
             (form.get("ship_city") or "").strip(),
             (form.get("ship_state") or "").strip(),
             (form.get("ship_postal") or "").strip()))
        conn.executemany(
            "INSERT INTO order_lines (order_id,p_id,name,quantity,unit_price) "
            "VALUES (?,?,?,?,?)",
            [(order_id, line["p_id"], line["name"], line["quantity"],
              line["price"]) for line in lines])
        conn.execute("DELETE FROM cart_lines WHERE cart_id=?", (cart_id,))
    return RedirectResponse(f"/order/{order_id}", status_code=303)


@app.get("/order/{order_id}")
def order_view(order_id: str) -> Response:
    with connection() as conn:
        conn.row_factory = sqlite3.Row
        order = conn.execute("SELECT * FROM orders WHERE order_id = ?",
                             (order_id,)).fetchone()
        if order is None:
            return not_found_response()
        lines = conn.execute(
            "SELECT p_id,name,quantity,unit_price FROM order_lines "
            "WHERE order_id = ? ORDER BY name", (order_id,)).fetchall()
    return Response(content=commerce.order_page(dict(order),
                                                [dict(r) for r in lines]),
                    media_type="text/html; charset=utf-8")


def not_found_response(accept_encoding: str = "") -> Response:
    """The source's own 404 page, at status 404."""
    response = frozen_response("_error/not-found", status=404,
                               accept_encoding=accept_encoding)
    if response is not None:
        return response
    return JSONResponse({"error": "not found"}, status_code=404)


def absent_product_response(accept_encoding: str = "") -> Response:
    """What the source answers for an id it no longer sells: 200, not 404."""
    response = frozen_response("_error/absent-product", status=200,
                               accept_encoding=accept_encoding)
    if response is not None:
        return response
    return not_found_response(accept_encoding)


def product_page(request: Request) -> Response:
    accept = request.headers.get("accept-encoding", "")
    pid = (request.query_params.get("p_id") or "").strip()
    if not pid:
        return not_found_response(accept)
    with connection() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM products WHERE p_id = ?", (pid,)).fetchone()
    if row is None:
        # The source answers 200 with "Products no longer Available" for an id it
        # no longer sells -- 1,906 of them. Answering 404 would be a difference
        # the source does not have.
        return absent_product_response(accept)
    return render_product(row)


# --------------------------------------------------------------------------- #
# Services that cannot be reproduced
# --------------------------------------------------------------------------- #

# A JSON 404, never an empty 200. An empty success tells the caller the request
# worked, so it reads `.data` on undefined and unmounts what it just rendered.
# A 404 sends it down the error branch it already has.
DECLARED_ABSENT = (
    "/api/live-chat", "/v1/inventory", "/v1/wishlist", "/securemetrics",
    "/CommissionJunction", "/cdn-cgi",
)


# --------------------------------------------------------------------------- #
# Content fills: the fragments the page injects into hidden containers
# --------------------------------------------------------------------------- #
#
# Both `mp_homepage.js` and `mp_productPage_more.js` run the same loop:
#
#     $(item.outerContainerSelector).hide();                 // hide first
#     $.ajax({url: item.url + "?p_id=" + p_id + ...,
#              success: function (data) {
#                  $(item.innerContainerSelector).html(data);
#                  ...
#              }});
#
# The container is hidden *before* the request and revealed only on success, so
# an endpoint that does not answer leaves it hidden forever. That is what
# happened: `/home/*` answered 404, and the three `/product/*` ones fell through
# to the catch-all, which recognised `p_id` and returned the entire 407 KB
# product page for injection into a carousel. Visible result was the source
# showing 35 product tiles on a product page against the clone's 1, and the
# source rendering 9,264 characters of home page against the clone's 3,678.
#
# These routes must be declared BEFORE the catch-all. Declaration order is what
# decides the match, and the catch-all claiming `/product/...` is precisely how
# three of them came to return a whole page.
FRAGMENT_ROOT = CLONE_DIR / "static" / "fragments"


def _fragment_index() -> dict:
    index = _state.get("fragment_index")
    if index is None:
        path = FRAGMENT_ROOT / "index.json"
        index = (json.loads(path.read_text(encoding="utf-8"))["fragments"]
                 if path.exists() else {})
        _state["fragment_index"] = index
    return index


def fragment_response(key: str) -> Response:
    """Serve one localised fragment, or an empty body the way the source does.

    An empty answer is a real answer here and is not the same as a missing one:
    the source returns nothing for `GetCustomersAlsoShoppedFor` on products with
    no such data, and nothing for either `getRecentlyViewed` when the session
    has no history. Both were measured, not assumed. Answering 200 with an empty
    body reproduces the source; answering 404 would leave the container hidden.
    """
    entry = _fragment_index().get(key)
    if entry is None or entry.get("empty") or not entry.get("file"):
        return Response(content="", media_type="text/html; charset=utf-8")
    path = FRAGMENT_ROOT / entry["file"]
    if not path.exists():
        return Response(content="", media_type="text/html; charset=utf-8")
    with gzip.open(path, "rb") as fh:
        body = fh.read().decode("utf-8", "replace")
    return Response(content=body, media_type="text/html; charset=utf-8")


@app.get("/home/getRecommendationsForYou")
def home_recommendations() -> Response:
    return fragment_response("/home/getRecommendationsForYou")


@app.get("/home/getTopSellers")
def home_top_sellers() -> Response:
    return fragment_response("/home/getTopSellers")


@app.get("/home/getRecentlyViewed")
def home_recently_viewed() -> Response:
    # Empty on the source for a session with no history, including the warmed
    # session that had already browsed product pages. Serving the captured
    # empty body rather than inventing a filled strip: the markup for a filled
    # one was never observed, and inventing tile markup is how a page ends up
    # with class names no stylesheet in the clone styles.
    return fragment_response("/home/getRecentlyViewed")


@app.get("/product/GetCustomersAlsoShoppedFor")
def product_also_shopped(p_id: str = "", cust_review: str = "") -> Response:
    return fragment_response(
        f"/product/GetCustomersAlsoShoppedFor?p_id={p_id}")


@app.get("/product/getrecommendationsforyou")
def product_recommendations(p_id: str = "", cust_review: str = "") -> Response:
    # Measured identical across every product sampled, so one captured copy
    # serves all of them rather than 3,859 identical files.
    return fragment_response("/product/getrecommendationsforyou")


@app.get("/product/getrecentlyviewed")
def product_recently_viewed(p_id: str = "", cust_review: str = "") -> Response:
    return fragment_response("/product/getrecentlyviewed")


# --------------------------------------------------------------------------- #
# The variant chooser
# --------------------------------------------------------------------------- #
#
# Clicking `3ft` on a product page POSTs {vals, PID, changedVal} here and
# expects JSON partials for the product that combination identifies. The markup
# carries no product id for any option, so `tools/build_variant_map.py` resolves
# them offline by name substitution and the map is checked against the
# catalogue: 3,807 of 4,720 selectable options resolve exactly.
#
# Getting this wrong is not quiet. The site's own error branch is
#
#     error: function () { mpSpinner.hide();
#                          location.href = '/StaticContent/generalerror'; }
#
# and a 200 whose `descPartialView` is empty takes the same path, so before this
# existed, clicking any variant navigated the visitor to an error page.
VARIANT_MAP_PATH = CLONE_DIR / "static" / "variant-map.json"
PARTIAL_IDS = ("imagePartial", "infoPartial")


def _variant_map() -> dict:
    cached = _state.get("variant_map")
    if cached is None:
        cached = (json.loads(VARIANT_MAP_PATH.read_text(encoding="utf-8"))["products"]
                  if VARIANT_MAP_PATH.exists() else {})
        _state["variant_map"] = cached
    return cached


def _extract_partial(markup: str, element_id: str) -> str:
    """Inner HTML of one container, by balancing div depth from its open tag.

    A regex to the next `</div>` would cut at the first nested close, returning
    a fragment of the panel. The depth walk is the only reason the returned
    partial is the whole panel rather than its first child.
    """
    m = re.search(r"<div\b[^>]*\bid\s*=\s*[\"']" + re.escape(element_id)
                  + r"[\"'][^>]*>", markup, re.I)
    if not m:
        return ""
    start = m.end()
    depth = 1
    for tag in re.finditer(r"<(/?)div\b[^>]*>", markup[start:], re.I):
        depth += -1 if tag.group(1) else 1
        if depth == 0:
            return markup[start:start + tag.start()]
    return ""


def _product_markup(pid: str) -> str | None:
    """The product's page as the clone serves it, frozen body or template.

    The frozen body is preferred because 600 products have one, and it is the
    source's own markup -- including that product's real variant chooser, which
    the template does not carry at all.
    """
    # The startup handler stores this under "routes". Reading it as "route_map"
    # returned an empty dict every time and fell through to the template
    # silently -- a lookup that never matches looks exactly like a product that
    # has no frozen body.
    route = _state.get("routes", {}).get(
        canonical_request_key("/product", f"p_id={pid}"))
    if route:
        frozen = frozen_text(route)
        if frozen:
            return frozen
    with connection() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM products WHERE p_id = ?",
                           (pid,)).fetchone()
    if row is None:
        return None
    response = render_product(row)
    body = response.body
    return body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)


@app.api_route("/product/selectpid", methods=["GET", "POST"])
async def select_pid(request: Request) -> JSONResponse:
    payload: dict = {}
    if request.method == "POST":
        raw = await request.body()
        if raw:
            try:
                payload = json.loads(raw)
            except ValueError:
                # The site sends this as form-encoded in one code path and as
                # JSON in another; both reach here.
                form = urllib.parse.parse_qs(raw.decode("utf-8", "replace"))
                payload = {k: (v[0] if len(v) == 1 else v)
                           for k, v in form.items()}
    if not payload:
        payload = dict(request.query_params)

    pid = str(payload.get("PID") or payload.get("p_id") or "").strip()
    changed = str(payload.get("changedVal") or "").strip()
    target = _variant_map().get(pid, {}).get(changed, pid)

    markup = _product_markup(target) or _product_markup(pid)
    if markup is None:
        # Nothing to render at all. A JSON 404 is right here: the site has an
        # error branch for it, and an empty 200 would send it to the same error
        # page anyway while claiming success.
        return JSONResponse({"error": "unknown product", "p_id": pid},
                            status_code=404)

    with connection() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT description, name FROM products WHERE p_id = ?",
                           (target,)).fetchone()

    # `descPartialView` must be non-empty or the site's own handler navigates to
    # /StaticContent/generalerror. Its container, `#descPartial`, is not present
    # on any of the 600 frozen product pages -- so on the source too this value
    # is injected into an empty selector and has no visible effect. It is
    # answered with the product's own description rather than invented markup.
    description = (row["description"] if row and row["description"]
                   else (row["name"] if row else target))
    return JSONResponse({
        "imagePartialView": _extract_partial(markup, "imagePartial"),
        "infoPartialView": _extract_partial(markup, "infoPartial"),
        "descPartialView": description,
        "p_id": target,
        "resolved": target != pid,
    })


# The product page's tab panels, filled the same way and found much later: the
# script builds their URL under `tabUrl:`, not `url:`, so the first inventory --
# a grep for `url:` -- listed fifteen endpoints and missed these three.
#
# `mp_productPage_more.js` POSTs them and injects the result:
#
#     if (item.index === 3) { $("#qaTab").parent(".tab-content").prepend(data);
#                             $("#tab3").show(); }
#     else                  { $(item.selector).html(data); }
#
# Tab 3 carries the specifications and the long description, which is most of a
# product page's visible text. The loop skips indexes 2 and 4, and the source
# answers those 404 -- so this clone has no route for them either.
@app.api_route("/Product/GetTab1", methods=["GET", "POST"])
def product_tab1(p_id: str = "", cust_review: str = "") -> Response:
    return fragment_response("/Product/GetTab1")


@app.api_route("/Product/GetTab3", methods=["GET", "POST"])
def product_tab3(p_id: str = "", cust_review: str = "") -> Response:
    return fragment_response(f"/Product/GetTab3?p_id={p_id}")


@app.api_route("/Product/GetTab5", methods=["GET", "POST"])
def product_tab5(p_id: str = "", cust_review: str = "") -> Response:
    return fragment_response("/Product/GetTab5")


# The site calls these with the exact casing above. Anything else reaching the
# catch-all is bridged there, for the same reason `/Cart` had to be.
FRAGMENT_ROUTES = {
    "/product/gettab1": "/Product/GetTab1",
    "/product/gettab3": "/Product/GetTab3",
    "/product/gettab5": "/Product/GetTab5",
    "/home/getrecommendationsforyou": "/home/getRecommendationsForYou",
    "/home/gettopsellers": "/home/getTopSellers",
    "/home/getrecentlyviewed": "/home/getRecentlyViewed",
    "/product/getcustomersalsoshoppedfor": "/product/GetCustomersAlsoShoppedFor",
    "/product/getrecommendationsforyou": "/product/getrecommendationsforyou",
    "/product/getrecentlyviewed": "/product/getrecentlyviewed",
}


@app.api_route("/{full_path:path}", methods=["GET", "HEAD", "POST"])
def catch_all(full_path: str, request: Request) -> Response:
    if not _state.get("ready"):
        return JSONResponse({"error": "starting"}, status_code=503)
    path = "/" + full_path

    # The site's own minicart.js posts to `/Cart` -- capital C -- and FastAPI
    # paths are case-sensitive, so the Add to Cart button was answered 404 and
    # did nothing. The core commerce action was dead, and every unit test
    # passed throughout: they all POST to /cart directly, testing the endpoint
    # and never the control.
    if request.method == "POST":
        lowered = path.lower()
        if lowered in ("/cart", "/cart/index"):
            return RedirectResponse("/cart", status_code=307)
        if lowered in ("/cart/minicart", "/minicart/removeitem"):
            return RedirectResponse(lowered, status_code=307)
    low = path.lower()

    # A content-fill endpoint reached with different casing. Answering it here
    # rather than letting it fall through matters more than it looks: these
    # endpoints' containers are hidden until the request succeeds, so a miss is
    # not a missing strip, it is a strip that never appears again.
    if low in FRAGMENT_ROUTES:
        key = FRAGMENT_ROUTES[low]
        if key in ("/product/GetCustomersAlsoShoppedFor", "/Product/GetTab3"):
            key = f"{key}?p_id={request.query_params.get('p_id', '')}"
        return fragment_response(key)

    if any(low.startswith(p.lower()) for p in DECLARED_ABSENT):
        return JSONResponse(
            {"error": "service not reproduced in this offline clone",
             "path": path}, status_code=404)

    # PerimeterX serves its sensor from a first-party path -- two long random
    # segments under /p/ -- so it looks like an ordinary page request and showed
    # up as an unexplained same-origin 404 on 38 of 197 audited routes. It is a
    # bot-detection sensor, not a page. Naming it makes the absence declared
    # rather than mysterious. The site's real /p/ pages are /p/shop, /p/cat and
    # /p/resources, so the exclusion cannot swallow one.
    segments = [s for s in low.split("/") if s]
    if (len(segments) == 3 and segments[0] == "p"
            and segments[1] not in ("shop", "cat", "resources")
            and len(segments[1]) > 20):
        return JSONResponse(
            {"error": "bot-detection sensor; not reproduced in this offline clone",
             "path": path}, status_code=404)

    accept = request.headers.get("accept-encoding", "")
    key = canonical_request_key(path, request.url.query)
    # `.get` rather than `_state["routes"]`: a request that arrives before
    # startup finished should get a 503, not a KeyError traceback.
    route = _state.get("routes", {}).get(key)
    if route is not None:
        response = frozen_response(route, accept_encoding=accept)
        if response is not None:
            return response

    # A listing reached with a sort or page-size selection. The page's own
    # `js_sort` navigates to the current path plus the option's whole query
    # string, so a category URL arrives as
    #
    #   /category/cables/hdmi-cables/hdmi-cables?&menuDisStr=hdmi cables
    #       &sort=sellingPrice asc&TotalProducts=36
    #
    # and none of that matched the route map, so choosing a sort on a category
    # page answered 404 -- worse than the search page, where it merely had no
    # effect. Retrying the lookup without those four parameters serves the
    # captured listing instead. Its order is the order the source served, so the
    # selection still does not reorder a category; see claim cl-024. The route
    # map is not rebuilt for this, and the key function is left alone, so no two
    # captured pages can collide as a result.
    if route is None:
        stripped = [(k, v) for k, v in request.query_params.multi_items()
                    if k.lower() not in ("sort", "rows", "menudisstr",
                                         "totalproducts")]
        if len(stripped) != len(request.query_params.multi_items()):
            retry = _state.get("routes", {}).get(
                canonical_request_key(path, urllib.parse.urlencode(stripped)))
            if retry is not None:
                raw_sort = request.query_params.get("sort") or ""
                if sort_clause(raw_sort) and raw_sort.strip():
                    body = frozen_text(retry)
                    if body is not None:
                        body = reorder_frozen_listing(body, raw_sort)
                        body = mark_selected_sort(body, raw_sort)
                        return Response(content=body,
                                        media_type="text/html; charset=utf-8")
                response = frozen_response(retry, accept_encoding=accept)
                if response is not None:
                    return response

    if low.startswith("/product"):
        return product_page(request)

    # The source serves search results under `/category/search/index` as well
    # as `/search/index` -- the facet links on a category listing are written
    # relative, so they resolve against the category path. 10 such pages were
    # captured and are served from the route map above; every other keyword and
    # facet combination reached this point and was answered 404.
    #
    # The runtime audit caught this and attributed it correctly: 1 same-origin
    # failure that is this project's gap, against 2 that are declared absences.
    # That classification is the only reason it was distinguishable from the
    # PerimeterX sensor noise sitting next to it in the same report.
    if low in ("/category/search/index", "/category/search"):
        return search_page(request)

    return not_found_response(accept)
