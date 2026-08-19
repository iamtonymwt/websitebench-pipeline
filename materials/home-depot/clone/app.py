"""The Home Depot offline clone — FastAPI composition root.

Layout (WebsiteBench offline-clone shape, per ASPCA precedent):

* Frozen localized snapshots (``frontend/pages/*.html``) captured anonymously
  from www.homedepot.com, asset-localized to ``/static`` and stripped of all
  remote/telemetry script, are served at their real source routes. Every
  React-app surface is served as its post-render DOM baseline; client
  interactivity (search submit, add-to-cart, filters, checkout accordion) is
  re-implemented locally in ``static/site/*.js`` against the JSON API below.
* The JSON API (added incrementally) serves the frozen catalog, cart, checkout
  (``local-sandbox`` payment), account, orders and lists through the vendored
  ``websitebench.site_backend`` runtime. The source walk stopped before payment
  submission; the clone-local place-order step accepts only an opaque scenario
  id and rejects card/credential facts.
* ``GET /healthz`` returns exactly ``{"ok":true,"site_id":"home-depot"}``.
* ``POST /__admin/reset`` is guarded by a constant-time admin-token compare.
* Every response carries a same-origin CSP; no remote origin is reachable.
"""

from __future__ import annotations

import hmac
import html
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from starlette.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SITE_ID = "home-depot"
DISPLAY_NAME = "The Home Depot"
PAGES_DIR = ROOT / "frontend" / "pages"
STATIC_DIR = ROOT / "static"

_HEALTH_BODY = json.dumps({"ok": True, "site_id": SITE_ID}, separators=(",", ":"))

ADMIN_TOKEN = os.environ.get("WEBSITEBENCH_HOME_DEPOT_ADMIN_TOKEN", "home-depot-local-admin")
BUILD_ID = os.environ.get("DEPLOYMENT_BUILD_ID") or os.environ.get("WEBSITEBENCH_BUILD_ID")

# Same-origin CSP: frozen documents carry inline styles; the load-bearing
# property is default-src 'self' — zero remote runtime requests.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

# Real source route -> frozen page fixture (localized). Frozen snapshots are the
# visual/structural baseline; dynamic behavior (search, filters, add-to-cart,
# checkout) is layered on via the JSON API + static/site JS incrementally.
PAGE_ROUTES: dict[str, str] = {
    "/": "home",
    # cart/checkout/confirmation use the home shell (its header CSS bundle is
    # complete; cart-empty's captured header shipped a smaller CSS split and
    # renders unstyled). hd-app.js overlays the live panel below the header.
    "/cart": "home",
    "/checkout": "home",
    "/order-confirmation": "home",
    "/auth/view/signin": "auth-signin",
    "/auth/view/createaccount": "auth-signin",  # email-first entry folds in
    "/c/customer-service": "help",
    "/c/customer_service": "help",
}

# Category PLP by Endeca N-code (…/N-5yc1vZ<code>).
PLP_BY_NCODE: dict[str, str] = {
    "N-5yc1vZc1xy": "plp-tools",
    "N-5yc1vZc27f": "plp-drills",
}
# PDP by trailing itemId (/p/<slug>/<itemId>).
PDP_BY_ITEMID: dict[str, str] = {
    "320326787": "pdp-anchor",
}
_NCODE_RE = re.compile(r"(N-[A-Za-z0-9]+)")
_ITEMID_RE = re.compile(r"/(\d{6,})/?$")

_PAGE_CACHE: dict[str, str] = {}
_RUNTIME_TAG = '<script src="/static/site/hd-app.js" defer></script>'


def _load_page(name: str) -> str | None:
    if name in _PAGE_CACHE:
        return _PAGE_CACHE[name]
    path = PAGES_DIR / f"{name}.html"
    if not path.is_file():
        return None
    body = path.read_text(encoding="utf-8")
    if _RUNTIME_TAG not in body:
        if "</body>" in body:
            body = body.replace("</body>", f"{_RUNTIME_TAG}</body>", 1)
        else:
            body = body + _RUNTIME_TAG
    _PAGE_CACHE[name] = body
    return body


