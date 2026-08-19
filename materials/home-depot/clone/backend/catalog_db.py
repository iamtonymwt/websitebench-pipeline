"""The Home Depot offline clone — catalog / cart / checkout / order persistence.

Owns the site business schema (products, stores, carts, cart_items, orders,
order_items, lists, list_items) on top of the vendored
``websitebench.site_backend`` runtime, which owns the library tables
(accounts / sessions / OTP / mail outbox / payment ledger) in the same bound
SQLite file (``home-depot.sqlite3``).

Determinism: quote/order numbers derive from row id; timestamps are pinned to
the frozen capture clock — no wall clock, no randomness — so identical
operation sequences yield identical state. :func:`reset` clears business rows
and library auth/payment state atomically.

Payment boundary: the source walk stopped before order submission. Checkout
adds a clearly labeled ``local-sandbox`` contract: the client submits one
opaque scenario id; amount, owner, currency and fingerprint are server-derived
from the cart. No card, credential or provider field is ever accepted or
stored.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from backend.site_backend_integration import open_site_services
from websitebench.local_clone_auth import (
    AuthError,
    AuthRateLimited,
    AuthRejected,
    AuthValidationError,
)

SITE_ID = "home-depot"
FROZEN_CLOCK_UTC = "2026-08-18T12:00:00Z"
ROOT = Path(__file__).resolve().parent
SEED_PATH = ROOT / "seed_data.json"

# Deterministic identity for the seeded demo account. The auth store owns the
# real credential material; this only names the fixture subject so the seed is
# idempotent and the same account survives every business reset.
DEMO_ACCOUNT_SUBJECT = "home-depot-demo-shopper"

# No payment-shaped key may enter a business insert path.
_PAYMENT_KEY_RE = re.compile(
    r"(card|cvv|cvc|cardnumber|card_number|pan|expir|security[-_]?code"
    r"|payment[-_]?(method|token)|stripe|bank|account[-_]?number|routing)",
    re.IGNORECASE,
)


class PaymentFieldRejected(ValueError):
    """A card/payment-like key reached a business insert path."""


def reject_payment_keys(payload: Any) -> None:
    if isinstance(payload, dict):
        for k, v in payload.items():
            if _PAYMENT_KEY_RE.search(str(k)):
                raise PaymentFieldRejected(f"payment-like key rejected: {k}")
            reject_payment_keys(v)


_MIGRATIONS: dict[str, str] = {
    "0001_catalog": """
        CREATE TABLE IF NOT EXISTS hd_products (
            item_id TEXT PRIMARY KEY,
            brand TEXT, model TEXT, label TEXT NOT NULL,
            price REAL NOT NULL, original REAL,
            rating REAL, reviews INTEGER DEFAULT 0,
            canonical_url TEXT, store_sku TEXT, thumb TEXT,
            images_json TEXT NOT NULL DEFAULT '[]',
            category TEXT, sort_order INTEGER NOT NULL DEFAULT 0,
            search_blob TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_hd_products_category ON hd_products(category);
        CREATE INDEX IF NOT EXISTS idx_hd_products_sort ON hd_products(sort_order);
        CREATE TABLE IF NOT EXISTS hd_stores (
            store_id TEXT PRIMARY KEY,
            name TEXT NOT NULL, address TEXT, city TEXT, state TEXT,
            zip TEXT, hours TEXT, pickup INTEGER NOT NULL DEFAULT 1
        );
    """,
    "0002_cart": """
        CREATE TABLE IF NOT EXISTS hd_carts (
            id INTEGER PRIMARY KEY,
            token TEXT NOT NULL UNIQUE,
            account_id INTEGER,
            store_id TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS hd_cart_items (
            id INTEGER PRIMARY KEY,
            cart_id INTEGER NOT NULL REFERENCES hd_carts(id) ON DELETE CASCADE,
            item_id TEXT NOT NULL REFERENCES hd_products(item_id),
            qty INTEGER NOT NULL DEFAULT 1 CHECK (qty >= 0),
            fulfillment TEXT NOT NULL DEFAULT 'pickup',
            UNIQUE (cart_id, item_id)
        );
        CREATE INDEX IF NOT EXISTS idx_hd_cart_items_cart ON hd_cart_items(cart_id);
    """,
    "0003_orders": """
        CREATE TABLE IF NOT EXISTS hd_orders (
            id INTEGER PRIMARY KEY,
            order_number TEXT NOT NULL UNIQUE,
            account_id INTEGER,
            store_id TEXT,
            fulfillment TEXT NOT NULL DEFAULT 'pickup',
            status TEXT NOT NULL DEFAULT 'Ready for Pickup',
            pickup_first TEXT, pickup_last TEXT, pickup_phone TEXT,
            subtotal_minor INTEGER NOT NULL,
            tax_minor INTEGER NOT NULL,
            total_minor INTEGER NOT NULL,
            gift_minor INTEGER NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'USD',
            payment_flow_id TEXT, payment_attempt_id TEXT,
            placed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS hd_order_items (
            id INTEGER PRIMARY KEY,
            order_id INTEGER NOT NULL REFERENCES hd_orders(id) ON DELETE CASCADE,
            item_id TEXT NOT NULL,
            label TEXT NOT NULL, model TEXT, thumb TEXT,
            qty INTEGER NOT NULL, unit_price_minor INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_hd_order_items_order ON hd_order_items(order_id);
    """,
    "0004_lists": """
        CREATE TABLE IF NOT EXISTS hd_lists (
            id INTEGER PRIMARY KEY,
            account_id INTEGER,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS hd_list_items (
            id INTEGER PRIMARY KEY,
            list_id INTEGER NOT NULL REFERENCES hd_lists(id) ON DELETE CASCADE,
            item_id TEXT NOT NULL REFERENCES hd_products(item_id),
            UNIQUE (list_id, item_id)
        );
    """,
    "0005_schema_log": """
        CREATE TABLE IF NOT EXISTS hd_schema_migrations (
            name TEXT PRIMARY KEY, applied_at TEXT NOT NULL
        );
    """,
}

TAX_RATE = 0.08  # NY pickup est. tax used in captured checkout ($399 -> $430.92)

# Sandbox gift cards (the official checkout offers "Apply Gift Card" as a
# payment tender). These synthetic codes are the gift-card analogue of the
# sandbox payment scenario ids: the order total is unchanged; the gift value
# reduces the amount charged through the payment sandbox.
GIFT_CARDS: dict[str, int] = {
    "SANDBOX-GIFT-25": 2500,
    "SANDBOX-GIFT-100": 10000,
}


def check_gift_card(code: str) -> dict[str, Any]:
    """Validate a sandbox gift-card code. Returns {valid, amount} (amount in $)."""
    c = (code or "").strip().upper()
    amt = GIFT_CARDS.get(c)
    if amt is None:
        return {"valid": False}
    return {"valid": True, "code": c, "amount": round(amt / 100, 2)}

_services_cache: tuple[Any, Any] | None = None


def services() -> tuple[Any, Any]:
    global _services_cache
    if _services_cache is None:
        _services_cache = open_site_services()
        _migrate(_services_cache[0])
        _seed_if_empty(_services_cache[0])
        _ensure_seed_account(_services_cache[1])
    return _services_cache


def _ensure_seed_account(auth: Any) -> None:
    """Idempotently bind the synthetic demo shopper to real auth credentials.

    The auth store keeps accounts in the library tables, which the business
    reset never touches, so one seed at open time keeps the fixture logged-in
    identity stable across resets. Values are fully synthetic (no real PII).
    """
    if auth is None:
        return
    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    acct = seed.get("demo_account")
    if not acct:
        return
    display = f"{acct.get('first_name', '')} {acct.get('last_name', '')}".strip()
    auth.seed_account(
        subject_id=DEMO_ACCOUNT_SUBJECT,
        email=acct["email"],
        display_name=display or acct["email"],
        password=acct["password"],
        email_verified=True,
    )


def _migrate(backend: Any) -> None:
    with backend.lifecycle.connection(transaction=True) as cx:
        for name, ddl in _MIGRATIONS.items():
            cx.executescript(ddl)
        # Column additions must be conditional (SQLite lacks ADD COLUMN IF NOT
        # EXISTS and the DDL above is re-run idempotently on every startup).
        cols = {r[1] for r in cx.execute("PRAGMA table_info(hd_orders)")}
        if "gift_minor" not in cols:
            cx.execute("ALTER TABLE hd_orders"
                       " ADD COLUMN gift_minor INTEGER NOT NULL DEFAULT 0")
        for name in _MIGRATIONS:
            cx.execute(
                "INSERT OR IGNORE INTO hd_schema_migrations (name, applied_at) VALUES (?, ?)",
                (name, FROZEN_CLOCK_UTC),
            )


def _seed_if_empty(backend: Any) -> None:
    with backend.lifecycle.connection(transaction=True) as cx:
        n = cx.execute("SELECT COUNT(*) FROM hd_products").fetchone()[0]
        if n:
            return
        seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        for st in seed["stores"]:
            cx.execute(
                "INSERT OR REPLACE INTO hd_stores"
                " (store_id,name,address,city,state,zip,hours,pickup)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (st["id"], st["name"], st.get("address"), st.get("city"),
                 st.get("state"), st.get("zip"), st.get("hours"),
                 1 if st.get("pickup", True) else 0),
            )
        for i, p in enumerate(seed["products"]):
            blob = " ".join(str(x) for x in
                            [p.get("brand"), p.get("model"), p.get("label"),
                             p.get("category")] if x).lower()
            cx.execute(
                "INSERT OR REPLACE INTO hd_products"
                " (item_id,brand,model,label,price,original,rating,reviews,"
                "  canonical_url,store_sku,thumb,images_json,category,sort_order,search_blob)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (p["item_id"] if "item_id" in p else p["itemId"], p.get("brand"),
                 p.get("model"), p["label"], p["price"], p.get("original"),
                 p.get("rating"), p.get("reviews", 0), p.get("canonicalUrl"),
                 p.get("storeSku"), p.get("thumb"),
                 json.dumps(p.get("images", [])), p.get("category"), i, blob),
            )
        # seed orders/lists (synthetic identity; account_id NULL = guest-visible)
        for od in seed.get("seed_orders", []):
            _insert_seed_order(cx, seed, od)
        for lst in seed.get("seed_lists", []):
            cx.execute("INSERT INTO hd_lists (account_id,name,created_at) VALUES (NULL,?,?)",
                       (lst["name"], FROZEN_CLOCK_UTC))
            list_id = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
            for it in lst.get("items", []):
                cx.execute("INSERT OR IGNORE INTO hd_list_items (list_id,item_id) VALUES (?,?)",
                           (list_id, it["itemId"]))


def _product_row(cx: sqlite3.Connection, item_id: str) -> sqlite3.Row | None:
    return cx.execute("SELECT * FROM hd_products WHERE item_id=?", (item_id,)).fetchone()


def _insert_seed_order(cx: sqlite3.Connection, seed: dict, od: dict) -> None:
    items = []
    subtotal = 0
    for it in od["items"]:
        pr = _product_row(cx, it["itemId"])
        if pr is None:
            continue
        unit = int(round(pr["price"] * 100))
        subtotal += unit * it["qty"]
        items.append((it["itemId"], pr["label"], pr["model"], pr["thumb"], it["qty"], unit))
    tax = int(round(subtotal * TAX_RATE))
    cx.execute(
        "INSERT OR IGNORE INTO hd_orders"
        " (order_number,account_id,store_id,fulfillment,status,subtotal_minor,"
        "  tax_minor,total_minor,currency,placed_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (od["order_number"], None, od.get("store"), od.get("fulfillment", "pickup"),
         od.get("status", "Ready for Pickup"), subtotal, tax, subtotal + tax,
         "USD", od.get("placed", FROZEN_CLOCK_UTC)),
    )
    oid = cx.execute("SELECT id FROM hd_orders WHERE order_number=?",
                     (od["order_number"],)).fetchone()[0]
    for item_id, label, model, thumb, qty, unit in items:
        cx.execute(
            "INSERT INTO hd_order_items"
            " (order_id,item_id,label,model,thumb,qty,unit_price_minor)"
            " VALUES (?,?,?,?,?,?,?)",
            (oid, item_id, label, model, thumb, qty, unit),
        )


def _restore_business_seed(cx: sqlite3.Connection, seed: dict) -> None:
    """Clear mutable business rows and restore the frozen seed orders/lists.

    Products/stores are static catalog seed and kept. ``cx`` operates on the one
    bound SQLite file, so this is called with the auth store's connection inside
    :meth:`reset_site_state` to keep the whole reset in a single transaction.
    """
    for t in ("hd_list_items", "hd_lists", "hd_order_items", "hd_orders",
              "hd_cart_items", "hd_carts"):
        cx.execute(f"DELETE FROM {t}")
    for od in seed.get("seed_orders", []):
        _insert_seed_order(cx, seed, od)
    for lst in seed.get("seed_lists", []):
        cx.execute("INSERT INTO hd_lists (account_id,name,created_at) VALUES (NULL,?,?)",
                   (lst["name"], FROZEN_CLOCK_UTC))
        list_id = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
        for it in lst.get("items", []):
            cx.execute("INSERT OR IGNORE INTO hd_list_items (list_id,item_id) VALUES (?,?)",
                       (list_id, it["itemId"]))


def _demo_seed_accounts(seed: dict) -> list[dict[str, Any]]:
    acct = seed.get("demo_account")
    if not acct:
        return []
    display = f"{acct.get('first_name', '')} {acct.get('last_name', '')}".strip()
    return [{
        "subject_id": DEMO_ACCOUNT_SUBJECT,
        "email": acct["email"],
        "display_name": display or acct["email"],
        "password": acct["password"],
        "email_verified": True,
    }]


def reset() -> None:
    """Deterministic full reset: business rows + all library auth state in one
    transaction, restoring the frozen seed orders/lists and the demo account
    (with its seed password, undoing any registration/password-reset a run made).
    """
    backend, auth = services()
    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    if auth is not None:
        auth.reset_site_state(
            site_reset=lambda cx: _restore_business_seed(cx, seed),
            seed_accounts=_demo_seed_accounts(seed),
        )
    else:  # pragma: no cover - auth store is always present in this clone
        with backend.lifecycle.connection(transaction=True) as cx:
            _restore_business_seed(cx, seed)


# --------------------------------------------------------------------------
# accounts / sessions (library auth seam)
# --------------------------------------------------------------------------
class LoginInvalid(ValueError):
    """Login input was malformed (missing / short email or password)."""


class LoginRejected(ValueError):
    """Credentials were syntactically valid but did not authenticate."""


def ensure_session(token: str | None) -> tuple[str, dict[str, Any]]:
    """Resolve or mint an anonymous session; returns (token, public_session)."""
    _, auth = services()
    return auth.ensure_session(token)


def current_account(token: str | None) -> dict[str, Any]:
    """Public session view ``{authenticated, account, ...}``; never raises."""
    _, auth = services()
    resolved = auth.resolve_session(token) if token else None
    if resolved is None:
        return {"authenticated": False, "account": None}
    return resolved


def login(token: str | None, email: str, password: str) -> dict[str, Any]:
    """Sign in against a live session; returns ``{session_token, account}``.

    The auth store rotates the session on success, so the returned
    ``session_token`` replaces the caller's cookie. Raises :class:`LoginInvalid`
    for malformed input and :class:`LoginRejected` for bad credentials or rate
    limiting, so the HTTP layer can map them to 422 / 401.
    """
    _, auth = services()
    session_token = token
    if not session_token or auth.resolve_session(session_token) is None:
        session_token = auth.create_anonymous_session()
    try:
        return auth.sign_in(session_token, email=email, password=password)
    except AuthValidationError as exc:
        raise LoginInvalid(str(exc)) from exc
    except AuthRateLimited as exc:
        raise LoginRejected(str(exc)) from exc
    except (AuthRejected, AuthError) as exc:
        raise LoginRejected("credentials are invalid") from exc


def logout(token: str | None) -> None:
    _, auth = services()
    auth.sign_out(token)


class AuthFlowError(ValueError):
    """An account-flow step failed; ``status`` is the HTTP code to surface."""

    def __init__(self, message: str, *, status: int = 400, code: str = "error") -> None:
        super().__init__(message)
        self.status = status
        self.code = code


def _live_session(auth: Any, token: str | None) -> str:
    if token and auth.resolve_session(token) is not None:
        return token
    return auth.create_anonymous_session()


def _sandbox_code(auth: Any, token: str, purpose: str) -> str | None:
    """The OTP for the offline outbox (LOCAL_ONLY) so the demo flow completes.

    In the deployed cloudflare-review profile mail is really sent and this is
    None; offline (local-outbox) the code is surfaced honestly as a sandbox aid.
    """
    mail = auth.local_mail_for_session(token, purpose=purpose)
    return mail.get("verification_code") if mail else None


def register_start(token: str | None, email: str, display_name: str,
                   password: str) -> dict[str, Any]:
    """Begin registration; returns ``{session_token, sandbox_code, mail_mode}``."""
    _, auth = services()
    st = _live_session(auth, token)
    try:
        auth.start_registration(st, email=email, display_name=display_name,
                                password=password, restart_invalid_flow=True)
    except AuthValidationError as exc:
        raise AuthFlowError(str(exc), status=422, code="invalid") from exc
    except AuthRateLimited as exc:
        raise AuthFlowError("Too many attempts. Please try again shortly.",
                            status=429, code="rate_limited") from exc
    except AuthError as exc:  # AuthConflict (email/authed) etc.
        raise AuthFlowError("An account with that email already exists.",
                            status=409, code="conflict") from exc
    return {"session_token": st, "sandbox_code": _sandbox_code(auth, st, "registration"),
            "mail_mode": getattr(auth, "mail_mode", None)}


def register_complete(token: str | None, code: str) -> dict[str, Any]:
    """Verify the OTP and create the account (logs in); returns sign_in shape."""
    _, auth = services()
    if not token:
        raise AuthFlowError("Your session expired. Please start over.",
                            status=400, code="no_session")
    try:
        auth.verify_registration_code(token, code)
        return auth.complete_registration(token)
    except AuthValidationError as exc:
        raise AuthFlowError(str(exc), status=422, code="invalid") from exc
    except AuthError as exc:  # AuthRejected / AuthExpired / AuthLocked / AuthConflict
        raise AuthFlowError("That verification code is incorrect or expired.",
                            status=400, code="bad_code") from exc


def password_reset_start(token: str | None, email: str) -> dict[str, Any]:
    """Begin password reset; returns ``{session_token, sandbox_code}``.

    The auth store returns a generic message regardless of account existence to
    avoid enumeration; the sandbox code is only present when a flow was created.
    """
    _, auth = services()
    st = _live_session(auth, token)
    try:
        auth.start_password_reset(st, email=email, restart_invalid_flow=True)
    except AuthValidationError as exc:
        raise AuthFlowError(str(exc), status=422, code="invalid") from exc
    except AuthRateLimited as exc:
        raise AuthFlowError("Too many attempts. Please try again shortly.",
                            status=429, code="rate_limited") from exc
    except AuthError:
        # Never reveal whether the email exists; treat as accepted.
        pass
    return {"session_token": st,
            "sandbox_code": _sandbox_code(auth, st, "password-reset")}


def password_reset_complete(token: str | None, code: str,
                            new_password: str) -> str:
    """Verify the OTP and set the new password (logs in); returns new token."""
    _, auth = services()
    if not token:
        raise AuthFlowError("Your session expired. Please start over.",
                            status=400, code="no_session")
    try:
        auth.verify_password_reset_code(token, code)
        return auth.complete_password_reset(token, new_password=new_password)
    except AuthValidationError as exc:
        raise AuthFlowError(str(exc), status=422, code="invalid") from exc
    except AuthError as exc:
        raise AuthFlowError("That verification code is incorrect or expired.",
                            status=400, code="bad_code") from exc


# --------------------------------------------------------------------------
# catalog API
# --------------------------------------------------------------------------
def _row_to_product(r: sqlite3.Row) -> dict[str, Any]:
    return {
        "itemId": r["item_id"], "brand": r["brand"], "model": r["model"],
        "label": r["label"], "price": r["price"], "original": r["original"],
        "rating": r["rating"], "reviews": r["reviews"],
        "canonicalUrl": r["canonical_url"], "thumb": r["thumb"],
        "images": json.loads(r["images_json"]), "category": r["category"],
    }


def _weighted_rating(r: sqlite3.Row) -> float:
    """Review-volume-weighted rating (Bayesian shrink toward the site mean).

    Retail "Top Rated" sorts weight by review count so a handful of 5-star
    reviews cannot outrank thousands. Calibrated against the frozen source
    walk: the highest-rated SKU for the anchor query is 3697-22
    (4.7664 / 3981 reviews), which raw-rating order would place below a
    4.875 / 8-review item that the official results did not rank above it.
    """
    rating = r["rating"] or 0.0
    votes = r["reviews"] or 0
    m, c = 50.0, 4.6  # prior weight and prior mean
    return (rating * votes + c * m) / (votes + m)


def _apply_sort(matched: list, sort: str) -> None:
    if sort == "top_rated":
        matched.sort(key=lambda r: (-_weighted_rating(r), -(r["reviews"] or 0)))
    elif sort == "price_low":
        matched.sort(key=lambda r: r["price"])
    elif sort == "price_high":
        matched.sort(key=lambda r: -r["price"])
    elif sort == "reviews":
        matched.sort(key=lambda r: -(r["reviews"] or 0))


def search_products(query: str, sort: str = "default", limit: int = 24,
                    offset: int = 0, brands: list[str] | None = None,
                    price_max: float | None = None,
                    min_rating: float | None = None) -> dict[str, Any]:
    backend, _ = services()
    terms = [t for t in re.split(r"\s+", (query or "").strip().lower()) if t]
    with backend.lifecycle.connection() as cx:
        rows = cx.execute("SELECT * FROM hd_products ORDER BY sort_order").fetchall()
    matched = [r for r in rows
               if not terms or all(t in r["search_blob"] for t in terms)]
    # Facets are computed over the keyword-matched set (pre-filter) so the
    # available brand/price choices don't vanish as the shopper narrows down.
    brand_counts: dict[str, int] = {}
    prices = []
    for r in matched:
        if r["brand"]:
            brand_counts[r["brand"]] = brand_counts.get(r["brand"], 0) + 1
        prices.append(r["price"])
    facets = {
        "brands": sorted(({"name": b, "count": c} for b, c in brand_counts.items()),
                         key=lambda x: (-x["count"], x["name"])),
        "price_min": round(min(prices), 2) if prices else 0,
        "price_max": round(max(prices), 2) if prices else 0,
    }
    want = {b for b in (brands or []) if b}
    if want:
        matched = [r for r in matched if r["brand"] in want]
    if price_max is not None:
        matched = [r for r in matched if r["price"] <= price_max]
    if min_rating is not None:
        matched = [r for r in matched if (r["rating"] or 0) >= min_rating]
    _apply_sort(matched, sort)
    total = len(matched)
    page = [_row_to_product(r) for r in matched[offset:offset + limit]]
    return {"query": query, "sort": sort, "total": total, "offset": offset,
            "limit": limit, "products": page, "facets": facets,
            "applied": {"brands": sorted(want), "price_max": price_max,
                        "min_rating": min_rating}}


def get_product(item_id: str) -> dict[str, Any] | None:
    backend, _ = services()
    with backend.lifecycle.connection() as cx:
        r = _product_row(cx, item_id)
    return _row_to_product(r) if r else None


def products_by_category(category: str, limit: int = 24, offset: int = 0) -> dict[str, Any]:
    backend, _ = services()
    with backend.lifecycle.connection() as cx:
        rows = cx.execute(
            "SELECT * FROM hd_products WHERE category=? ORDER BY sort_order LIMIT ? OFFSET ?",
            (category, limit, offset)).fetchall()
        total = cx.execute("SELECT COUNT(*) FROM hd_products WHERE category=?",
                           (category,)).fetchone()[0]
    return {"category": category, "total": total,
            "products": [_row_to_product(r) for r in rows]}


def related_products(item_id: str, limit: int = 8) -> dict[str, Any]:
    """Same-category alternatives to one product (excluding itself).

    Backs the PDP "Compare Similar Products" strip: a truthful set of real
    catalog SKUs the shopper can switch between (the anchor combo kit has no
    captured variant matrix, so related real products stand in for options).
    """
    backend, _ = services()
    with backend.lifecycle.connection() as cx:
        base = cx.execute("SELECT category FROM hd_products WHERE item_id=?",
                          (item_id,)).fetchone()
        if base is None:
            return {"itemId": item_id, "products": []}
        rows = cx.execute(
            "SELECT * FROM hd_products WHERE category=? AND item_id<>? "
            "ORDER BY (rating IS NULL), rating DESC, reviews DESC LIMIT ?",
            (base["category"], item_id, limit)).fetchall()
    return {"itemId": item_id, "category": base["category"],
            "products": [_row_to_product(r) for r in rows]}


# --------------------------------------------------------------------------
# cart API (guest, session-token based)
# --------------------------------------------------------------------------
def _get_or_create_cart(cx: sqlite3.Connection, token: str) -> sqlite3.Row:
    row = cx.execute("SELECT * FROM hd_carts WHERE token=?", (token,)).fetchone()
    if row is None:
        cx.execute("INSERT INTO hd_carts (token,store_id,created_at) VALUES (?,?,?)",
                   (token, "1287", FROZEN_CLOCK_UTC))
        row = cx.execute("SELECT * FROM hd_carts WHERE token=?", (token,)).fetchone()
    return row


def _cart_view(cx: sqlite3.Connection, cart_id: int, store_id: str) -> dict[str, Any]:
    items = cx.execute(
        "SELECT ci.item_id, ci.qty, ci.fulfillment, p.label, p.model, p.price,"
        "       p.thumb, p.brand FROM hd_cart_items ci"
        " JOIN hd_products p ON p.item_id=ci.item_id WHERE ci.cart_id=?"
        " ORDER BY ci.id", (cart_id,)).fetchall()
    lines, subtotal_minor, count = [], 0, 0
    for it in items:
        unit = int(round(it["price"] * 100))
        line = unit * it["qty"]
        subtotal_minor += line
        count += it["qty"]
        lines.append({"itemId": it["item_id"], "label": it["label"],
                      "model": it["model"], "brand": it["brand"],
                      "thumb": it["thumb"], "price": it["price"],
                      "qty": it["qty"], "fulfillment": it["fulfillment"],
                      "line_total": round(line / 100, 2)})
    tax_minor = int(round(subtotal_minor * TAX_RATE))
    st = cx.execute("SELECT * FROM hd_stores WHERE store_id=?", (store_id,)).fetchone()
    return {"items": lines, "count": count,
            "subtotal": round(subtotal_minor / 100, 2),
            "tax": round(tax_minor / 100, 2),
            "total": round((subtotal_minor + tax_minor) / 100, 2),
            "subtotal_minor": subtotal_minor, "tax_minor": tax_minor,
            "total_minor": subtotal_minor + tax_minor,
            "store": {"id": st["store_id"], "name": st["name"],
                      "address": st["address"], "city": st["city"],
                      "state": st["state"], "zip": st["zip"]} if st else None}


def get_cart(token: str) -> dict[str, Any]:
    backend, _ = services()
    with backend.lifecycle.connection() as cx:
        cart = _get_or_create_cart(cx, token)
        return _cart_view(cx, cart["id"], cart["store_id"])


def list_stores() -> list[dict[str, Any]]:
    backend, _ = services()
    with backend.lifecycle.connection() as cx:
        rows = cx.execute("SELECT * FROM hd_stores ORDER BY store_id").fetchall()
    return [{"id": r["store_id"], "name": r["name"], "address": r["address"],
             "city": r["city"], "state": r["state"], "zip": r["zip"]} for r in rows]


def set_cart_store(token: str, store_id: str) -> dict[str, Any]:
    """Change the pickup store bound to this cart (fulfillment.address, T12)."""
    backend, _ = services()
    with backend.lifecycle.connection(transaction=True) as cx:
        if cx.execute("SELECT 1 FROM hd_stores WHERE store_id=?", (store_id,)).fetchone() is None:
            raise ValueError("unknown store")
        cart = _get_or_create_cart(cx, token)
        cx.execute("UPDATE hd_carts SET store_id=? WHERE id=?", (store_id, cart["id"]))
        return _cart_view(cx, cart["id"], store_id)


def add_to_cart(token: str, item_id: str, qty: int = 1,
                fulfillment: str = "pickup") -> dict[str, Any]:
    qty = max(1, min(int(qty), 3))  # source cart shows "Limit 3 per order"
    backend, _ = services()
    with backend.lifecycle.connection(transaction=True) as cx:
        if _product_row(cx, item_id) is None:
            raise ValueError("unknown item")
        cart = _get_or_create_cart(cx, token)
        existing = cx.execute(
            "SELECT qty FROM hd_cart_items WHERE cart_id=? AND item_id=?",
            (cart["id"], item_id)).fetchone()
        if existing:
            newqty = min(existing["qty"] + qty, 3)
            cx.execute("UPDATE hd_cart_items SET qty=? WHERE cart_id=? AND item_id=?",
                       (newqty, cart["id"], item_id))
        else:
            cx.execute("INSERT INTO hd_cart_items (cart_id,item_id,qty,fulfillment)"
                       " VALUES (?,?,?,?)", (cart["id"], item_id, qty, fulfillment))
        return _cart_view(cx, cart["id"], cart["store_id"])


def update_cart_item(token: str, item_id: str, qty: int) -> dict[str, Any]:
    qty = int(qty)
    backend, _ = services()
    with backend.lifecycle.connection(transaction=True) as cx:
        cart = _get_or_create_cart(cx, token)
        if qty <= 0:
            cx.execute("DELETE FROM hd_cart_items WHERE cart_id=? AND item_id=?",
                       (cart["id"], item_id))
        else:
            cx.execute("UPDATE hd_cart_items SET qty=? WHERE cart_id=? AND item_id=?",
                       (min(qty, 3), cart["id"], item_id))
        return _cart_view(cx, cart["id"], cart["store_id"])


def remove_cart_item(token: str, item_id: str) -> dict[str, Any]:
    return update_cart_item(token, item_id, 0)


# --------------------------------------------------------------------------
# checkout API (local-sandbox payment) + orders
# --------------------------------------------------------------------------
def _order_number(order_id: int) -> str:
    return f"WD{90000000 + order_id}"


def place_order(token: str, pickup_person: dict[str, str],
                scenario_id: str, fulfillment: str = "pickup",
                gift_card: str | None = None) -> dict[str, Any] | None:
    """Attempt local-sandbox payment and atomically create one order."""
    reject_payment_keys(pickup_person)
    for f in ("first_name", "last_name", "phone"):
        if not (pickup_person.get(f) or "").strip():
            raise ValueError(f"pickup {f} is required")
    if not isinstance(scenario_id, str) or not scenario_id:
        raise ValueError("scenario_id is required")
    gift_minor = 0
    if gift_card:
        gc = check_gift_card(gift_card)
        if not gc["valid"]:
            raise ValueError("invalid gift card")
        gift_minor = GIFT_CARDS[gc["code"]]
    fulfillment = "delivery" if str(fulfillment).lower() == "delivery" else "pickup"
    order_status = "Ordered" if fulfillment == "delivery" else "Ready for Pickup"

    backend, _ = services()
    with backend.lifecycle.connection(transaction=True) as cx:
        cart = _get_or_create_cart(cx, token)
        view = _cart_view(cx, cart["id"], cart["store_id"])
        if not view["items"]:
            raise ValueError("cart is empty")
        # owner must match OWNER_RE (8-240 [A-Za-z0-9._:-]); hash the token so
        # any cart token yields a valid, stable owner identity.
        owner = "cart:" + hashlib.sha256(cart["token"].encode()).hexdigest()[:32]
        # The gift card is a payment tender: order totals are unchanged; the
        # gift value reduces the amount charged through the payment sandbox.
        # (Clamped so at least 1 cent still flows through the sandbox charge —
        # every catalog item exceeds the largest sandbox card, so in practice
        # the clamp never engages.)
        gift_minor = min(gift_minor, max(view["total_minor"] - 1, 0))
        amount_minor = view["total_minor"] - gift_minor
        currency = "USD"
        fingerprint = hashlib.sha256(
            json.dumps([(i["itemId"], i["qty"]) for i in view["items"]],
                       sort_keys=True).encode()).hexdigest()
        flow = backend.payments.create_intent(
            owner=owner, amount_minor=amount_minor, currency=currency,
            fingerprint=fingerprint,
            idempotency_key=f"hd.create:{cart['token']}:{fingerprint}",
            connection=cx)
        attempt = backend.payments.attempt(
            flow_id=flow["flow_id"], owner=owner, amount_minor=amount_minor,
            currency=currency, fingerprint=fingerprint, scenario_id=scenario_id,
            idempotency_key=f"hd.attempt:{cart['token']}:{fingerprint[:32]}:{scenario_id}",
            connection=cx)
        if attempt["status"] != "APPROVED":
            return {"placed": False, "payment": {"status": attempt["status"]}}
        consumed = backend.payments.consume_approval(
            cx, flow_id=flow["flow_id"], owner=owner, amount_minor=amount_minor,
            currency=currency, fingerprint=fingerprint)
        cx.execute(
            "INSERT INTO hd_orders (order_number,store_id,fulfillment,status,"
            " pickup_first,pickup_last,pickup_phone,subtotal_minor,tax_minor,"
            " total_minor,gift_minor,currency,payment_flow_id,payment_attempt_id,"
            " placed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("PENDING", cart["store_id"], fulfillment, order_status,
             pickup_person["first_name"], pickup_person["last_name"],
             pickup_person["phone"], view["subtotal_minor"], view["tax_minor"],
             view["total_minor"], gift_minor, currency, flow["flow_id"],
             consumed["attempt_id"], FROZEN_CLOCK_UTC))
        oid = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
        onum = _order_number(oid)
        cx.execute("UPDATE hd_orders SET order_number=? WHERE id=?", (onum, oid))
        for it in view["items"]:
            cx.execute(
                "INSERT INTO hd_order_items (order_id,item_id,label,model,thumb,"
                " qty,unit_price_minor) VALUES (?,?,?,?,?,?,?)",
                (oid, it["itemId"], it["label"], it["model"], it["thumb"],
                 it["qty"], int(round(it["price"] * 100))))
        cx.execute("DELETE FROM hd_cart_items WHERE cart_id=?", (cart["id"],))
        return {"placed": True, "order_number": onum,
                "order": get_order(onum, _cx=cx)}


def get_order(order_number: str, _cx: sqlite3.Connection | None = None) -> dict[str, Any] | None:
    def _run(cx):
        o = cx.execute("SELECT * FROM hd_orders WHERE order_number=?",
                       (order_number,)).fetchone()
        if o is None:
            return None
        items = cx.execute("SELECT * FROM hd_order_items WHERE order_id=?",
                           (o["id"],)).fetchall()
        st = cx.execute("SELECT * FROM hd_stores WHERE store_id=?",
                        (o["store_id"],)).fetchone()
        return {
            "order_number": o["order_number"], "status": o["status"],
            "fulfillment": o["fulfillment"], "placed_at": o["placed_at"],
            "pickup_person": {"first_name": o["pickup_first"],
                              "last_name": o["pickup_last"],
                              "phone": o["pickup_phone"]},
            "subtotal": round(o["subtotal_minor"] / 100, 2),
            "tax": round(o["tax_minor"] / 100, 2),
            "total": round(o["total_minor"] / 100, 2),
            "gift": round((o["gift_minor"] or 0) / 100, 2),
            "charged": round((o["total_minor"] - (o["gift_minor"] or 0)) / 100, 2),
            "store": {"id": st["store_id"], "name": st["name"],
                      "address": st["address"], "city": st["city"],
                      "state": st["state"], "zip": st["zip"]} if st else None,
            "items": [{"itemId": i["item_id"], "label": i["label"],
                       "model": i["model"], "thumb": i["thumb"], "qty": i["qty"],
                       "unit_price": round(i["unit_price_minor"] / 100, 2)}
                      for i in items]}
    if _cx is not None:
        return _run(_cx)
    backend, _ = services()
    with backend.lifecycle.connection() as cx:
        return _run(cx)


def list_orders() -> list[dict[str, Any]]:
    backend, _ = services()
    with backend.lifecycle.connection() as cx:
        rows = cx.execute("SELECT order_number FROM hd_orders ORDER BY id DESC").fetchall()
    return [get_order(r["order_number"]) for r in rows]


class OrderActionError(ValueError):
    """An order post-action was not allowed from the order's current status."""

    def __init__(self, message: str, *, status: int = 409) -> None:
        super().__init__(message)
        self.status = status


CANCELLABLE_STATUSES = {"Ready for Pickup", "Processing", "Ordered"}
RETURNABLE_STATUSES = {"Completed", "Picked Up"}


def _set_order_status(order_number: str, new_status: str,
                      allowed: set[str]) -> dict[str, Any]:
    backend, _ = services()
    with backend.lifecycle.connection(transaction=True) as cx:
        o = cx.execute("SELECT id,status FROM hd_orders WHERE order_number=?",
                       (order_number,)).fetchone()
        if o is None:
            raise OrderActionError("order not found", status=404)
        if o["status"] not in allowed:
            raise OrderActionError(
                f"This order can't be changed from '{o['status']}'.", status=409)
        cx.execute("UPDATE hd_orders SET status=? WHERE id=?", (new_status, o["id"]))
    return get_order(order_number)


def cancel_order(order_number: str) -> dict[str, Any]:
    return _set_order_status(order_number, "Cancelled", CANCELLABLE_STATUSES)


def request_return(order_number: str) -> dict[str, Any]:
    return _set_order_status(order_number, "Return Requested", RETURNABLE_STATUSES)


def reorder(cart_token: str, order_number: str) -> dict[str, Any]:
    """Add every line of a past order back into the cart (Limit-3 clamped)."""
    order = get_order(order_number)
    if order is None:
        raise OrderActionError("order not found", status=404)
    view = None
    for it in order["items"]:
        view = add_to_cart(cart_token, it["itemId"], it["qty"])
    return view if view is not None else get_cart(cart_token)


def get_lists() -> list[dict[str, Any]]:
    backend, _ = services()
    with backend.lifecycle.connection() as cx:
        lrows = cx.execute("SELECT * FROM hd_lists ORDER BY id").fetchall()
        out = []
        for lst in lrows:
            items = cx.execute(
                "SELECT li.item_id,p.label,p.model,p.price,p.thumb FROM hd_list_items li"
                " JOIN hd_products p ON p.item_id=li.item_id WHERE li.list_id=?",
                (lst["id"],)).fetchall()
            out.append({"id": lst["id"], "name": lst["name"],
                        "items": [dict(itemId=i["item_id"], label=i["label"],
                                       model=i["model"], price=i["price"],
                                       thumb=i["thumb"]) for i in items]})
    return out

def add_to_list(item_id: str, list_name: str = "My List") -> dict[str, Any]:
    """Save one product to a named saved-list, creating the list if needed.

    Lists are guest-visible (account_id NULL), matching the seed lists; the
    UNIQUE(list_id,item_id) constraint makes a repeat save idempotent.
    """
    name = (list_name or "My List").strip()[:80] or "My List"
    backend, _ = services()
    with backend.lifecycle.connection(transaction=True) as cx:
        if _product_row(cx, item_id) is None:
            raise ValueError("unknown item")
        row = cx.execute("SELECT id FROM hd_lists WHERE name=? ORDER BY id LIMIT 1",
                         (name,)).fetchone()
        if row is None:
            cx.execute("INSERT INTO hd_lists (account_id,name,created_at) VALUES (NULL,?,?)",
                       (name, FROZEN_CLOCK_UTC))
            list_id = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
        else:
            list_id = row["id"]
        before = cx.execute("SELECT COUNT(*) FROM hd_list_items WHERE list_id=?",
                            (list_id,)).fetchone()[0]
        cx.execute("INSERT OR IGNORE INTO hd_list_items (list_id,item_id) VALUES (?,?)",
                   (list_id, item_id))
        after = cx.execute("SELECT COUNT(*) FROM hd_list_items WHERE list_id=?",
                           (list_id,)).fetchone()[0]
    return {"ok": True, "list": name, "added": after > before, "count": after}
