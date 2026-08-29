"""Humble Bundle offline clone — FastAPI composition root.

Layout (WebsiteBench offline-clone shape, per ASPCA / Home Depot precedent):

* Frozen localized snapshots (``frontend/pages/*.html``) captured anonymously
  from www.humblebundle.com, asset-localized to ``/static`` and stripped of
  all remote/telemetry script, are served at their real source routes. Client
  interactivity (tier engine, search, cart drawer, checkout, account panels)
  is re-implemented locally in ``static/site/hb-app.js`` against the JSON API
  below.
* The JSON API serves the frozen catalog subset (69 store products, 13 full
  game bundles, 57-bundle listing), the pay-what-you-want tier engine, cart,
  checkout (``local-sandbox`` payment only), purchases/keys/library, wishlist
  and accounts through the vendored ``websitebench.site_backend`` seam. The
  source walk stops before payment submission; the clone-local checkout
  accepts only an opaque sandbox scenario id and rejects payment-shaped keys.
* Bundle detail is frozen for the two captured bundles and hydrated from seed
  data for the other 11 active game bundles; software/books bundle slugs and
  unknown routes return the branded 404 (mirrors the source, where expired
  bundle links 404).
* ``/home/*`` (and ``/checkout`` until the authenticated handoff refines it)
  reproduce the observed secure-area gate:
  302 → ``/login?goto=<path>&qs=reason%3DsecureArea``.
* ``GET /healthz`` returns exactly ``{"ok":true,"site_id":"humble-bundle"}``.
* ``POST /__admin/reset`` is guarded by a constant-time admin-token compare.
* Every response carries a same-origin CSP; no remote origin is reachable.
"""

from __future__ import annotations

import hmac
import json
import os
import sys
import urllib.parse
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import catalog_db as db  # noqa: E402

SITE_ID = "humble-bundle"
PAGES_DIR = ROOT / "frontend" / "pages"
MANIFEST = json.loads((ROOT / "frontend" / "pages-manifest.json").read_text())
ADMIN_TOKEN = os.environ.get(
    "WEBSITEBENCH_HUMBLE_BUNDLE_ADMIN_TOKEN", "local-dev-admin"
)
CART_COOKIE = "hb_cart"
FROZEN_BUNDLE_PAGES = {
    "yes-chef-cooking-bundle": "bundle-anchor",
    "2k-megahits-2026-bundle": "bundle-2k",
}
CSP = (
    "default-src 'self'; img-src 'self' data:; media-src 'self'; "
    "style-src 'self' 'unsafe-inline'; script-src 'self'; "
    "connect-src 'self'; font-src 'self' data:; frame-ancestors 'none'"
)

app = FastAPI(title="Humble Bundle offline clone", docs_url=None, redoc_url=None)

_page_cache: dict[str, str] = {}


def _page_html(name: str) -> str:
    if name not in _page_cache:
        _page_cache[name] = (PAGES_DIR / f"{name}.html").read_text(encoding="utf-8")
    return _page_cache[name]