def _not_found_response() -> HTMLResponse:
    body = _load_page("not-found")
    if body is None:
        body = ("<!doctype html><html lang=en><head><meta charset=utf-8>"
                "<title>Page Not Found - The Home Depot</title></head>"
                "<body><h1>Sorry, we can't find that page.</h1>"
                "<p><a href='/'>Return to homepage</a></p></body></html>")
    return HTMLResponse(body, status_code=404)


_EXTERNAL_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>External link</title></head>
<body style="font-family:sans-serif;max-width:40rem;margin:4rem auto">
<h1>External link</h1>
<p>This offline clone does not open third-party destinations ({slug}).
No remote request was made.</p>
<p><a href="/">Return to The Home Depot home page</a></p>
</body></html>
"""

app = FastAPI(title=f"{DISPLAY_NAME} offline clone",
              docs_url=None, redoc_url=None, openapi_url=None)


class _MirrorStaticFiles(StaticFiles):
    """Retry percent-encoded on-disk names when the decoded lookup misses."""

    def lookup_path(self, path):
        full, stat = super().lookup_path(path)
        if stat is not None:
            return full, stat
        requoted = "/".join(urllib.parse.quote(seg) for seg in path.split("/"))
        if requoted != path:
            return super().lookup_path(requoted)
        return full, stat


app.mount("/static", _MirrorStaticFiles(directory=str(STATIC_DIR)), name="static")


@app.middleware("http")
async def runtime_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    if BUILD_ID:
        response.headers["X-WebsiteBench-Build-Id"] = BUILD_ID
    return response


@app.get("/healthz", include_in_schema=False)
async def healthz() -> Response:
    return Response(content=_HEALTH_BODY, media_type="application/json")


_FAVICON = STATIC_DIR / "site" / "favicon.ico"


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    if _FAVICON.is_file():
        return Response(content=_FAVICON.read_bytes(), media_type="image/x-icon")
    return Response(status_code=204)


@app.post("/__admin/reset", include_in_schema=False)
async def admin_reset(request: Request) -> Response:
    token = request.headers.get("X-WebsiteBench-Admin-Token", "")
    if not hmac.compare_digest(token, ADMIN_TOKEN):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    from backend import catalog_db as _db
    _db.reset()
    return JSONResponse({"reset": True, "site_id": SITE_ID})


@app.get("/external/{slug}", include_in_schema=False)
async def external_boundary(slug: str) -> HTMLResponse:
    return HTMLResponse(_EXTERNAL_TEMPLATE.format(slug=html.escape(slug[:80])))


# ---------------------------------------------------------------------------
# JSON API — catalog / cart / checkout / orders / lists
# ---------------------------------------------------------------------------
import secrets  # noqa: E402

from backend import catalog_db as db  # noqa: E402

CART_COOKIE = "hd_cart"


def _cart_token(request: Request) -> tuple[str, bool]:
    tok = request.cookies.get(CART_COOKIE)
    if tok and 8 <= len(tok) <= 120:
        return tok, False
    return "guest-" + secrets.token_urlsafe(18), True


def _with_cart_cookie(payload: dict, token: str, is_new: bool) -> JSONResponse:
    resp = JSONResponse(payload)
    if is_new:
        resp.set_cookie(CART_COOKIE, token, max_age=86400, httponly=True,
                        samesite="lax", path="/")
    return resp


# Account session cookie: the library auth store owns the token; the cookie
# name and Host-only attributes come from backend/runtime.json so local and
# deployed behaviour stay identical (the __Host- prefix requires Secure + "/").
def _session_cookie_cfg() -> dict:
    backend, _ = db.services()
    return dict(backend.session_cookie)


def _session_token(request: Request) -> str | None:
    return request.cookies.get(_session_cookie_cfg()["name"])


def _set_session_cookie(resp: Response, token: str) -> None:
    cfg = _session_cookie_cfg()
    resp.set_cookie(
        cfg["name"], token, max_age=86400,
        httponly=bool(cfg.get("httponly", True)),
        samesite=str(cfg.get("samesite", "Lax")).lower(),
        secure=bool(cfg.get("secure", True)),
        path=str(cfg.get("path", "/")),
    )


def _clear_session_cookie(resp: Response) -> None:
    cfg = _session_cookie_cfg()
    resp.delete_cookie(
        cfg["name"], path=str(cfg.get("path", "/")),
        httponly=bool(cfg.get("httponly", True)),
        samesite=str(cfg.get("samesite", "Lax")).lower(),
        secure=bool(cfg.get("secure", True)),
    )


@app.get("/api/search", include_in_schema=False)
async def api_search(q: str = "", sort: str = "default",
                     offset: int = 0, limit: int = 24, brands: str = "",
                     price_max: float | None = None,
                     min_rating: float | None = None) -> Response:
    brand_list = [b for b in brands.split(",") if b.strip()]
    return JSONResponse(db.search_products(
        q, sort=sort, offset=offset, limit=limit, brands=brand_list,
        price_max=price_max, min_rating=min_rating))


@app.get("/api/products/{item_id}/related", include_in_schema=False)
async def api_product_related(item_id: str) -> Response:
    return JSONResponse(db.related_products(item_id))


@app.get("/api/products/{item_id}", include_in_schema=False)
async def api_product(item_id: str) -> Response:
    p = db.get_product(item_id)
    if p is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(p)


@app.get("/api/category", include_in_schema=False)
async def api_category(name: str, offset: int = 0, limit: int = 24) -> Response:
    return JSONResponse(db.products_by_category(name, offset=offset, limit=limit))


@app.get("/api/cart", include_in_schema=False)
async def api_cart(request: Request) -> Response:
    tok, is_new = _cart_token(request)
    return _with_cart_cookie(db.get_cart(tok), tok, is_new)


@app.post("/api/cart/add", include_in_schema=False)
async def api_cart_add(request: Request) -> Response:
    tok, is_new = _cart_token(request)
    body = await request.json()
    try:
        view = db.add_to_cart(tok, str(body.get("itemId", "")),
                              int(body.get("qty", 1)))
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return _with_cart_cookie({"ok": True, "cart": view}, tok, is_new)


@app.post("/api/cart/update", include_in_schema=False)
async def api_cart_update(request: Request) -> Response:
    tok, is_new = _cart_token(request)
    body = await request.json()
    view = db.update_cart_item(tok, str(body.get("itemId", "")),
                               int(body.get("qty", 0)))
    return _with_cart_cookie({"ok": True, "cart": view}, tok, is_new)


@app.post("/api/cart/remove", include_in_schema=False)
async def api_cart_remove(request: Request) -> Response:
    tok, is_new = _cart_token(request)
    body = await request.json()
    view = db.remove_cart_item(tok, str(body.get("itemId", "")))
    return _with_cart_cookie({"ok": True, "cart": view}, tok, is_new)


@app.get("/api/stores", include_in_schema=False)
async def api_stores() -> Response:
    return JSONResponse({"stores": db.list_stores()})


@app.post("/api/cart/store", include_in_schema=False)
async def api_cart_store(request: Request) -> Response:
    tok, is_new = _cart_token(request)
    body = await request.json()
    try:
        view = db.set_cart_store(tok, str(body.get("store_id", "")))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return _with_cart_cookie({"ok": True, "cart": view}, tok, is_new)


@app.post("/api/checkout", include_in_schema=False)
async def api_checkout(request: Request) -> Response:
    tok, is_new = _cart_token(request)
    body = await request.json()
    try:
        db.reject_payment_keys(body)  # fail closed on any card/credential field
    except db.PaymentFieldRejected:
        return JSONResponse({"error": "payment fields are not accepted"},
                            status_code=400)
    person = {
        "first_name": str(body.get("first_name", "")),
        "last_name": str(body.get("last_name", "")),
        "phone": str(body.get("phone", "")),
    }
    scenario = str(body.get("scenario_id", "sandbox-approved"))
    fulfillment = str(body.get("fulfillment", "pickup"))
    # Key is "gift_code" (not *card*) so the payment-key guard stays strict.
    gift = str(body.get("gift_code") or "") or None
    try:
        result = db.place_order(tok, person, scenario, fulfillment=fulfillment,
                                gift_card=gift)
    except db.PaymentFieldRejected:
        return JSONResponse({"error": "payment fields are not accepted"},
                            status_code=400)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return _with_cart_cookie(result, tok, is_new)


@app.get("/api/giftcard/check", include_in_schema=False)
async def api_giftcard_check(code: str = "") -> Response:
    return JSONResponse(db.check_gift_card(code))


@app.get("/api/orders", include_in_schema=False)
async def api_orders() -> Response:
    return JSONResponse({"orders": db.list_orders()})


@app.get("/api/order/{order_number}", include_in_schema=False)
async def api_order(order_number: str) -> Response:
    o = db.get_order(order_number)
    if o is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(o)


@app.post("/api/order/{order_number}/cancel", include_in_schema=False)
async def api_order_cancel(order_number: str) -> Response:
    try:
        return JSONResponse({"ok": True, "order": db.cancel_order(order_number)})
    except db.OrderActionError as exc:
        return JSONResponse({"error": str(exc)}, status_code=exc.status)


@app.post("/api/order/{order_number}/return", include_in_schema=False)
async def api_order_return(order_number: str) -> Response:
    try:
        return JSONResponse({"ok": True, "order": db.request_return(order_number)})
    except db.OrderActionError as exc:
        return JSONResponse({"error": str(exc)}, status_code=exc.status)


@app.post("/api/order/{order_number}/reorder", include_in_schema=False)
async def api_order_reorder(order_number: str, request: Request) -> Response:
    tok, is_new = _cart_token(request)
    try:
        cart = db.reorder(tok, order_number)
    except db.OrderActionError as exc:
        return JSONResponse({"error": str(exc)}, status_code=exc.status)
    return _with_cart_cookie({"ok": True, "cart": cart}, tok, is_new)


@app.get("/api/lists", include_in_schema=False)
async def api_lists() -> Response:
    return JSONResponse({"lists": db.get_lists()})


@app.post("/api/lists/add", include_in_schema=False)
async def api_lists_add(request: Request) -> Response:
    body = await request.json()
    try:
        result = db.add_to_list(str(body.get("itemId", "")),
                                str(body.get("list") or "My List"))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(result)


# --- account / session ---------------------------------------------------
@app.get("/api/account", include_in_schema=False)
async def api_account(request: Request) -> Response:
    tok, session = db.ensure_session(_session_token(request))
    resp = JSONResponse(session)
    _set_session_cookie(resp, tok)
    return resp


@app.post("/api/account/login", include_in_schema=False)
async def api_account_login(request: Request) -> Response:
    body = await request.json()
    email = str(body.get("email", "")).strip()
    password = str(body.get("password", ""))
    errors: dict[str, str] = {}
    if not email:
        errors["email"] = "Please enter your email address."
    if not password:
        errors["password"] = "Please enter your password."
    if errors:
        return JSONResponse({"errors": errors}, status_code=422)
    try:
        result = db.login(_session_token(request), email, password)
    except db.LoginInvalid:
        return JSONResponse(
            {"errors": {"password": "Please check your entries and try again."}},
            status_code=422,
        )
    except db.LoginRejected:
        return JSONResponse(
            {"error": "That email and password combination doesn't match our records."},
            status_code=401,
        )
    resp = JSONResponse({"authenticated": True, "account": result["account"]})
    _set_session_cookie(resp, result["session_token"])
    return resp


@app.post("/api/account/logout", include_in_schema=False)
async def api_account_logout(request: Request) -> Response:
    db.logout(_session_token(request))
    resp = JSONResponse({"authenticated": False, "account": None})
    _clear_session_cookie(resp)
    return resp


@app.post("/api/account/register/start", include_in_schema=False)
async def api_register_start(request: Request) -> Response:
    body = await request.json()
    email = str(body.get("email", "")).strip()
    first = str(body.get("first_name", "")).strip()
    last = str(body.get("last_name", "")).strip()
    display = (str(body.get("display_name", "")).strip()
               or f"{first} {last}".strip())
    password = str(body.get("password", ""))
    errors: dict[str, str] = {}
    if not email:
        errors["email"] = "Please enter your email address."
    if not display:
        errors["first_name"] = "Please enter your name."
    if not password:
        errors["password"] = "Please create a password."
    if errors:
        return JSONResponse({"errors": errors}, status_code=422)
    try:
        result = db.register_start(_session_token(request), email, display, password)
    except db.AuthFlowError as exc:
        return JSONResponse({"error": str(exc), "code": exc.code}, status_code=exc.status)
    resp = JSONResponse({"accepted": True, "sandbox_code": result.get("sandbox_code")})
    _set_session_cookie(resp, result["session_token"])
    return resp


@app.post("/api/account/register/complete", include_in_schema=False)
async def api_register_complete(request: Request) -> Response:
    body = await request.json()
    code = str(body.get("code", "")).strip()
    if not code:
        return JSONResponse({"errors": {"code": "Enter the verification code."}},
                            status_code=422)
    try:
        result = db.register_complete(_session_token(request), code)
    except db.AuthFlowError as exc:
        return JSONResponse({"error": str(exc), "code": exc.code}, status_code=exc.status)
    resp = JSONResponse({"authenticated": True, "account": result["account"]})
    _set_session_cookie(resp, result["session_token"])
    return resp


@app.post("/api/account/password-reset/start", include_in_schema=False)
async def api_password_reset_start(request: Request) -> Response:
    body = await request.json()
    email = str(body.get("email", "")).strip()
    if not email:
        return JSONResponse({"errors": {"email": "Please enter your email address."}},
                            status_code=422)
    try:
        result = db.password_reset_start(_session_token(request), email)
    except db.AuthFlowError as exc:
        return JSONResponse({"error": str(exc), "code": exc.code}, status_code=exc.status)
    resp = JSONResponse({"accepted": True, "sandbox_code": result.get("sandbox_code")})
    _set_session_cookie(resp, result["session_token"])
    return resp


@app.post("/api/account/password-reset/complete", include_in_schema=False)
async def api_password_reset_complete(request: Request) -> Response:
    body = await request.json()
    code = str(body.get("code", "")).strip()
    new_password = str(body.get("new_password", ""))
    errors: dict[str, str] = {}
    if not code:
        errors["code"] = "Enter the verification code."
    if not new_password:
        errors["new_password"] = "Create a new password."
    if errors:
        return JSONResponse({"errors": errors}, status_code=422)
    try:
        new_token = db.password_reset_complete(_session_token(request), code, new_password)
    except db.AuthFlowError as exc:
        return JSONResponse({"error": str(exc), "code": exc.code}, status_code=exc.status)
    resp = JSONResponse({"authenticated": True})
    _set_session_cookie(resp, new_token)
    return resp


def _resolve_page(route: str, query: str) -> str | None:
    """Map a source route (+query) to a frozen page fixture name."""
    exact = PAGE_ROUTES.get(route) or PAGE_ROUTES.get(route.rstrip("/") or "/")
    if exact:
        return exact
    if route.startswith("/b/"):
        m = _NCODE_RE.search(route)
        if m and m.group(1) in PLP_BY_NCODE:
            return PLP_BY_NCODE[m.group(1)]
    if route.startswith("/p/"):
        m = _ITEMID_RE.search(route)
        if m and m.group(1) in PDP_BY_ITEMID:
            return PDP_BY_ITEMID[m.group(1)]
    if route.startswith("/s/"):
        term = urllib.parse.unquote(route[3:]).lower()
        if "zzzz-no-match" in term or "zzzz" in term:
            return "search-no-results"
        return "search-results"
    # Account + saved-lists surfaces render on the home shell (complete header
    # CSS bundle); hd-app.js paints the live account panel over it.
    if route.startswith("/myaccount") or route.startswith("/list/"):
        return "home"
    return None


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_page(full_path: str, request: Request) -> Response:
    route = "/" + full_path
    name = _resolve_page(route, request.url.query)
    if name:
        body = _load_page(name)
        if body is not None:
            return HTMLResponse(body)
    return _not_found_response()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8099")))
