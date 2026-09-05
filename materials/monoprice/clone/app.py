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

import gzip
import hashlib
import json
import pathlib
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
@app.get("/medialibrary/{full_path:path}")
def serve_image_host_path(full_path: str, request: Request) -> Response:
    prefix = request.url.path.split("/")[1]
    return serve_asset(f"images.monoprice.com/{prefix}/{full_path}")


# --------------------------------------------------------------------------- #
# The mini-cart the header asks for on every page
# --------------------------------------------------------------------------- #

@app.get("/cart/minicart")
def minicart(request: Request) -> Response:
    """The header's cart flyout.

    The source fetches this on every page load -- it was answering 404 on 27 of
    60 audited routes. The markup is this project's own, for the same reason the
    cart page is: /cart is under a robots Disallow rule.
    """
    cart_id = cart_id_from(request)
    lines = cart_lines(cart_id) if cart_id else []
    count = sum(line["quantity"] for line in lines)
    total = round(sum(line["line_total"] for line in lines), 2)
    if not lines:
        body = ('<div class="wb-minicart" data-cart-count="0">'
                '<p class="wb-muted">Your cart is empty.</p></div>')
    else:
        rows = "".join(
            f'<li data-p-id="{commerce.esc(line["p_id"])}">'
            f'<a href="/product?p_id={commerce.esc(line["p_id"])}">'
            f'{commerce.esc(line["name"])}</a> &times; {line["quantity"]} '
            f'<span>{commerce.money(line["line_total"], line["currency"])}</span>'
            "</li>" for line in lines)
        body = (f'<div class="wb-minicart" data-cart-count="{count}">'
                f"<ul>{rows}</ul>"
                f'<p data-minicart-total>Subtotal '
                f'{commerce.money(total, lines[0]["currency"])}</p>'
                f'<p><a class="wb-btn" href="/cart">View cart</a></p></div>')
    return Response(content=body, media_type="text/html; charset=utf-8")


@app.post("/minicart/removeitem")
async def minicart_remove(request: Request) -> Response:
    form = await request.form()
    pid = (form.get("p_id") or form.get("productId") or "").strip()
    cart_id = cart_id_from(request)
    if cart_id and pid:
        with _state["backend"].lifecycle.connection(transaction=True) as conn:
            conn.execute("DELETE FROM cart_lines WHERE cart_id=? AND p_id=?",
                         (cart_id, pid))
    return minicart(request)


# --------------------------------------------------------------------------- #
# Search and the type-ahead that replaces Unbxd
# --------------------------------------------------------------------------- #

def search_products(term: str, limit: int = 48) -> list[sqlite3.Row]:
    if not term.strip():
        return []
    like = f"%{term.strip()}%"
    with connection() as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT p_id, name, brand, price, currency FROM products "
            "WHERE name LIKE ? OR sku = ? OR brand LIKE ? "
            "ORDER BY CASE WHEN name LIKE ? THEN 0 ELSE 1 END, LENGTH(name), name "
            "LIMIT ?",
            (like, term.strip(), like, f"{term.strip()}%", limit)).fetchall()


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
    rows = search_products(keyword) if keyword else []
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
    return Response(content=page, media_type="text/html; charset=utf-8")


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


@app.api_route("/{full_path:path}", methods=["GET", "HEAD", "POST"])
def catch_all(full_path: str, request: Request) -> Response:
    if not _state.get("ready"):
        return JSONResponse({"error": "starting"}, status_code=503)
    path = "/" + full_path
    low = path.lower()

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

    if low.startswith("/product"):
        return product_page(request)

    return not_found_response(accept)