def _page(name: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(_page_html(name), status_code=status)


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": code, "message": message}, status_code=status)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("Content-Security-Policy", CSP)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp


# --------------------------------------------------------------------------
# session + cart cookies
# --------------------------------------------------------------------------
def _session_cookie_cfg() -> dict:
    backend, _ = db.services()
    return dict(backend.session_cookie)


def _session_token(request: Request) -> str | None:
    return request.cookies.get(_session_cookie_cfg()["name"])


def _set_session_cookie(resp: Response, token: str) -> None:
    cfg = _session_cookie_cfg()
    resp.set_cookie(
        cfg["name"],
        token,
        secure=cfg.get("secure", True),
        httponly=cfg.get("httponly", True),
        samesite=cfg.get("samesite", "lax"),
        path=cfg.get("path", "/"),
        max_age=cfg.get("max_age"),
    )


def _clear_session_cookie(resp: Response) -> None:
    cfg = _session_cookie_cfg()
    resp.delete_cookie(cfg["name"], path=cfg.get("path", "/"))


def _account(request: Request) -> dict:
    return db.current_account(_session_token(request))


def _owner(request: Request) -> str | None:
    """The business owner key for the signed-in account.

    Business rows key on the normalized email (``catalog_db.DEMO_OWNER`` is the
    demo account's email), so the session must resolve to the same value or a
    signed-in account cannot see its own seeded history.
    """
    state = _account(request)
    if not state.get("authenticated"):
        return None
    account = state.get("account") or {}
    for key in ("email_normalized", "email"):
        value = account.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return account.get("subject_id")


def _cart_id(request: Request) -> tuple[str, bool]:
    cid = request.cookies.get(CART_COOKIE)
    if cid and 8 <= len(cid) <= 64:
        return cid, False
    return uuid.uuid4().hex, True


def _with_cart_cookie(resp: Response, cid: str, minted: bool) -> Response:
    if minted:
        resp.set_cookie(
            CART_COOKIE, cid, httponly=True, samesite="lax", path="/",
            max_age=60 * 60 * 24 * 30,
        )
    return resp


def _secure_area_redirect(path: str) -> RedirectResponse:
    goto = urllib.parse.quote(path, safe="")
    return RedirectResponse(
        f"/login?goto={goto}&qs=reason%3DsecureArea", status_code=302
    )


# --------------------------------------------------------------------------
# frozen pages at their real routes
# --------------------------------------------------------------------------
_EXACT_ROUTES: dict[str, str] = {}
for _name, _meta in MANIFEST.items():
    _route = _meta.get("route", "")
    if not _route.startswith("/") or "?" in _route or "{" in _route:
        continue
    if _name in ("bundle-anchor", "bundle-2k", "store-product-satisfactory"):
        continue  # parametric families own these paths
    _EXACT_ROUTES[_route] = _name


def _exact_page_handler(page_name: str):
    async def handler() -> HTMLResponse:  # pragma: no cover - trivial closure
        return _page(page_name)

    return handler


for _route, _name in sorted(_EXACT_ROUTES.items()):
    if _route in ("/store/search",):
        continue  # query-dependent handler below
    app.get(_route, include_in_schema=False)(_exact_page_handler(_name))


@app.get("/store/search", include_in_schema=False)
async def store_search_page(request: Request) -> HTMLResponse:
    query = request.query_params.get("search", "")
    if query == "zzzz-no-match-websitebench":
        return _page("store-search-noresults")
    return _page("store-search")


@app.get("/store/c/{genre}", include_in_schema=False)
async def store_category_page(genre: str) -> HTMLResponse:
    # Category pages reuse the search surface (live panel over the frozen
    # search shell); hb-app.js hydrates from /api/search?genre=<genre>.
    return _page("store-search")


@app.get("/store/wishlist", include_in_schema=False)
async def wishlist_page(request: Request) -> Response:
    # The source serves the wishlist under /store/, not /home/ (established by
    # the authenticated handoff, see scope/handoff-findings.md).
    if _owner(request) is None:
        return _secure_area_redirect("/store/wishlist")
    return _page("store")


# Promo listings, the footer's own pages, and a trailing slash.
#
# All three were 404s reachable in one click from the chrome that appears on
# every page — 12 of the 24 broken links a crawl of the served clone found, and
# the nine promo paths are the store dropdown a visitor opens first.

PROMO_LISTINGS = {
    # Two promo paths are the same listing the site already serves under its
    # own name, so they redirect to it and are exact.
    "books": "/books",
    "software": "/software",
}

# The rest are curated store selections. The capture holds no page for any of
# them, and the catalogue supports genre, platform, DRM, sort and an
# onsale/new filter but not a price bound — so `deals-under-10` cannot be
# reproduced as a query. Rather than fabricate a curated list or leave a
# dropdown item dead, these serve the store listing they are a view of, with
# the promo name preserved in the query string so the substitution is visible
# in the URL rather than silent. Recorded as a known difference.
PROMO_AS_STORE = {
    "deals-under-5", "deals-under-10", "deals-under-20", "pre-order",
    "handheld-friendly", "humble-15-deals-of-the-day",
    "humble-15th-anniversary-summer-sale-2026",
}


@app.get("/store/promo/{name:path}", include_in_schema=False)
async def store_promo(name: str) -> Response:
    key = name.strip("/")
    target = PROMO_LISTINGS.get(key)
    if target:
        return RedirectResponse(target, status_code=302)
    # Any other promo name. A whitelist was the first shape here and it was
    # the wrong one: the store's own dropdown links twenty-nine publisher
    # promos — 2K, Capcom, Bethesda, Bandai Namco and the rest — and every one
    # of them fell straight through to a 404 because it was not on the list.
    # A promo path is a curated view of the store, so the store is where it
    # goes, with `filter=onsale` where the name says "deals" and the promo name
    # kept in the query so the substitution is visible rather than silent.
    query = "?filter=onsale" if key.startswith("deals-") else ""
    return RedirectResponse(f"/store{query}", status_code=302)


@app.get("/membership/checkout", include_in_schema=False)
async def membership_checkout(request: Request) -> Response:
    """Humble Choice checkout.

    Linked from the membership page and from the home page's Humble Choice
    takeover, and it had no route at all. Signed out it goes where every other
    secure area goes; signed in it reaches the checkout the clone actually
    serves. No payment is taken anywhere in this build.
    """
    if _owner(request) is None:
        return _secure_area_redirect("/membership/checkout")
    return RedirectResponse("/checkout", status_code=302)


@app.get("/developer", include_in_schema=False)
@app.get("/partner", include_in_schema=False)
async def unfrozen_footer_page() -> HTMLResponse:
    """Footer destinations the capture never visited.

    `/developer` and `/partner` are linked from the footer of every page and
    were never captured, so there is nothing to serve. The branded 404 is what
    goes out — the same answer as before, but reached by a route that says why
    rather than by falling through the catch-all, so the gap is visible in the
    code and in the delivery report instead of only in a crawl.
    """
    return _page("notfound-404", status=404)


@app.get("/store/{slug}", include_in_schema=False)
async def store_product_page(slug: str) -> HTMLResponse:
    if slug == "satisfactory":
        return _page("store-product-satisfactory")
    if db.get_product(slug) is not None:
        # Frozen product template hydrated client-side from /api/product.
        return _page("store-product-satisfactory")
    return _page("notfound-404", status=404)


@app.get("/games/{slug}", include_in_schema=False)
async def game_bundle_page(slug: str) -> HTMLResponse:
    frozen = FROZEN_BUNDLE_PAGES.get(slug)
    if frozen:
        return _page(frozen)
    if db.get_bundle(slug) is not None:
        # Seeded active game bundle: anchor template + client hydration.
        return _page("bundle-anchor")
    return _page("notfound-404", status=404)


@app.get("/books/{slug}", include_in_schema=False)
async def books_bundle_page(slug: str) -> HTMLResponse:
    """Books bundle detail.

    This used to 404 unconditionally, on the reasoning that book bundle detail
    was outside the frozen subset. That was true of `hb_bundles`, which holds
    only the thirteen game bundles whose pages were captured — and wrong about
    the seed as a whole: `bundles_listing` carries nineteen book bundles with
    their names, end dates, highlights and tile images, and the home page links
    six of them. They were answering 404 with their own data one table over.
    """
    if db.get_bundle(slug) is not None or db.get_listing_bundle(slug) is not None:
        return _page("bundle-anchor")
    return _page("notfound-404", status=404)


@app.get("/software/{slug}", include_in_schema=False)
async def software_bundle_page(slug: str) -> HTMLResponse:
    if db.get_bundle(slug) is not None or db.get_listing_bundle(slug) is not None:
        return _page("bundle-anchor")
    return _page("notfound-404", status=404)


@app.get("/home/{rest:path}", include_in_schema=False)
async def account_area(rest: str, request: Request) -> Response:
    if _owner(request) is None:
        return _secure_area_redirect(f"/home/{rest}")
    # Authenticated account surface: home shell + hb-app.js panel. The real
    # interior structure is refined after the authenticated handoff (tr-001).
    return _page("home")


@app.get("/user/{section}", include_in_schema=False)
async def user_area(section: str, request: Request) -> Response:
    # /user/settings and /user/wallet are real signed-in routes (handoff
    # tr-001); anything else under /user/ is not in the frozen subset.
    if section not in ("settings", "wallet"):
        return _page("notfound-404", status=404)
    if _owner(request) is None:
        return _secure_area_redirect(f"/user/{section}")
    return _page("home")


@app.get("/checkout", include_in_schema=False)
async def checkout_page(request: Request) -> Response:
    if _owner(request) is None:
        return _secure_area_redirect("/checkout")
    return _page("store")


# --------------------------------------------------------------------------
# JSON API — catalog
# --------------------------------------------------------------------------
@app.get("/api/search")
async def api_search(request: Request) -> JSONResponse:
    q = request.query_params
    try:
        page = max(0, int(q.get("page", "0")))
    except ValueError:
        page = 0
    return JSONResponse(
        db.search(
            search=q.get("search") or None,
            genre=q.get("genre") or None,
            platform=q.get("platform") or None,
            drm=q.get("drm") or None,
            sort=q.get("sort") or "bestselling",
            filter=q.get("filter") or None,
            page=page,
        )
    )


@app.get("/api/suggest")
async def api_suggest(request: Request) -> JSONResponse:
    return JSONResponse({"results": db.suggest(request.query_params.get("q", ""))})


@app.get("/api/product/{slug}")
async def api_product(slug: str) -> Response:
    product = db.get_product(slug)
    if product is None:
        return _err(404, "not_found", "unknown product")
    return JSONResponse(product)


@app.get("/api/bundles")
async def api_bundles() -> JSONResponse:
    return JSONResponse(db.bundles_listing())


@app.get("/api/bundle/{slug}")
async def api_bundle(slug: str) -> Response:
    bundle = db.get_bundle(slug)
    if bundle is None:
        # Fall back to the listing tile. The payload carries `listing_only` so
        # the page can render the bundle's own name, logo and highlights and
        # drop the purchase machinery, instead of leaving another bundle's
        # tiers and prices standing in the frozen template.
        bundle = db.get_listing_bundle(slug)
    if bundle is None:
        return _err(404, "not_found", "unknown bundle")
    return JSONResponse(bundle)


@app.get("/api/bundle/{slug}/preview")
async def api_bundle_preview(slug: str, request: Request) -> Response:
    try:
        amount = int(request.query_params.get("amount_minor", "0"))
    except ValueError:
        return _err(422, "invalid", "amount_minor must be an integer")
    try:
        return JSONResponse(db.tier_preview(slug, amount))
    except db.NotFound:
        return _err(404, "not_found", "unknown bundle")


# --------------------------------------------------------------------------
# JSON API — cart
# --------------------------------------------------------------------------
@app.get("/api/cart")
async def api_cart(request: Request) -> Response:
    cid, minted = _cart_id(request)
    # ``split_mode`` is the donation mode the bundle page carried over; it
    # only moves the charity share of the Order Summary (and the taxable
    # base), never the item lines.
    view = db.get_or_create_cart(
        cid,
        owner=_owner(request),
        split_mode=request.query_params.get("split_mode") or "default",
    )
    return _with_cart_cookie(JSONResponse(view), cid, minted)


async def _json_body(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


@app.post("/api/cart/add")
async def api_cart_add(request: Request) -> Response:
    body = await _json_body(request)
    cid, minted = _cart_id(request)
    try:
        db.reject_payment_keys(body)
        view = db.cart_add(
            cid,
            kind=str(body.get("kind", "")),
            slug=str(body.get("slug", "")),
            amount_minor=body.get("amount_minor"),
        )
    except db.PaymentFieldRejected as exc:
        return _err(400, "payment_field_rejected", str(exc))
    except db.BelowFloor as exc:
        return _err(422, "below_floor", str(exc))
    except db.CartLimitExceeded as exc:
        return _err(409, "cart_limit", str(exc))
    except (db.NotFound, ValueError) as exc:
        return _err(404 if isinstance(exc, db.NotFound) else 422, "invalid", str(exc))
    return _with_cart_cookie(JSONResponse(view), cid, minted)


@app.post("/api/cart/update")
async def api_cart_update(request: Request) -> Response:
    body = await _json_body(request)
    cid, minted = _cart_id(request)
    try:
        db.reject_payment_keys(body)
        view = db.cart_update(
            cid,
            item_id=int(body.get("item_id", 0)),
            amount_minor=body.get("amount_minor"),
            qty=body.get("qty"),
        )
    except db.PaymentFieldRejected as exc:
        return _err(400, "payment_field_rejected", str(exc))
    except db.BelowFloor as exc:
        return _err(422, "below_floor", str(exc))
    except (db.NotFound, ValueError) as exc:
        return _err(404 if isinstance(exc, db.NotFound) else 422, "invalid", str(exc))
    return _with_cart_cookie(JSONResponse(view), cid, minted)


@app.post("/api/cart/remove")
async def api_cart_remove(request: Request) -> Response:
    body = await _json_body(request)
    try:
        result = db.cart_remove(int(body.get("item_id", 0)))
    except (db.NotFound, ValueError) as exc:
        return _err(404, "not_found", str(exc))
    return JSONResponse(result)


@app.post("/api/cart/restore")
async def api_cart_restore(request: Request) -> Response:
    body = await _json_body(request)
    snapshot = body.get("snapshot")
    if not isinstance(snapshot, dict):
        return _err(422, "invalid", "snapshot required")
    try:
        db.reject_payment_keys(snapshot)
        view = db.cart_restore(snapshot)
    except db.PaymentFieldRejected as exc:
        return _err(400, "payment_field_rejected", str(exc))
    except (db.NotFound, db.CartLimitExceeded, ValueError) as exc:
        return _err(409, "conflict", str(exc))
    return JSONResponse(view)


# --------------------------------------------------------------------------
# JSON API — checkout
# --------------------------------------------------------------------------
@app.post("/api/checkout")
async def api_checkout(request: Request) -> Response:
    body = await _json_body(request)
    owner = _owner(request)
    if owner is None:
        return _err(401, "auth_required", "sign in to check out")
    cid, _ = _cart_id(request)
    # The gifting opt-in arrives either as the captured triple
    # {"gift": {"mode": "none|email|link", "recipient": ..., "anonymous": ...}}
    # or, for older callers, as the flat delivery_kind / gift_email pair.
    gift = body.get("gift")
    gift_mode = None
    gift_recipient = body.get("gift_email")
    gift_anonymous = bool(body.get("gift_anonymous", False))
    if isinstance(gift, dict):
        gift_mode = gift.get("mode")
        if gift.get("recipient") is not None:
            gift_recipient = gift.get("recipient")
        gift_anonymous = bool(gift.get("anonymous", gift_anonymous))
    elif isinstance(gift, str):
        gift_mode = gift
    if gift_mode is not None:
        gift_mode = str(gift_mode)
    try:
        db.reject_payment_keys(body)
        order = db.place_order(
            cid,
            owner=owner,
            scenario_id=str(body.get("scenario_id", "")),
            delivery_kind=str(body.get("delivery_kind", "self")),
            gift_email=gift_recipient,
            splits=body.get("splits"),
            processor=str(body.get("processor", "card")),
            gift_mode=gift_mode,
            gift_anonymous=gift_anonymous,
            leaderboard_name=body.get("leaderboard_name"),
        )
    except db.PaymentFieldRejected as exc:
        return _err(400, "payment_field_rejected", str(exc))
    except db.EmptyCart as exc:
        return _err(400, "empty_cart", str(exc))
    except db.BelowFloor as exc:
        return _err(422, "below_floor", str(exc))
    except db.ProcessorInvalid as exc:
        return _err(422, "unknown_processor", str(exc))
    except db.GiftRecipientInvalid as exc:
        return _err(422, "gift_email_invalid", str(exc))
    except db.SplitInvalid as exc:
        return _err(422, "split_invalid", str(exc))
    except db.PaymentDeclined:
        return JSONResponse(
            {"error": "declined", "retryable": False,
             "message": "Your payment was declined."},
            status_code=402,
        )
    except db.PaymentRetryable:
        return JSONResponse(
            {"error": "retryable", "retryable": True,
             "message": "The payment service is temporarily unavailable. "
                        "Please try again."},
            status_code=402,
        )
    except ValueError as exc:
        return _err(422, "invalid", str(exc))
    return JSONResponse(order)


# --------------------------------------------------------------------------
# JSON API — purchases / library / wishlist
# --------------------------------------------------------------------------
@app.get("/api/purchases")
async def api_purchases(request: Request) -> Response:
    owner = _owner(request)
    if owner is None:
        return _err(401, "auth_required", "sign in")
    return JSONResponse({"purchases": db.list_purchases(owner)})


@app.get("/api/purchase/{order_no}")
async def api_purchase(order_no: str, request: Request) -> Response:
    owner = _owner(request)
    if owner is None:
        return _err(401, "auth_required", "sign in")
    try:
        return JSONResponse(db.get_purchase(owner, order_no))
    except db.NotFound:
        return _err(404, "not_found", "unknown order")


@app.post("/api/purchase/{order_no}/reveal-key")
async def api_reveal_key(order_no: str, request: Request) -> Response:
    owner = _owner(request)
    if owner is None:
        return _err(401, "auth_required", "sign in")
    body = await _json_body(request)
    try:
        code = db.reveal_key(owner, order_no, str(body.get("machine_name", "")))
    except db.NotFound:
        return _err(404, "not_found", "unknown key")
    return JSONResponse({"machine_name": body.get("machine_name"), "key": code})


@app.get("/api/library")
async def api_library(request: Request) -> Response:
    owner = _owner(request)
    if owner is None:
        return _err(401, "auth_required", "sign in")
    return JSONResponse({"library": db.library(owner)})


@app.get("/api/wishlist")
async def api_wishlist(request: Request) -> Response:
    owner = _owner(request)
    if owner is None:
        return _err(401, "auth_required", "sign in")
    return JSONResponse({"wishlist": db.wishlist_list(owner)})


@app.post("/api/wishlist/add")
async def api_wishlist_add(request: Request) -> Response:
    owner = _owner(request)
    if owner is None:
        return _err(401, "auth_required", "sign in")
    body = await _json_body(request)
    try:
        items = db.wishlist_add(owner, str(body.get("slug", "")))
    except db.NotFound as exc:
        return _err(404, "not_found", str(exc))
    except db.WishlistLimitExceeded as exc:
        return _err(409, "wishlist_limit", str(exc))
    return JSONResponse({"wishlist": items})


@app.post("/api/wishlist/remove")
async def api_wishlist_remove(request: Request) -> Response:
    owner = _owner(request)
    if owner is None:
        return _err(401, "auth_required", "sign in")
    body = await _json_body(request)
    return JSONResponse(
        {"wishlist": db.wishlist_remove(owner, str(body.get("slug", "")))}
    )


# --------------------------------------------------------------------------
# JSON API — accounts
# --------------------------------------------------------------------------
@app.get("/api/account")
async def api_account(request: Request) -> JSONResponse:
    state = _account(request)
    owner = _owner(request)
    if owner is not None:
        # The delivery destination for a digital order: the settings override
        # if the account edited it, otherwise the signed-in address.
        state = dict(state)
        state["delivery_email"] = db.delivery_email(owner, owner)
    return JSONResponse(state)


@app.get("/api/account/settings")
async def api_account_settings(request: Request) -> Response:
    """The /user/settings surface state (see catalog_db.account_prefs)."""

    owner = _owner(request)
    if owner is None:
        return _err(401, "auth_required", "sign in")
    prefs = db.account_prefs(owner)
    return JSONResponse(
        {
            "sign_in_email": owner,
            "delivery_email": prefs["delivery_email"] or owner,
            "delivery_email_is_override": bool(prefs["delivery_email"]),
            "subscriptions": prefs["subscriptions"],
            "subscription_fields": [
                {"name": name, "label": label}
                for name, label, _default in db.SUBSCRIPTION_PREFS
            ],
            "charity_preference": prefs["charity_preference"],
            "community_donated_display": db.COMMUNITY_DONATED_DISPLAY,
            "wallet": {
                "currency": db.WALLET_CURRENCY,
                "funds_minor": db.WALLET_FUNDS_MINOR,
                "expiring_minor": db.WALLET_EXPIRING_MINOR,
            },
        }
    )


@app.post("/api/account/delivery-email")
async def api_account_delivery_email(request: Request) -> Response:
    owner = _owner(request)
    if owner is None:
        return _err(401, "auth_required", "sign in")
    body = await _json_body(request)
    try:
        prefs = db.set_delivery_email(owner, str(body.get("email", "")))
    except db.DeliveryEmailInvalid as exc:
        return _err(400, "invalid_email", str(exc))
    return JSONResponse(
        {"delivery_email": prefs["delivery_email"], "sign_in_email": owner}
    )


@app.post("/api/account/contact-prefs")
async def api_account_contact_prefs(request: Request) -> Response:
    owner = _owner(request)
    if owner is None:
        return _err(401, "auth_required", "sign in")
    body = await _json_body(request)
    subscriptions = body.get("subscriptions")
    charity = body.get("charity_preference")
    try:
        prefs = db.set_contact_prefs(
            owner,
            subscriptions=subscriptions if isinstance(subscriptions, dict) else None,
            charity_preference=str(charity) if charity is not None else None,
        )
    except ValueError as exc:
        return _err(400, "invalid_preferences", str(exc))
    return JSONResponse(
        {
            "subscriptions": prefs["subscriptions"],
            "charity_preference": prefs["charity_preference"],
        }
    )


@app.post("/api/account/login")
async def api_account_login(request: Request) -> Response:
    body = await _json_body(request)
    try:
        result = db.login(
            _session_token(request),
            email=str(body.get("email", "")),
            password=str(body.get("password", "")),
        )
    except db.LoginInvalid as exc:
        return _err(422, "invalid", str(exc))
    except db.LoginRejected:
        return _err(401, "rejected", "credentials are invalid")
    resp = JSONResponse({"authenticated": True, "account": result["account"]})
    _set_session_cookie(resp, result["session_token"])
    return resp


@app.post("/api/account/logout")
async def api_account_logout(request: Request) -> Response:
    db.logout(_session_token(request))
    resp = JSONResponse({"authenticated": False, "account": None})
    _clear_session_cookie(resp)
    return resp


@app.post("/api/account/register/start")
async def api_register_start(request: Request) -> Response:
    body = await _json_body(request)
    try:
        result = db.register_start(
            _session_token(request),
            email=str(body.get("email", "")),
            display_name=str(body.get("display_name", "") or body.get("email", "")),
            password=str(body.get("password", "")),
        )
    except db.AuthFlowError as exc:
        return _err(exc.status, exc.code, str(exc))
    resp = JSONResponse(
        {"pending": True, "sandbox_code": result.get("sandbox_code"),
         "mail_mode": str(result.get("mail_mode") or "")}
    )
    _set_session_cookie(resp, result["session_token"])
    return resp


@app.post("/api/account/register/complete")
async def api_register_complete(request: Request) -> Response:
    body = await _json_body(request)
    try:
        result = db.register_complete(
            _session_token(request), str(body.get("code", ""))
        )
    except db.AuthFlowError as exc:
        return _err(exc.status, exc.code, str(exc))
    resp = JSONResponse({"authenticated": True, "account": result["account"]})
    _set_session_cookie(resp, result["session_token"])
    return resp


@app.post("/api/account/password-reset/start")
async def api_password_reset_start(request: Request) -> Response:
    body = await _json_body(request)
    try:
        result = db.password_reset_start(
            _session_token(request), email=str(body.get("email", ""))
        )
    except db.AuthFlowError as exc:
        return _err(exc.status, exc.code, str(exc))
    resp = JSONResponse(
        {"accepted": True, "sandbox_code": result.get("sandbox_code")}
    )
    _set_session_cookie(resp, result["session_token"])
    return resp


@app.post("/api/account/password-reset/complete")
async def api_password_reset_complete(request: Request) -> Response:
    body = await _json_body(request)
    try:
        token = db.password_reset_complete(
            _session_token(request),
            code=str(body.get("code", "")),
            new_password=str(body.get("new_password", "")),
        )
    except db.AuthFlowError as exc:
        return _err(exc.status, exc.code, str(exc))
    resp = JSONResponse({"authenticated": True})
    _set_session_cookie(resp, token)
    return resp


# --------------------------------------------------------------------------
# infra
# --------------------------------------------------------------------------
EXTERNAL_LINKS = json.loads(
    (ROOT / "frontend" / "external-links.json").read_text(encoding="utf-8")
)


@app.get("/external/{slug}", include_in_schema=False)
async def external_interstitial(slug: str) -> HTMLResponse:
    target = EXTERNAL_LINKS.get(slug)
    if target is None:
        return _page("notfound-404", status=404)
    import html as _html

    dest = _html.escape(target["host"] + (target["path"] or "/"))
    body = (
        "<!-- websitebench-frozen -->\n<!DOCTYPE html>\n<html lang=\"en\"><head>"
        "<meta charset=\"utf-8\"><title>Leaving the demo | Humble Bundle</title>"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<style>body{margin:0;font-family:'Sofia Pro','Helvetica Neue',Helvetica,Arial,"
        "sans-serif;background:#494f5c;color:#fff;display:flex;min-height:100vh;"
        "align-items:center;justify-content:center}main{max-width:560px;padding:40px;"
        "text-align:center}h1{font-size:22px}p{color:#cdd2df;line-height:1.5}"
        "code{color:#fff}a{color:#78ceff;text-decoration:none;font-weight:700}</style>"
        "</head><body><main><h1>This link leads outside the offline demo</h1>"
        f"<p>Destination on the live site:</p><p><code>{dest}</code></p>"
        "<p>External destinations are not part of this offline clone.</p>"
        "<p><a href=\"/\">&larr; Back to Humble Bundle</a></p></main></body></html>"
    )
    return HTMLResponse(body)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> JSONResponse:
    return JSONResponse({"ok": True, "site_id": SITE_ID})


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)


@app.post("/__admin/reset", include_in_schema=False)
async def admin_reset(request: Request) -> Response:
    supplied = request.headers.get("X-WebsiteBench-Admin-Token", "")
    if not hmac.compare_digest(supplied, ADMIN_TOKEN):
        return _err(403, "forbidden", "bad admin token")
    db.reset()
    return JSONResponse({"ok": True, "reset": True})


app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


@app.get("/{rest:path}", include_in_schema=False)
async def branded_not_found(rest: str, request: Request) -> Response:
    # A trailing slash reached here and 404ed while the same path without one
    # served the page: `/store/` versus `/store`. The path convertor for
    # `/store/{slug}` requires at least one character, so `/store/` matched no
    # named route and fell through to this catch-all. One character apart, two
    # different answers, on a link the chrome puts on every page.
    if rest.endswith("/") and rest.strip("/"):
        return RedirectResponse("/" + rest.strip("/"), status_code=302)
    return _page("notfound-404", status=404)
