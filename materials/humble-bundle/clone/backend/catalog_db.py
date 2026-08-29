"""Humble Bundle offline clone — business backend on the vendored seam.

Owns the site business schema (``hb_``-prefixed tables: catalog, captured
search orders, captured suggest panels, bundles/tiers/items, bundles
listing, carts, wishlist, purchases, purchase items, keys) on top of the
vendored
``websitebench.site_backend`` runtime, which owns the library tables
(site binding / mail jobs / payment ledger) and — via
``websitebench.local_clone_auth`` — the auth tables, all in the same bound
SQLite file (``humble-bundle.sqlite3``).

The runtime contract (``backend/runtime.json``) declares this module's
:func:`migrate` and :func:`seed` as its ``migration_hook`` / ``seed_hook``;
the seam resolves them by their dotted names, so the module must be imported
as ``backend.catalog_db``. Both hooks receive the lifecycle's already-open
transaction connection and therefore never call ``executescript`` (which
would commit the seam's transaction edge) — every statement runs through
``Connection.execute``.

Determinism: all money is integer minor units in the captured currency
(CAD); timestamps are pinned to frozen constants (no wall clock); order
numbers derive from the purchase row id; synthetic keys derive from
``sha256(order_no, machine_name)`` and are clearly sandbox-labeled.
:func:`reset` restores the full deterministic seed (catalog, bundles, demo
account, seeded purchases) and clears run accounts/carts/orders plus the
library payment/mail ledgers in one SQLite transaction.

Evidence grading of ordering rules (documented deterministic fallbacks):

- Captured (authoritative): search ``portal`` order (29 results) and
  ``genre=adventure`` + ``sort=bestselling`` order (40 results) reproduce
  the frozen listings exactly, via ``hb_product_search_orders``; the
  header-search suggest panel for ``portal`` (5 rows) is pinned verbatim
  via ``hb_suggest_orders`` (seed ``suggest_orders``, parsed from the
  frozen suggest DOM capture).
- Inferred ``global_rank`` fallback: the harvest contains exactly the union
  of the two captured listings (no overlap), so the "first-seen captured
  order" is the portal listing in rank order followed by the adventure
  listing in rank order. Uncaptured queries and un-anchored sorts tiebreak
  on this rank.
- Inferred ``newest`` sort: the harvest carries no release dates; products
  with a seeded ``cta_badge`` (new / preorder / earlyaccess — the same
  badges that ground the ``new`` filter) sort first, then ``global_rank``.
  Evidence-graded inferred, not captured.

Payment boundary (scope/payment-scope-decision.md): the only client payment
input is an opaque local-sandbox scenario id. :data:`PAYMENT_KEY_RE` guards
payment-shaped keys; the app layer applies it to the raw request body and
this module re-applies it to split metadata. Amounts are recomputed
server-side from the persisted cart; bundle amounts are re-validated against
the frozen tier floor. The payment ledger's currency is frozen by the
runtime contract (``payments.currency``) and is passed through as-is, while
business rows keep the captured CAD minor units.
"""

from __future__ import annotations

import hashlib
import json
import math
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

SITE_ID = "humble-bundle"
CURRENCY = "CAD"  # captured presentation currency of every *_minor value
FROZEN_CLOCK_UTC = "2026-08-20T22:39:17Z"  # harvest timestamp; no wall clock
ROOT = Path(__file__).resolve().parent
SEED_PATH = ROOT / "seed_data.json"

PAGE_SIZE = 20
MAX_CART_SIZE = 20
MAX_WISHLIST_SIZE = 100

# Deterministic identity for the seeded demo account (fully synthetic).
# The auth store owns the credential material; business rows reference the
# account by its normalized email, which the app layer reads back from the
# public session (``account.email_normalized``).
DEMO_ACCOUNT_SUBJECT = "humble-bundle-demo-gamer"
DEMO_EMAIL = "demo.gamer@example.test"
DEMO_PASSWORD = "HumbleDemo!2026"
DEMO_DISPLAY_NAME = "Riley Chen"
DEMO_OWNER = DEMO_EMAIL

ANCHOR_BUNDLE_SLUG = "yes-chef-cooking-bundle"
# Demo history fixtures (order numbers + frozen timestamps are constants;
# item sets and totals derive from the seed catalog/tier data).
DEMO_BUNDLE_ORDER_NO = "HB2026080001"
DEMO_BUNDLE_AMOUNT_MINOR = 1500
DEMO_BUNDLE_PURCHASED_AT = "2026-08-14T18:05:00Z"
DEMO_PRODUCT_ORDER_NO = "HB2026080002"
DEMO_PRODUCT_SLUG = "bridge-constructor-portal"  # captured portal rank 1
DEMO_PRODUCT_PURCHASED_AT = "2026-08-16T11:32:00Z"

SPLIT_MODES = ("default", "extra-charity", "custom")

# Payment processors offered by the source review (radio ``processor-type``:
# Paypal / Credit Card / Alipay). The clone stays a local sandbox, so each
# label maps to an opaque sandbox scenario id; no processor is ever contacted.
PROCESSORS = ("paypal", "card", "alipay")
PROCESSOR_SCENARIOS = {
    "paypal": "sandbox-approved",
    "card": "sandbox-approved",
    "alipay": "sandbox-approved",
}

# Gift modes mirror the source's ``gifting-enabled`` + ``gift-type`` pair:
# unchecked -> "none"; checked -> gift-recipient-email | gift-recipient-link.
GIFT_MODES = ("none", "email", "link")
LEADERBOARD_NAME_MAX = 70  # source input maxlength

# --- regional tax + charity math (captured oracle) -------------------------
# Walk tr-001 captured the authenticated review for the anchor bundle at the
# custom price CA$15.00 and showed, in the Order Summary:
#     Subtotal CA$15.00 | HST CA$1.85 | Total CA$16.85 | charity CA$0.75
# Charity is the bundle's OWN split share, not a guess: the frozen splits
# give the ``paypalgivingfund`` party sibling_split 0.05, and 5% of 1500 is
# exactly the captured 75 minor.
# The tax line then reproduces exactly as 13% (the captured region's HST
# rate) of the NON-charity remainder: (1500 - 75) * 13% = 185.25 -> 185.
# A flat 13% of the subtotal would be 195, and no clean single rate on the
# full subtotal yields 185 (it would need 12.333%), so the taxable base
# provably excludes the charitable share. ``TAX_ORACLE`` keeps the captured
# quadruple next to the rate as the regression anchor.
#
# ROUNDING. The bundle oracle does not discriminate: 185.25 truncates and
# rounds-half-up to the same 185. The authenticated store cart drawer
# (walk-671 ``cart-drawer-populated``) does: on a CA$1.37 sub-total it shows
# ``Sales Tax: CA$0.17`` and a self-consistent ``Total: CA$1.54``, while
# 137 * 13% = 17.81 would round half-up to 18. The source therefore
# TRUNCATES the tax line, and ``_bp_of`` floors. ``TAX_ORACLE_STORE`` pins
# that second, discriminating observation.
#
# LABEL. The same rate carries two captured labels, one per flow: the store
# cart drawer says ``Sales Tax:`` and the bundle checkout Order Summary says
# ``HST``. The label travels with the computed totals (``tax_flow`` /
# ``tax_label``) so no surface hardcodes one of them.
TAX_LABEL_BUNDLE = "HST"  # captured: bundle checkout Order Summary
TAX_LABEL_STORE = "Sales Tax"  # captured: store cart drawer totals block
TAX_FLOW_LABELS = {"bundle": TAX_LABEL_BUNDLE, "store": TAX_LABEL_STORE}
TAX_FLOW_DEFAULT = "bundle"
TAX_LABEL = TAX_LABEL_BUNDLE
TAX_RATE_BP = 1300  # 13.00% in basis points; integer math only, no floats
TAX_ORACLE = {
    "bundle_slug": ANCHOR_BUNDLE_SLUG,
    "split_mode": "default",
    "subtotal_minor": 1500,
    "charity_minor": 75,
    "tax_minor": 185,
    "grand_total_minor": 1685,
}
# Store-flow oracle from the authenticated drawer capture: one store product,
# no charity share, so the taxable base is the whole sub-total.
TAX_ORACLE_STORE = {
    "product_slug": "bridge-constructor-portal-portal-proficiency",
    "subtotal_minor": 137,
    "charity_minor": 0,
    "tax_minor": 17,  # 17.81 truncated; half-up would be 18
    "grand_total_minor": 154,
    "tax_label": TAX_LABEL_STORE,
}

# --- store rewards + membership coupon (captured drawer lines) -------------
# ``Wallet Credit Earned CA$0.14`` sits under the drawer totals on a CA$1.37
# sub-total. The rate is not guessed: the store API payload harvested with the
# catalog carries a per-product ``rewards_split`` and it is 0.1 for this
# product (``source-current/2026-08-20.humble-bundle-r1/api-harvest/
# product-detail-1.json``; 0.1 for 117 of the 139 harvested entries, with 0.05
# and 0.0 the only other values). 137 * 10% = 13.7, and the captured 14 is the
# NEAREST cent, not the truncated one -- so the rewards line rounds where the
# tax line truncates, which is why it gets its own helper. A single
# observation cannot separate nearest from ceiling; nearest is used and the
# ambiguity is recorded in scope/implement-notes.md.
# The seed does not carry the per-product ``rewards_split`` column, so the
# clone applies the harvest's modal rate uniformly (disclosed difference).
WALLET_CREDIT_BP = 1000  # 10.00%, harvest ``rewards_split`` 0.1
WALLET_CREDIT_LABEL = "Wallet Credit Earned"
WALLET_CREDIT_ORACLE = {"subtotal_minor": 137, "credit_minor": 14}
# ``You'll get a coupon for CA$1.95 off your first month when you check out.``
# One observation only (that same CA$1.37 cart), so the offer is reproduced as
# the captured constant; the copy's "Save even more by adding items!" implies
# the real value scales with the cart, but no second cart was captured and no
# scaling rule is invented here.
CHOICE_COUPON_MINOR = 195
# The charity party in every frozen bundle's split list (PayPal Giving Fund
# passthrough); its ``name`` is the charity shown in the summary callout.
CHARITY_SPLIT_CLASS = "paypalgivingfund"

# No payment-shaped key may enter a business write path. Matches key NAMES
# (card/pan/cvv/expiry/bank/wallet/provider shapes), not values; benign keys
# like scenario_id / amount_minor / gift_email / allocations never match.
PAYMENT_KEY_RE = re.compile(
    r"(?<![a-z0-9])(card|pan|cvv|cvc|iban)(?![a-z0-9])"
    r"|card[-_ ]?number|expir|security[-_]?code"
    r"|payment[-_]?(?:method|token|card)"
    r"|stripe|bank|routing|account[-_]?number|wallet",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# typed errors
# ---------------------------------------------------------------------------
class PaymentFieldRejected(ValueError):
    """A card/payment-like key reached a business write path."""


class NotFound(LookupError):
    """A referenced product / bundle / cart line / purchase does not exist."""


class BelowFloor(ValueError):
    """A pay-what-you-want amount is below the bundle's frozen floor."""

    def __init__(self, floor_minor: int) -> None:
        super().__init__(f"amount is below the bundle floor of {floor_minor} minor")
        self.floor_minor = floor_minor


class CartLimitExceeded(ValueError):
    """The cart already holds MAX_CART_SIZE items."""


class WishlistLimitExceeded(ValueError):
    """The wishlist already holds MAX_WISHLIST_SIZE items."""


class EmptyCart(ValueError):
    """Checkout was attempted on an empty cart."""


class SplitInvalid(ValueError):
    """Charity split metadata was malformed or did not sum to the total."""


class ProcessorInvalid(ValueError):
    """An unknown ``processor-type`` reached checkout (see PROCESSORS)."""


class GiftRecipientInvalid(ValueError):
    """gift-by-email was chosen without a correctly formatted address."""


class PaymentDeclined(RuntimeError):
    """The sandbox declined the attempt; no business rows were written."""

    def __init__(self, scenario_id: str) -> None:
        super().__init__("payment was declined by the sandbox")
        self.scenario_id = scenario_id


class PaymentRetryable(RuntimeError):
    """The sandbox asked for a retry; no business rows were written."""

    def __init__(self, scenario_id: str) -> None:
        super().__init__("payment is retryable; please try again")
        self.scenario_id = scenario_id


def reject_payment_keys(payload: Any) -> None:
    """Recursively refuse dict keys that look like payment instruments."""

    if isinstance(payload, dict):
        for key, value in payload.items():
            if PAYMENT_KEY_RE.search(str(key)):
                raise PaymentFieldRejected(f"payment-like key rejected: {key}")
            reject_payment_keys(value)
    elif isinstance(payload, (list, tuple)):
        for value in payload:
            reject_payment_keys(value)


# ---------------------------------------------------------------------------
# schema (idempotent CREATEs + pragma-guarded ALTERs; no executescript)
# ---------------------------------------------------------------------------
_MIGRATIONS: dict[str, list[str]] = {
    "0001_catalog": [
        """
        CREATE TABLE IF NOT EXISTS hb_products (
            slug TEXT PRIMARY KEY,
            machine_name TEXT NOT NULL UNIQUE,
            human_name TEXT NOT NULL,
            current_price_minor INTEGER NOT NULL,
            full_price_minor INTEGER NOT NULL,
            discount_pct INTEGER NOT NULL DEFAULT 0,
            cta_badge TEXT,
            global_rank INTEGER NOT NULL,
            genres_json TEXT NOT NULL DEFAULT '[]',
            platforms_json TEXT NOT NULL DEFAULT '[]',
            drm_json TEXT NOT NULL DEFAULT '[]',
            payload_json TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_hb_products_rank"
        " ON hb_products(global_rank)",
        """
        CREATE TABLE IF NOT EXISTS hb_product_search_orders (
            query_key TEXT NOT NULL,
            rank INTEGER NOT NULL,
            slug TEXT NOT NULL REFERENCES hb_products(slug),
            PRIMARY KEY (query_key, rank)
        )
        """,
    ],
    "0002_bundles": [
        """
        CREATE TABLE IF NOT EXISTS hb_bundles (
            slug TEXT PRIMARY KEY,
            machine_name TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            type TEXT,
            end_at TEXT,
            msrp_minor INTEGER NOT NULL,
            floor_minor INTEGER NOT NULL,
            suggested_price_minor INTEGER,
            preset_prices_json TEXT NOT NULL DEFAULT '[]',
            tier_order_json TEXT NOT NULL DEFAULT '[]',
            charity_json TEXT,
            charity_raised_minor INTEGER,
            splits_json TEXT NOT NULL DEFAULT '[]',
            sold_count INTEGER,
            harvested_at TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hb_bundle_tiers (
            slug TEXT NOT NULL REFERENCES hb_bundles(slug),
            tier_id TEXT NOT NULL,
            ord INTEGER NOT NULL,
            threshold_minor INTEGER NOT NULL,
            header TEXT,
            item_count INTEGER NOT NULL,
            PRIMARY KEY (slug, tier_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hb_bundle_items (
            id INTEGER PRIMARY KEY,
            slug TEXT NOT NULL,
            tier_id TEXT NOT NULL,
            ord INTEGER NOT NULL,
            machine_name TEXT NOT NULL,
            human_name TEXT NOT NULL,
            msrp_minor INTEGER,
            one_liner TEXT,
            steam_positive_pct INTEGER,
            media_json TEXT,
            UNIQUE (slug, tier_id, ord)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hb_bundles_listing (
            category TEXT NOT NULL,
            ord INTEGER NOT NULL,
            slug TEXT NOT NULL,
            machine_name TEXT NOT NULL,
            name TEXT NOT NULL,
            type TEXT,
            end_at TEXT,
            highlights_json TEXT NOT NULL DEFAULT '[]',
            tile_image TEXT,
            PRIMARY KEY (category, ord)
        )
        """,
    ],
    "0003_cart_wishlist": [
        """
        CREATE TABLE IF NOT EXISTS hb_carts (
            cart_id TEXT PRIMARY KEY,
            owner TEXT,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hb_cart_items (
            item_id INTEGER PRIMARY KEY,
            cart_id TEXT NOT NULL REFERENCES hb_carts(cart_id) ON DELETE CASCADE,
            kind TEXT NOT NULL CHECK (kind IN ('bundle','product')),
            slug TEXT NOT NULL,
            amount_minor INTEGER,
            qty INTEGER NOT NULL DEFAULT 1 CHECK (qty >= 1),
            UNIQUE (cart_id, kind, slug)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_hb_cart_items_cart"
        " ON hb_cart_items(cart_id)",
        """
        CREATE TABLE IF NOT EXISTS hb_wishlist (
            owner TEXT NOT NULL,
            slug TEXT NOT NULL REFERENCES hb_products(slug),
            added_at TEXT NOT NULL,
            PRIMARY KEY (owner, slug)
        )
        """,
    ],
    "0004_purchases": [
        """
        CREATE TABLE IF NOT EXISTS hb_purchases (
            id INTEGER PRIMARY KEY,
            order_no TEXT NOT NULL UNIQUE,
            owner TEXT,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Completed',
            total_minor INTEGER NOT NULL,
            charged_minor INTEGER NOT NULL,
            scenario TEXT,
            delivery_kind TEXT NOT NULL DEFAULT 'self'
                CHECK (delivery_kind IN ('self','gift')),
            gift_email TEXT,
            splits_json TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hb_purchase_items (
            id INTEGER PRIMARY KEY,
            order_no TEXT NOT NULL REFERENCES hb_purchases(order_no),
            kind TEXT NOT NULL CHECK (kind IN ('bundle','product')),
            slug TEXT NOT NULL,
            human_name TEXT NOT NULL,
            amount_minor INTEGER NOT NULL,
            qty INTEGER NOT NULL DEFAULT 1
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hb_keys (
            order_no TEXT NOT NULL REFERENCES hb_purchases(order_no),
            machine_name TEXT NOT NULL,
            human_name TEXT NOT NULL,
            key_code TEXT NOT NULL,
            revealed INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (order_no, machine_name)
        )
        """,
    ],
    "0005_schema_log": [
        """
        CREATE TABLE IF NOT EXISTS hb_schema_migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """,
    ],
    # Captured header-search suggest panels: one pre-rendered row per
    # (typed query, panel position), stored verbatim as seeded JSON.
    "0006_suggest_orders": [
        """
        CREATE TABLE IF NOT EXISTS hb_suggest_orders (
            query_key TEXT NOT NULL,
            ord INTEGER NOT NULL,
            row_json TEXT NOT NULL,
            PRIMARY KEY (query_key, ord)
        )
        """,
    ],
    # /user/settings preferences the captured page lets an account edit:
    # the delivery (contact) email, the ten contact-preference checkboxes
    # and the charity preference. Keyed by the business owner key, so a
    # reset restores the captured defaults.
    "0007_account_prefs": [
        """
        CREATE TABLE IF NOT EXISTS hb_account_prefs (
            owner TEXT PRIMARY KEY,
            delivery_email TEXT,
            subscriptions_json TEXT NOT NULL DEFAULT '{}',
            charity_preference TEXT
        )
        """,
    ],
}

# All mutable + static business tables, in FK-safe delete order.
_BUSINESS_TABLES = (
    "hb_account_prefs",
    "hb_keys",
    "hb_purchase_items",
    "hb_purchases",
    "hb_wishlist",
    "hb_cart_items",
    "hb_carts",
    "hb_bundles_listing",
    "hb_bundle_items",
    "hb_bundle_tiers",
    "hb_bundles",
    "hb_suggest_orders",
    "hb_product_search_orders",
    "hb_products",
)


def _ensure_column(
    cx: sqlite3.Connection, table: str, column: str, declaration: str
) -> None:
    """Pragma-guarded ALTER: SQLite has no ADD COLUMN IF NOT EXISTS and the
    CREATE statements above re-run idempotently on every startup."""

    columns = {row[1] for row in cx.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        cx.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def align_schema(cx: sqlite3.Connection) -> None:
    """Bring an existing database up to the current column set.

    The seam records a declared migration hook by its declaration string and
    never runs it again (``websitebench_backend_migrations`` holds
    ``site-migration:backend.catalog_db:migrate``), so a column added to
    :func:`migrate` after a database exists would be skipped forever — a
    deployed instance would keep an old table shape across a code upgrade.
    These guarded ALTERs are therefore applied on every open, from
    :func:`services`, not only from the one-shot hook.
    """

    _ensure_column(cx, "hb_carts", "order_seq", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(cx, "hb_purchases", "payment_flow_id", "TEXT")
    _ensure_column(cx, "hb_purchases", "payment_attempt_id", "TEXT")
    # Review-surface fields captured by walk tr-001 (processor choice, gift
    # opt-in triple, leaderboard opt-in) and the Order Summary numbers the
    # review shows (tax line + charity share).
    _ensure_column(cx, "hb_purchases", "processor", "TEXT")
    _ensure_column(cx, "hb_purchases", "gift_mode", "TEXT")
    _ensure_column(
        cx, "hb_purchases", "gift_anonymous", "INTEGER NOT NULL DEFAULT 0"
    )
    _ensure_column(cx, "hb_purchases", "leaderboard_name", "TEXT")
    _ensure_column(cx, "hb_purchases", "tax_minor", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(
        cx, "hb_purchases", "charity_minor", "INTEGER NOT NULL DEFAULT 0"
    )
    _ensure_column(cx, "hb_purchases", "charity_name", "TEXT")
    # Same reasoning for a whole table added after a database exists: the seam
    # will not re-run the declared hook, so the /user/settings preference table
    # is created here too (the statement is idempotent by construction).
    for statement in _MIGRATIONS["0007_account_prefs"]:
        cx.execute(statement)


def migrate(cx: sqlite3.Connection) -> None:
    """Declared ``migration_hook`` — idempotent, runs in the seam's txn."""

    for statements in _MIGRATIONS.values():
        for statement in statements:
            cx.execute(statement)
    align_schema(cx)
    for name in _MIGRATIONS:
        cx.execute(
            "INSERT OR IGNORE INTO hb_schema_migrations (name, applied_at)"
            " VALUES (?, ?)",
            (name, FROZEN_CLOCK_UTC),
        )


# ---------------------------------------------------------------------------
# seed
# ---------------------------------------------------------------------------
_seed_cache: dict[str, Any] | None = None


def _seed_doc() -> dict[str, Any]:
    global _seed_cache
    if _seed_cache is None:
        _seed_cache = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    return _seed_cache


def _global_order(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """First-seen captured order: portal ranks, then adventure ranks.

    The harvest is exactly the union of the two captured listings with no
    overlap; anything without a rank (defensive) sorts last by slug.
    """

    def sort_key(product: dict[str, Any]) -> tuple[int, int, str]:
        orders = product.get("search_orders", {})
        if "portal" in orders:
            return (0, int(orders["portal"]), product["slug"])
        if "adventure-bestselling" in orders:
            return (1, int(orders["adventure-bestselling"]), product["slug"])
        return (2, 0, product["slug"])

    return sorted(products, key=sort_key)


def _install_catalog(cx: sqlite3.Connection, doc: dict[str, Any]) -> None:
    for rank, product in enumerate(_global_order(doc["products"]), start=1):
        cx.execute(
            "INSERT OR REPLACE INTO hb_products (slug, machine_name,"
            " human_name, current_price_minor, full_price_minor, discount_pct,"
            " cta_badge, global_rank, genres_json, platforms_json, drm_json,"
            " payload_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                product["slug"],
                product["machine_name"],
                product["human_name"],
                product["current_price_minor"],
                product["full_price_minor"],
                product.get("discount_pct", 0),
                product.get("cta_badge"),
                rank,
                json.dumps(product.get("genres", [])),
                json.dumps(product.get("platforms", [])),
                json.dumps(product.get("drm", [])),
                json.dumps(product, ensure_ascii=False),
            ),
        )
        for query_key, captured_rank in product.get("search_orders", {}).items():
            cx.execute(
                "INSERT OR REPLACE INTO hb_product_search_orders"
                " (query_key, rank, slug) VALUES (?,?,?)",
                (query_key, int(captured_rank), product["slug"]),
            )
    for query_key, rows in doc.get("suggest_orders", {}).items():
        for ord_, row in enumerate(rows):
            cx.execute(
                "INSERT OR REPLACE INTO hb_suggest_orders"
                " (query_key, ord, row_json) VALUES (?,?,?)",
                (query_key, ord_, json.dumps(row, ensure_ascii=False)),
            )
    for bundle in doc["bundles"]:
        cx.execute(
            "INSERT OR REPLACE INTO hb_bundles (slug, machine_name, name,"
            " type, end_at, msrp_minor, floor_minor, suggested_price_minor,"
            " preset_prices_json, tier_order_json, charity_json,"
            " charity_raised_minor, splits_json, sold_count, harvested_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                bundle["slug"],
                bundle["machine_name"],
                bundle["name"],
                bundle.get("type"),
                bundle.get("end_at"),
                bundle["msrp_minor"],
                bundle["floor_minor"],
                bundle.get("suggested_price_minor"),
                json.dumps(bundle.get("preset_prices_minor", [])),
                json.dumps(bundle.get("tier_order", [])),
                json.dumps(bundle.get("charity"), ensure_ascii=False),
                bundle.get("charity_raised_minor"),
                json.dumps(bundle.get("splits", []), ensure_ascii=False),
                bundle.get("sold_count"),
                bundle.get("harvested_at"),
            ),
        )
        tier_order = list(bundle.get("tier_order", []))
        tiers_by_id = {tier["tier_id"]: tier for tier in bundle["tiers"]}
        for position, tier_id in enumerate(tier_order):
            tier = tiers_by_id[tier_id]
            cx.execute(
                "INSERT OR REPLACE INTO hb_bundle_tiers (slug, tier_id, ord,"
                " threshold_minor, header, item_count) VALUES (?,?,?,?,?,?)",
                (
                    bundle["slug"],
                    tier_id,
                    position,
                    tier["threshold_minor"],
                    tier.get("header"),
                    tier["item_count"],
                ),
            )
            cx.execute(
                "DELETE FROM hb_bundle_items WHERE slug=? AND tier_id=?",
                (bundle["slug"], tier_id),
            )
            for ord_, item in enumerate(tier.get("items", [])):
                cx.execute(
                    "INSERT INTO hb_bundle_items (slug, tier_id, ord,"
                    " machine_name, human_name, msrp_minor, one_liner,"
                    " steam_positive_pct, media_json)"
                    " VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        bundle["slug"],
                        tier_id,
                        ord_,
                        item["machine_name"],
                        item["human_name"],
                        item.get("msrp_minor"),
                        item.get("one_liner"),
                        item.get("steam_positive_pct"),
                        json.dumps(item.get("media"), ensure_ascii=False),
                    ),
                )
    for category, tiles in doc["bundles_listing"].items():
        for ord_, tile in enumerate(tiles):
            cx.execute(
                "INSERT OR REPLACE INTO hb_bundles_listing (category, ord,"
                " slug, machine_name, name, type, end_at, highlights_json,"
                " tile_image) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    category,
                    ord_,
                    tile["slug"],
                    tile["machine_name"],
                    tile["name"],
                    tile.get("type"),
                    tile.get("end_at"),
                    json.dumps(tile.get("highlights", []), ensure_ascii=False),
                    tile.get("tile_image"),
                ),
            )


def _key_code(order_no: str, machine_name: str) -> str:
    """Deterministic, clearly synthetic key: SANDBOX-XXXX-XXXX-XXXX."""

    digest = hashlib.sha256(
        f"{SITE_ID}:{order_no}:{machine_name}".encode()
    ).hexdigest().upper()
    return f"SANDBOX-{digest[0:4]}-{digest[4:8]}-{digest[8:12]}"


def _insert_purchase_keys(
    cx: sqlite3.Connection,
    order_no: str,
    entitlements: list[tuple[str, str]],
) -> None:
    for machine_name, human_name in entitlements:
        cx.execute(
            "INSERT OR IGNORE INTO hb_keys (order_no, machine_name,"
            " human_name, key_code, revealed) VALUES (?,?,?,?,0)",
            (order_no, machine_name, human_name, _key_code(order_no, machine_name)),
        )


def _install_demo_purchases(cx: sqlite3.Connection) -> None:
    """Two frozen history fixtures for the demo account (library/keys tests).

    Seeded purchases are fixture history, not sandbox transactions: their
    scenario is recorded as ``seeded`` and they carry no payment-ledger ids.
    """

    state = _tier_state(cx, ANCHOR_BUNDLE_SLUG, DEMO_BUNDLE_AMOUNT_MINOR)
    bundle = cx.execute(
        "SELECT name FROM hb_bundles WHERE slug=?", (ANCHOR_BUNDLE_SLUG,)
    ).fetchone()
    charity_minor, charity_name = _charity_of(
        cx, [(ANCHOR_BUNDLE_SLUG, DEMO_BUNDLE_AMOUNT_MINOR)], "default"
    )
    totals = order_totals(DEMO_BUNDLE_AMOUNT_MINOR, charity_minor, flow="bundle")
    cx.execute(
        "INSERT OR REPLACE INTO hb_purchases (order_no, owner, created_at,"
        " status, total_minor, charged_minor, scenario, delivery_kind,"
        " gift_email, splits_json, processor, gift_mode, gift_anonymous,"
        " leaderboard_name, tax_minor, charity_minor, charity_name)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            DEMO_BUNDLE_ORDER_NO,
            DEMO_OWNER,
            DEMO_BUNDLE_PURCHASED_AT,
            "Completed",
            DEMO_BUNDLE_AMOUNT_MINOR,
            totals["grand_total_minor"],
            "seeded",
            "self",
            None,
            json.dumps({"mode": "default"}),
            "card",
            "none",
            0,
            None,
            totals["tax_minor"],
            charity_minor,
            charity_name,
        ),
    )
    cx.execute(
        "INSERT INTO hb_purchase_items (order_no, kind, slug, human_name,"
        " amount_minor, qty) VALUES (?,?,?,?,?,1)",
        (
            DEMO_BUNDLE_ORDER_NO,
            "bundle",
            ANCHOR_BUNDLE_SLUG,
            bundle["name"],
            DEMO_BUNDLE_AMOUNT_MINOR,
        ),
    )
    _insert_purchase_keys(
        cx,
        DEMO_BUNDLE_ORDER_NO,
        [(row["machine_name"], row["human_name"]) for row in state["unlocked_items"]],
    )

    product = cx.execute(
        "SELECT machine_name, human_name, current_price_minor FROM hb_products"
        " WHERE slug=?",
        (DEMO_PRODUCT_SLUG,),
    ).fetchone()
    product_totals = order_totals(
        int(product["current_price_minor"]), 0, flow="store"
    )
    cx.execute(
        "INSERT OR REPLACE INTO hb_purchases (order_no, owner, created_at,"
        " status, total_minor, charged_minor, scenario, delivery_kind,"
        " gift_email, splits_json, processor, gift_mode, gift_anonymous,"
        " leaderboard_name, tax_minor, charity_minor, charity_name)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            DEMO_PRODUCT_ORDER_NO,
            DEMO_OWNER,
            DEMO_PRODUCT_PURCHASED_AT,
            "Completed",
            product["current_price_minor"],
            product_totals["grand_total_minor"],
            "seeded",
            "self",
            None,
            None,
            "card",
            "none",
            0,
            None,
            product_totals["tax_minor"],
            0,
            None,
        ),
    )
    cx.execute(
        "INSERT INTO hb_purchase_items (order_no, kind, slug, human_name,"
        " amount_minor, qty) VALUES (?,?,?,?,?,1)",
        (
            DEMO_PRODUCT_ORDER_NO,
            "product",
            DEMO_PRODUCT_SLUG,
            product["human_name"],
            product["current_price_minor"],
        ),
    )
    _insert_purchase_keys(
        cx,
        DEMO_PRODUCT_ORDER_NO,
        [(product["machine_name"], product["human_name"])],
    )


def seed(cx: sqlite3.Connection) -> None:
    """Declared ``seed_hook`` — runs once per fresh database, in the seam's
    transaction. The demo *account* cannot be created here (the auth store's
    schema does not exist yet at hook time); :func:`ensure_demo` binds it as
    soon as the services open."""

    doc = _seed_doc()
    _install_catalog(cx, doc)
    _install_demo_purchases(cx)


# ---------------------------------------------------------------------------
# services (one bound backend + auth store per process)
# ---------------------------------------------------------------------------
_services_cache: tuple[Any, Any] | None = None


def services() -> tuple[Any, Any]:
    global _services_cache
    if _services_cache is None:
        _services_cache = open_site_services()
        backend = _services_cache[0]
        with backend.lifecycle.connection(transaction=True) as cx:
            align_schema(cx)
        ensure_demo(_services_cache[1])
    return _services_cache


def _demo_seed_accounts() -> list[dict[str, Any]]:
    return [
        {
            "subject_id": DEMO_ACCOUNT_SUBJECT,
            "email": DEMO_EMAIL,
            "display_name": DEMO_DISPLAY_NAME,
            "password": DEMO_PASSWORD,
            "email_verified": True,
        }
    ]


def ensure_demo(auth: Any) -> None:
    """Idempotently bind the synthetic demo account to real credentials.

    Mirrors the seam mechanism used by earlier sites: the auth store keeps
    accounts in library tables the business seed hook cannot reach, so the
    account is seeded at service-open time and re-seeded by :func:`reset`.
    """

    if auth is None:  # pragma: no cover - auth store is always present here
        return
    auth.seed_account(
        subject_id=DEMO_ACCOUNT_SUBJECT,
        email=DEMO_EMAIL,
        display_name=DEMO_DISPLAY_NAME,
        password=DEMO_PASSWORD,
        email_verified=True,
    )


def reset() -> None:
    """Deterministic full reset in one transaction via the auth seam.

    Restores the frozen catalog/bundles/listing, the demo account (undoing
    any password change) and its two seeded purchases; clears run accounts,
    sessions, carts, wishlists, orders and keys; and empties the library
    payment/mail ledgers through the lifecycle's embedded reset so replayed
    runs regenerate identical payment flows.
    """

    backend, auth = services()

    def _restore(cx: sqlite3.Connection) -> None:
        backend.lifecycle.reset_embedded(cx, confirm_site_id=SITE_ID)
        for table in _BUSINESS_TABLES:
            cx.execute(f"DELETE FROM {table}")
        doc = _seed_doc()
        _install_catalog(cx, doc)
        _install_demo_purchases(cx)

    auth.reset_site_state(
        site_reset=_restore,
        seed_accounts=_demo_seed_accounts(),
    )


# ---------------------------------------------------------------------------
# catalog API
# ---------------------------------------------------------------------------
def _payload(row: sqlite3.Row) -> dict[str, Any]:
    return json.loads(row["payload_json"])


def get_product(slug: str) -> dict[str, Any] | None:
    backend, _ = services()
    with backend.lifecycle.connection() as cx:
        row = cx.execute(
            "SELECT payload_json FROM hb_products WHERE slug=?", (slug,)
        ).fetchone()
    return _payload(row) if row else None


def _captured_order(cx: sqlite3.Connection, query_key: str) -> list[sqlite3.Row]:
    return cx.execute(
        "SELECT p.* FROM hb_product_search_orders o"
        " JOIN hb_products p ON p.slug=o.slug"
        " WHERE o.query_key=? ORDER BY o.rank",
        (query_key,),
    ).fetchall()


def _matches_filters(
    row: sqlite3.Row,
    *,
    genre: str | None,
    platform: str | None,
    drm: str | None,
    filter_key: str | None,
) -> bool:
    if genre is not None and genre not in json.loads(row["genres_json"]):
        return False
    if platform is not None and platform not in json.loads(row["platforms_json"]):
        return False
    if drm is not None and drm not in json.loads(row["drm_json"]):
        return False
    if filter_key == "onsale" and not row["discount_pct"] > 0:
        return False
    if filter_key == "new" and row["cta_badge"] is None:
        return False
    return True


def search(
    search: str | None = None,
    genre: str | None = None,
    platform: str | None = None,
    drm: str | None = None,
    sort: str = "bestselling",
    filter: str | None = None,
    page: int = 0,
) -> dict[str, Any]:
    """Store search with captured-order oracles and documented fallbacks.

    Ordering: a query with a captured listing (``portal``, case-insensitive)
    reproduces that listing; ``genre=adventure`` with ``sort=bestselling``
    and no query reproduces the captured adventure listing (that listing is
    authoritative for both membership and order); any other query is a
    case-insensitive title-substring match ordered by ``global_rank``.
    Non-default sorts re-rank the matched set: ``discount`` by discount desc
    then rank, ``alphabetical`` by title, ``newest`` by badge-first then
    rank (inferred fallback — see module docstring).
    """

    query = (search or "").strip().lower()
    page = max(0, int(page))
    if sort not in ("discount", "alphabetical", "newest", "bestselling"):
        sort = "bestselling"
    filter_key = filter if filter in ("onsale", "new") else None

    backend, _ = services()
    with backend.lifecycle.connection() as cx:
        captured_genre_listing = False
        if query:
            captured = _captured_order(cx, query)
            if captured:
                matched = list(captured)
            else:
                matched = [
                    row
                    for row in cx.execute(
                        "SELECT * FROM hb_products ORDER BY global_rank"
                    )
                    if query in row["human_name"].lower()
                ]
        elif genre == "adventure" and sort == "bestselling":
            matched = list(_captured_order(cx, "adventure-bestselling"))
            captured_genre_listing = True
        else:
            matched = cx.execute(
                "SELECT * FROM hb_products ORDER BY global_rank"
            ).fetchall()

        matched = [
            row
            for row in matched
            if _matches_filters(
                row,
                genre=None if captured_genre_listing else genre,
                platform=platform,
                drm=drm,
                filter_key=filter_key,
            )
        ]

    if sort == "discount":
        matched.sort(key=lambda r: (-r["discount_pct"], r["global_rank"]))
    elif sort == "alphabetical":
        matched.sort(key=lambda r: (r["human_name"].casefold(), r["slug"]))
    elif sort == "newest":
        matched.sort(
            key=lambda r: (0 if r["cta_badge"] is not None else 1, r["global_rank"])
        )

    num_results = len(matched)
    start = page * PAGE_SIZE
    return {
        "results": [_payload(row) for row in matched[start : start + PAGE_SIZE]],
        "num_results": num_results,
        "num_pages": math.ceil(num_results / PAGE_SIZE),
        "page_size": PAGE_SIZE,
    }


# Captured suggest icon classes are hb-<token>: delivery keys pass through
# (hb-steam, ...) and platform keys map to the captured tokens (the panel
# renders platform "mac" as hb-osx). Platforms display in the captured
# panel order (windows, osx, linux) before any remaining payload order.
_SUGGEST_PLATFORM_ICON = {"mac": "osx"}
_SUGGEST_PLATFORM_DISPLAY_ORDER = ("windows", "mac", "linux")


def _cad_display(minor: int) -> str:
    """Integer CAD minor units -> the captured "CA$x.xx" display string."""

    return f"CA${minor // 100}.{minor % 100:02d}"


def _suggest_bundle_row(tile: sqlite3.Row) -> dict[str, Any]:
    """A ``hb_bundles_listing`` tile -> fallback suggest row."""

    row: dict[str, Any] = {
        "kind": "bundle",
        "href": f"/{tile['category']}/{tile['slug']}",
        "name": tile["name"],
        "platform_icons": [],
        "delivery_separator": False,
        "discount_pct": None,
        "action_text": "View",
    }
    tile_image = tile["tile_image"]
    if tile_image:
        row["img"] = (
            {"source_url": tile_image}
            if tile_image.startswith("http")
            else {"local": tile_image}
        )
    return row


def _suggest_product_row(product: sqlite3.Row) -> dict[str, Any]:
    """An ``hb_products`` row -> fallback suggest row (icons best-effort)."""

    payload = _payload(product)
    delivery = [str(key) for key in payload.get("delivery_methods", [])]
    platforms = list(payload.get("platforms", []))
    ordered = [p for p in _SUGGEST_PLATFORM_DISPLAY_ORDER if p in platforms]
    ordered += [p for p in platforms if p not in _SUGGEST_PLATFORM_DISPLAY_ORDER]
    row: dict[str, Any] = {
        "kind": "product",
        "href": f"/store/{product['slug']}",
        "name": product["human_name"],
    }
    if product["cta_badge"] is not None:
        row["cta_badge"] = product["cta_badge"]
    row["platform_icons"] = delivery + [
        _SUGGEST_PLATFORM_ICON.get(p, p) for p in ordered
    ]
    row["delivery_separator"] = bool(delivery) and bool(ordered)
    row["discount_pct"] = product["discount_pct"] or None
    row["price_display"] = _cad_display(product["current_price_minor"])
    media = payload.get("media", {})
    img = media.get("standard_carousel_image") or media.get("icon")
    if img:
        row["img"] = img
    return row


def _suggest_href_servable(cx: sqlite3.Connection, href: str) -> bool:
    """Does ``href`` name a route this clone actually serves?

    The suggest panel is a navigation affordance, so a row that lands on
    the branded 404 is a trap: the captured ``portal`` panel's most
    prominent row is a books/software bundle
    (``/software/massive-unreal-engine-bundle-software``) whose detail page
    is outside the frozen subset (``claim.difference.books-software-bundle
    -detail``). Rows are therefore emitted only for destinations the app
    layer resolves — ``/store/<slug>`` for a seeded product and
    ``/games/<slug>`` for a seeded game bundle — on both the captured and
    the fallback path, so the rule is the same for every query.
    """

    target = (href or "").split("?", 1)[0].split("#", 1)[0].rstrip("/")
    parts = target.split("/")
    if len(parts) != 3 or parts[0]:
        return False
    section, slug = parts[1], parts[2]
    if not slug:
        return False
    if section == "store":
        table, column = "hb_products", "slug"
    elif section == "games":
        table, column = "hb_bundles", "slug"
    else:
        # /books/<slug> and /software/<slug> are the declared out-of-subset
        # bundle categories; anything else is not a detail route at all.
        return False
    row = cx.execute(
        f"SELECT 1 FROM {table} WHERE {column}=?", (slug,)
    ).fetchone()
    return row is not None


def suggest(q: str, limit: int = 5) -> list[dict[str, Any]]:
    """Header-search suggest rows for the typed query.

    A query whose normalized form (lowercased, trimmed) has a captured
    panel in ``hb_suggest_orders`` (seed ``suggest_orders``; today:
    ``portal``) returns those pinned rows in captured order. Every other
    query falls back deterministically: first bundles from the bundles
    listing whose name contains the query (listing order, ``ORDER BY
    category, ord``, deduped by slug), then products whose title contains
    it (captured ``global_rank`` order), capped at ``limit`` rows total.

    Both paths then drop rows whose destination this clone does not serve
    (see :func:`_suggest_href_servable`), so the panel never offers a link
    that resolves to the branded 404.

    Row shape — identical on both paths: ``kind`` ("bundle"|"product"),
    ``href`` (query-stripped link path), ``name``, ``platform_icons``
    (hb-<token> icon classes, delivery first), ``delivery_separator``
    (bool: a "|" separates delivery from platform icons),
    ``discount_pct`` (int | None), and exactly one of ``price_display``
    ("CA$x.xx") / ``action_text`` ("View"). Optional keys, present only
    when known: ``description`` (captured bundle row), ``cta_badge``
    (new / preorder / earlyaccess) and ``img`` (``{"local":
    "/static/assets/...", "source_url": ...}``; fallback bundle tiles
    carry ``{"local": <tile path>}``).
    """

    query = (q or "").strip().lower()
    if not query:
        return []
    cap = max(0, int(limit))
    backend, _ = services()
    with backend.lifecycle.connection() as cx:
        captured = cx.execute(
            "SELECT row_json FROM hb_suggest_orders WHERE query_key=?"
            " ORDER BY ord",
            (query,),
        ).fetchall()
        if captured:
            pinned = [json.loads(row["row_json"]) for row in captured]
            return [
                row
                for row in pinned
                if _suggest_href_servable(cx, row.get("href", ""))
            ][:cap]
        rows: list[dict[str, Any]] = []
        seen_slugs: set[str] = set()
        tiles = cx.execute(
            "SELECT * FROM hb_bundles_listing ORDER BY category, ord"
        ).fetchall()
        for tile in tiles:
            if len(rows) >= cap:
                break
            if query not in tile["name"].lower() or tile["slug"] in seen_slugs:
                continue
            seen_slugs.add(tile["slug"])
            row = _suggest_bundle_row(tile)
            if not _suggest_href_servable(cx, row["href"]):
                continue
            rows.append(row)
        if len(rows) < cap:
            for product in cx.execute(
                "SELECT * FROM hb_products ORDER BY global_rank"
            ):
                if len(rows) >= cap:
                    break
                if query in product["human_name"].lower():
                    rows.append(_suggest_product_row(product))
    return rows


# ---------------------------------------------------------------------------
# bundles
# ---------------------------------------------------------------------------
def bundles_listing() -> dict[str, list[dict[str, Any]]]:
    backend, _ = services()
    with backend.lifecycle.connection() as cx:
        rows = cx.execute(
            "SELECT * FROM hb_bundles_listing ORDER BY category, ord"
        ).fetchall()
    listing: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        listing.setdefault(row["category"], []).append(
            {
                "slug": row["slug"],
                "machine_name": row["machine_name"],
                "name": row["name"],
                "type": row["type"],
                "end_at": row["end_at"],
                "highlights": json.loads(row["highlights_json"]),
                "tile_image": row["tile_image"],
            }
        )
    return listing


def _bundle_item_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "machine_name": row["machine_name"],
        "human_name": row["human_name"],
        "msrp_minor": row["msrp_minor"],
        "one_liner": row["one_liner"],
        "steam_positive_pct": row["steam_positive_pct"],
        "media": json.loads(row["media_json"]) if row["media_json"] else None,
    }


def get_listing_bundle(slug: str) -> dict[str, Any] | None:
    """A bundle known only from a listing tile.

    `hb_bundles` holds the thirteen bundles whose full pages were captured, all
    of them game bundles. `hb_bundles_listing` holds every tile the site showed
    across books, games and software — nineteen book bundles among them, with a
    name, an end date, the highlight lines and a tile image each.

    The home page links those book bundles, so they were 404ing while their own
    data sat in the seed. This returns what the listing actually holds and says
    so, rather than letting a caller mistake it for a full bundle record.
    """
    backend, _ = services()
    with backend.lifecycle.connection() as cx:
        row = cx.execute(
            "SELECT * FROM hb_bundles_listing WHERE slug=?", (slug,)
        ).fetchone()
    if row is None:
        return None
    return {
        "slug": row["slug"],
        "machine_name": row["machine_name"],
        "name": row["name"],
        "type": row["type"],
        "end_at": row["end_at"],
        "highlights": json.loads(row["highlights_json"] or "[]"),
        "tile_image": row["tile_image"],
        "listing_only": True,
        "listing_only_reason": (
            "Captured as a listing tile. The bundle's own page was never "
            "visited, so its tiers, prices and contents are absent rather than "
            "borrowed from another bundle."),
    }


def get_bundle(slug: str) -> dict[str, Any] | None:
    backend, _ = services()
    with backend.lifecycle.connection() as cx:
        bundle = cx.execute(
            "SELECT * FROM hb_bundles WHERE slug=?", (slug,)
        ).fetchone()
        if bundle is None:
            return None
        tiers = cx.execute(
            "SELECT * FROM hb_bundle_tiers WHERE slug=? ORDER BY ord", (slug,)
        ).fetchall()
        tier_dicts = []
        for tier in tiers:
            items = cx.execute(
                "SELECT * FROM hb_bundle_items WHERE slug=? AND tier_id=?"
                " ORDER BY ord",
                (slug, tier["tier_id"]),
            ).fetchall()
            tier_dicts.append(
                {
                    "tier_id": tier["tier_id"],
                    "header": tier["header"],
                    "threshold_minor": tier["threshold_minor"],
                    "item_count": tier["item_count"],
                    "items": [_bundle_item_dict(item) for item in items],
                }
            )
    return {
        "slug": bundle["slug"],
        "machine_name": bundle["machine_name"],
        "name": bundle["name"],
        "type": bundle["type"],
        "end_at": bundle["end_at"],
        "msrp_minor": bundle["msrp_minor"],
        "floor_minor": bundle["floor_minor"],
        "suggested_price_minor": bundle["suggested_price_minor"],
        "preset_prices_minor": json.loads(bundle["preset_prices_json"]),
        "tier_order": json.loads(bundle["tier_order_json"]),
        "tiers": tier_dicts,
        "charity": json.loads(bundle["charity_json"])
        if bundle["charity_json"]
        else None,
        "charity_raised_minor": bundle["charity_raised_minor"],
        "splits": json.loads(bundle["splits_json"]),
        "sold_count": bundle["sold_count"],
        "currency": CURRENCY,
    }


def _tier_state(
    cx: sqlite3.Connection, slug: str, amount_minor: int
) -> dict[str, Any]:
    """Cumulative tier unlock math over the frozen thresholds.

    Tier item lists nest cumulatively (initial ⊆ mid ⊆ top), so the unlocked
    set is the highest tier whose threshold <= amount, and the top tier is
    the authoritative full item list/order for "missing" phrasing.
    """

    bundle = cx.execute(
        "SELECT floor_minor FROM hb_bundles WHERE slug=?", (slug,)
    ).fetchone()
    if bundle is None:
        raise NotFound(f"unknown bundle: {slug}")
    tiers = cx.execute(
        "SELECT * FROM hb_bundle_tiers WHERE slug=? ORDER BY threshold_minor",
        (slug,),
    ).fetchall()
    top = tiers[-1]
    top_items = cx.execute(
        "SELECT * FROM hb_bundle_items WHERE slug=? AND tier_id=? ORDER BY ord",
        (slug, top["tier_id"]),
    ).fetchall()
    floor_minor = int(bundle["floor_minor"])
    valid = isinstance(amount_minor, int) and amount_minor >= floor_minor
    unlocked = [t for t in tiers if t["threshold_minor"] <= amount_minor] if valid else []
    if unlocked:
        best = unlocked[-1]
        unlocked_items = cx.execute(
            "SELECT * FROM hb_bundle_items WHERE slug=? AND tier_id=?"
            " ORDER BY ord",
            (slug, best["tier_id"]),
        ).fetchall()
    else:
        unlocked_items = []
    unlocked_names = {row["machine_name"] for row in unlocked_items}
    missing = [row for row in top_items if row["machine_name"] not in unlocked_names]
    return {
        "valid": valid,
        "floor_minor": floor_minor,
        "unlocked_tier_ids": [t["tier_id"] for t in unlocked],
        "unlocked_items": unlocked_items,
        "unlocked_count": len(unlocked_items),
        "total_count": len(top_items),
        "missing_count": len(missing),
        "missing_first_name": missing[0]["human_name"] if missing else None,
        # "Pay at least CA$X to get all items": the frozen $15 message points
        # at the top threshold (22.19), not the next tier up. This field is
        # only ever the all-items threshold — below the floor it stays the
        # top threshold (which is what unlocks everything) and the caller
        # surfaces the floor separately through ``valid``/``floor_minor``,
        # so the floor is never presented as the all-items price.
        "next_threshold_minor": (
            None if not missing else int(top["threshold_minor"])
        ),
    }


def tier_preview(slug: str, amount_minor: int) -> dict[str, Any]:
    """Frozen-message contract for the pay-what-you-want box.

    At 1500 on the anchor bundle this returns unlocked_count 7 of 16,
    missing_count 9, missing_first_name "Tavern Manager Simulator" and
    next_threshold_minor 2219, so the frontend renders exactly
    "You're missing out on <first> and <missing_count - 1> more! Pay at
    least <next_threshold> to get all items."
    """

    backend, _ = services()
    with backend.lifecycle.connection() as cx:
        state = _tier_state(cx, slug, amount_minor)
    return {
        "valid": state["valid"],
        "floor_minor": state["floor_minor"],
        "unlocked_tier_ids": state["unlocked_tier_ids"],
        "unlocked_count": state["unlocked_count"],
        "total_count": state["total_count"],
        "missing_count": state["missing_count"],
        "missing_first_name": state["missing_first_name"],
        "next_threshold_minor": state["next_threshold_minor"],
    }


# ---------------------------------------------------------------------------
# cart
# ---------------------------------------------------------------------------
def _ensure_cart(
    cx: sqlite3.Connection, cart_id: str, owner: str | None = None
) -> sqlite3.Row:
    if not isinstance(cart_id, str) or not cart_id.strip():
        raise ValueError("cart_id is required")
    row = cx.execute(
        "SELECT * FROM hb_carts WHERE cart_id=?", (cart_id,)
    ).fetchone()
    if row is None:
        cx.execute(
            "INSERT INTO hb_carts (cart_id, owner, created_at) VALUES (?,?,?)",
            (cart_id, owner, FROZEN_CLOCK_UTC),
        )
    elif owner is not None and row["owner"] is None:
        cx.execute(
            "UPDATE hb_carts SET owner=? WHERE cart_id=?", (owner, cart_id)
        )
    return cx.execute(
        "SELECT * FROM hb_carts WHERE cart_id=?", (cart_id,)
    ).fetchone()


def _cart_view(
    cx: sqlite3.Connection, cart_id: str, split_mode: str = "default"
) -> dict[str, Any]:
    """Cart lines plus the Order Summary numbers the checkout review shows.

    ``split_mode`` is the donation mode carried over from the bundle page
    (the source picks it there, not on the review); it only moves the charity
    share, and through it the taxable base.
    """

    rows = cx.execute(
        "SELECT * FROM hb_cart_items WHERE cart_id=? ORDER BY item_id",
        (cart_id,),
    ).fetchall()
    cart = cx.execute(
        "SELECT * FROM hb_carts WHERE cart_id=?", (cart_id,)
    ).fetchone()
    items: list[dict[str, Any]] = []
    total_minor = 0
    for row in rows:
        if row["kind"] == "bundle":
            state = _tier_state(cx, row["slug"], row["amount_minor"])
            bundle = cx.execute(
                "SELECT name FROM hb_bundles WHERE slug=?", (row["slug"],)
            ).fetchone()
            line_total = int(row["amount_minor"])
            items.append(
                {
                    "item_id": row["item_id"],
                    "kind": "bundle",
                    "slug": row["slug"],
                    "name": bundle["name"],
                    "amount_minor": line_total,
                    "qty": 1,
                    "line_total_minor": line_total,
                    # A pay-what-you-want line has no undiscounted original,
                    # so the drawer's original/discounted pair collapses.
                    "line_full_total_minor": line_total,
                    "floor_minor": state["floor_minor"],
                    "unlocked_count": state["unlocked_count"],
                    "total_count": state["total_count"],
                }
            )
        else:
            product = cx.execute(
                "SELECT machine_name, human_name, current_price_minor,"
                " full_price_minor, discount_pct, platforms_json, drm_json"
                " FROM hb_products WHERE slug=?",
                (row["slug"],),
            ).fetchone()
            unit = int(product["current_price_minor"])
            unit_full = int(product["full_price_minor"])
            line_total = unit * row["qty"]
            items.append(
                {
                    "item_id": row["item_id"],
                    "kind": "product",
                    "slug": row["slug"],
                    # machine_name backs the captured row's per-product error
                    # holder class (js-product-error-holder-<machine_name>).
                    "machine_name": product["machine_name"],
                    "name": product["human_name"],
                    "unit_price_minor": unit,
                    "unit_full_price_minor": unit_full,
                    "discount_pct": product["discount_pct"],
                    # The captured row lists the DRM platform icon plus one
                    # "Redeem for <OS>" line per operating system.
                    "platforms": json.loads(product["platforms_json"] or "[]"),
                    "drm": json.loads(product["drm_json"] or "[]"),
                    "qty": row["qty"],
                    "line_total_minor": line_total,
                    "line_full_total_minor": unit_full * row["qty"],
                }
            )
        total_minor += line_total
    mode = split_mode if split_mode in SPLIT_MODES else "default"
    charity_minor, charity_name = _charity_of(
        cx,
        [(i["slug"], i["amount_minor"]) for i in items if i["kind"] == "bundle"],
        mode,
    )
    # Which captured surface these numbers are rendered on decides the tax
    # label. A bundle line means the bundle checkout review (``HST``);
    # store-product lines only mean the store cart drawer (``Sales Tax``).
    # The source never mixes the two (a bundle goes straight to /checkout);
    # the clone routes both through one cart, so a mixed cart is treated as
    # the bundle flow.
    flow = "bundle" if any(i["kind"] == "bundle" for i in items) else "store"
    totals = order_totals(total_minor, charity_minor, flow=flow)
    # Store rewards + membership coupon, both captured in the drawer and both
    # store-flow only (the bundle review shows the upsell checkbox instead).
    rewards_base = sum(
        i["line_total_minor"] for i in items if i["kind"] == "product"
    )
    rewards_credit_minor = _bp_of_nearest(rewards_base, WALLET_CREDIT_BP)
    view = {
        "cart_id": cart_id,
        "owner": cart["owner"] if cart else None,
        "currency": CURRENCY,
        "items": items,
        "count": len(items),
        "total_minor": total_minor,
        # Undiscounted sub-total behind the drawer's struck-through original.
        "original_total_minor": sum(i["line_full_total_minor"] for i in items),
        "split_mode": mode,
        "charity_name": charity_name,
        "rewards_label": WALLET_CREDIT_LABEL,
        "rewards_rate_bp": WALLET_CREDIT_BP,
        "rewards_credit_minor": rewards_credit_minor,
        "choice_coupon_minor": (
            CHOICE_COUPON_MINOR if items and flow == "store" else 0
        ),
    }
    view.update(totals)
    return view


def get_or_create_cart(
    cart_id: str, owner: str | None = None, split_mode: str = "default"
) -> dict[str, Any]:
    backend, _ = services()
    with backend.lifecycle.connection(transaction=True) as cx:
        _ensure_cart(cx, cart_id, owner)
        return _cart_view(cx, cart_id, split_mode)


def cart_view(cart_id: str, split_mode: str = "default") -> dict[str, Any]:
    backend, _ = services()
    with backend.lifecycle.connection() as cx:
        return _cart_view(cx, cart_id, split_mode)


def _cart_insert(
    cx: sqlite3.Connection,
    cart_id: str,
    kind: str,
    slug: str,
    amount_minor: int | None,
    qty: int = 1,
) -> None:
    if kind not in ("bundle", "product"):
        raise ValueError("kind must be 'bundle' or 'product'")
    _ensure_cart(cx, cart_id)
    if kind == "bundle":
        state = _tier_state(cx, slug, amount_minor if isinstance(amount_minor, int) else -1)
        if not isinstance(amount_minor, int) or isinstance(amount_minor, bool):
            raise ValueError("amount_minor (integer) is required for a bundle")
        if amount_minor < state["floor_minor"]:
            raise BelowFloor(state["floor_minor"])
        stored_amount: int | None = amount_minor
        qty = 1
    else:
        exists = cx.execute(
            "SELECT 1 FROM hb_products WHERE slug=?", (slug,)
        ).fetchone()
        if exists is None:
            raise NotFound(f"unknown product: {slug}")
        stored_amount = None  # products are always priced from the catalog
        qty = max(1, min(int(qty), MAX_CART_SIZE))
    existing = cx.execute(
        "SELECT * FROM hb_cart_items WHERE cart_id=? AND kind=? AND slug=?",
        (cart_id, kind, slug),
    ).fetchone()
    if existing is not None:
        if kind == "bundle":
            cx.execute(
                "UPDATE hb_cart_items SET amount_minor=? WHERE item_id=?",
                (stored_amount, existing["item_id"]),
            )
        return  # product re-add is a no-op: one entry per title
    count = cx.execute(
        "SELECT COUNT(*) FROM hb_cart_items WHERE cart_id=?", (cart_id,)
    ).fetchone()[0]
    if count >= MAX_CART_SIZE:
        raise CartLimitExceeded(f"cart is limited to {MAX_CART_SIZE} items")
    cx.execute(
        "INSERT INTO hb_cart_items (cart_id, kind, slug, amount_minor, qty)"
        " VALUES (?,?,?,?,?)",
        (cart_id, kind, slug, stored_amount, qty),
    )


def cart_add(
    cart_id: str,
    kind: str,
    slug: str,
    amount_minor: int | None = None,
) -> dict[str, Any]:
    backend, _ = services()
    with backend.lifecycle.connection(transaction=True) as cx:
        _cart_insert(cx, cart_id, kind, slug, amount_minor)
        return _cart_view(cx, cart_id)


def cart_update(
    cart_id: str,
    item_id: int,
    amount_minor: int | None = None,
    qty: int | None = None,
) -> dict[str, Any]:
    backend, _ = services()
    with backend.lifecycle.connection(transaction=True) as cx:
        row = cx.execute(
            "SELECT * FROM hb_cart_items WHERE item_id=? AND cart_id=?",
            (item_id, cart_id),
        ).fetchone()
        if row is None:
            raise NotFound(f"no such cart line: {item_id}")
        if row["kind"] == "bundle":
            if amount_minor is not None:
                if not isinstance(amount_minor, int) or isinstance(amount_minor, bool):
                    raise ValueError("amount_minor must be an integer")
                state = _tier_state(cx, row["slug"], amount_minor)
                if amount_minor < state["floor_minor"]:
                    raise BelowFloor(state["floor_minor"])
                cx.execute(
                    "UPDATE hb_cart_items SET amount_minor=? WHERE item_id=?",
                    (amount_minor, item_id),
                )
        else:
            if amount_minor is not None:
                raise ValueError("products are priced from the catalog")
            if qty is not None:
                qty = int(qty)
                if qty < 1:
                    raise ValueError("qty must be >= 1 (use cart_remove)")
                cx.execute(
                    "UPDATE hb_cart_items SET qty=? WHERE item_id=?",
                    (min(qty, MAX_CART_SIZE), item_id),
                )
        return _cart_view(cx, cart_id)


def cart_remove(item_id: int) -> dict[str, Any]:
    """Delete one line; returns a restore snapshot for the undo affordance."""

    backend, _ = services()
    with backend.lifecycle.connection(transaction=True) as cx:
        row = cx.execute(
            "SELECT * FROM hb_cart_items WHERE item_id=?", (item_id,)
        ).fetchone()
        if row is None:
            raise NotFound(f"no such cart line: {item_id}")
        cx.execute("DELETE FROM hb_cart_items WHERE item_id=?", (item_id,))
        snapshot = {
            "cart_id": row["cart_id"],
            "kind": row["kind"],
            "slug": row["slug"],
            "amount_minor": row["amount_minor"],
            "qty": row["qty"],
        }
        return {"snapshot": snapshot, "cart": _cart_view(cx, row["cart_id"])}


def cart_restore(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Undo a removal; the line is revalidated (floor, cap) on the way back."""

    if not isinstance(snapshot, dict):
        raise ValueError("snapshot must be the dict returned by cart_remove")
    backend, _ = services()
    with backend.lifecycle.connection(transaction=True) as cx:
        _cart_insert(
            cx,
            snapshot["cart_id"],
            snapshot["kind"],
            snapshot["slug"],
            snapshot.get("amount_minor"),
            qty=snapshot.get("qty", 1),
        )
        return _cart_view(cx, snapshot["cart_id"])


# ---------------------------------------------------------------------------
# checkout (local-sandbox payment through the seam ledger)
# ---------------------------------------------------------------------------
def _bp_of(minor: int, basis_points: int) -> int:
    """Truncated percentage of a minor amount, integer arithmetic only.

    Floor, not half-up: see the ``TAX_ORACLE_STORE`` note above -- the
    captured store drawer shows 137 -> 17 (17.81 truncated), which half-up
    would have rendered as 18. The bundle oracle (1425 -> 185) holds either
    way, so this helper is pinned by the store observation.
    """

    if minor <= 0 or basis_points <= 0:
        return 0
    return (minor * basis_points) // 10000


def _bp_of_nearest(minor: int, basis_points: int) -> int:
    """Nearest-cent percentage, for the rewards line only.

    The captured wallet-credit line rounds where the tax line truncates
    (137 * 10% = 13.7 shown as CA$0.14); see ``WALLET_CREDIT_ORACLE``.
    """

    if minor <= 0 or basis_points <= 0:
        return 0
    return (minor * basis_points + 5000) // 10000


def _charity_fraction_bp(entry: dict[str, Any], mode: str) -> int:
    """The charity party's share of the order, in basis points.

    ``sibling_split`` is the frozen default-donation ratio and
    ``extra_charity_split`` the "Extra to Charity" ratio (both sum to 1.0
    across the parties); the frontend split rows use the same two keys.
    """

    key = "extra_charity_split" if mode == "extra-charity" else "sibling_split"
    return int(round(float(entry.get(key) or 0.0) * 10000))


def _charity_party(parties: list[dict[str, Any]]) -> dict[str, Any] | None:
    for entry in parties or []:
        if entry.get("class") == CHARITY_SPLIT_CLASS:
            return entry
    return None


def _bundle_splits(cx: sqlite3.Connection, slug: str) -> list[dict[str, Any]]:
    row = cx.execute(
        "SELECT splits_json FROM hb_bundles WHERE slug=?", (slug,)
    ).fetchone()
    if row is None or not row["splits_json"]:
        return []
    parties = json.loads(row["splits_json"])
    return parties if isinstance(parties, list) else []


def _charity_of(
    cx: sqlite3.Connection,
    bundle_amounts: list[tuple[str, int]],
    mode: str,
    allocations: dict[str, int] | None = None,
) -> tuple[int, str | None]:
    """(charity minor, charity name) for an order, from the bundles' own splits.

    Store products carry no charity split, so a product-only order donates
    nothing. Under ``custom`` the buyer's own allocation to the charity party
    IS the charity amount; otherwise it is the frozen split fraction of each
    bundle line. Never a guessed rate.
    """

    name: str | None = None
    charity_minor = 0
    for slug, amount in bundle_amounts:
        entry = _charity_party(_bundle_splits(cx, slug))
        if entry is None:
            continue
        if name is None:
            name = str(entry.get("name") or "").strip() or None
        if allocations is None:
            charity_minor += _bp_of(amount, _charity_fraction_bp(entry, mode))
    if allocations is not None:
        charity_minor = int(allocations.get(CHARITY_SPLIT_CLASS, 0) or 0)
    return charity_minor, name


def order_totals(
    subtotal_minor: int, charity_minor: int, *, flow: str = TAX_FLOW_DEFAULT
) -> dict[str, Any]:
    """The Order Summary quadruple: subtotal, charity, tax line, grand total.

    Single source of truth for the review summary, the placed order row and
    the confirmation, so all three always agree. See ``TAX_ORACLE`` (bundle
    checkout) and ``TAX_ORACLE_STORE`` (store cart drawer) for the captured
    tuples this reproduces.

    ``flow`` selects the captured label for the surface the numbers are
    rendered on -- ``"store"`` -> ``Sales Tax``, ``"bundle"`` -> ``HST``. The
    rate and the rounding are identical; only the label differs, and it is
    carried in the payload so no frontend hardcodes one of the two.
    """

    tax_flow = flow if flow in TAX_FLOW_LABELS else TAX_FLOW_DEFAULT
    taxable_minor = max(0, int(subtotal_minor) - int(charity_minor))
    tax_minor = _bp_of(taxable_minor, TAX_RATE_BP)
    return {
        "subtotal_minor": int(subtotal_minor),
        "charity_minor": int(charity_minor),
        "taxable_minor": taxable_minor,
        "tax_flow": tax_flow,
        "tax_label": TAX_FLOW_LABELS[tax_flow],
        "tax_rate_bp": TAX_RATE_BP,
        "tax_minor": tax_minor,
        "grand_total_minor": int(subtotal_minor) + tax_minor,
    }


def _order_no(purchase_id: int) -> str:
    # Run orders live in the HB2026 09xxxx span; seeded history is 08xxxx.
    return f"HB{2026090000 + purchase_id}"


def _payment_owner(owner: str | None, cart_id: str) -> str:
    basis = owner if owner else f"guest:{cart_id}"
    return "hb-owner:" + hashlib.sha256(basis.encode()).hexdigest()[:32]


def _resolve_splits(
    cx: sqlite3.Connection,
    bundle_slugs: list[str],
    splits: dict[str, Any] | None,
    total_minor: int,
) -> str:
    """Order split metadata: mode + frozen party shapes (+ custom amounts).

    Default / extra-charity modes store the frozen split fractions verbatim
    (they are ratios, never money). Custom allocations are integer minor
    units validated to sum to the order total; they never change the charge.
    """

    frozen = {slug: _bundle_splits(cx, slug) for slug in bundle_slugs}
    if splits is None:
        return json.dumps({"mode": "default", "bundles": frozen})
    if not isinstance(splits, dict):
        raise SplitInvalid("splits must be an object")
    reject_payment_keys(splits)
    mode = splits.get("mode", "default")
    if mode not in SPLIT_MODES:
        raise SplitInvalid(f"unknown split mode: {mode}")
    stored: dict[str, Any] = {"mode": mode, "bundles": frozen}
    if mode == "custom":
        allocations = splits.get("allocations")
        if not isinstance(allocations, dict) or not allocations:
            raise SplitInvalid("custom splits require allocations")
        for party, amount in allocations.items():
            if (
                not isinstance(party, str)
                or not isinstance(amount, int)
                or isinstance(amount, bool)
                or amount < 0
            ):
                raise SplitInvalid("allocations must map parties to minor ints")
        if sum(allocations.values()) != total_minor:
            raise SplitInvalid("custom allocations must sum to the order total")
        stored["allocations"] = dict(allocations)
    return json.dumps(stored)


def _valid_email(value: Any) -> bool:
    """Same shape the review's inline gift-email error checks client-side."""

    if not isinstance(value, str):
        return False
    value = value.strip()
    if not value or len(value) > 254 or value.count("@") != 1:
        return False
    local, _, domain = value.partition("@")
    return bool(local) and bool(domain) and " " not in value


def place_order(
    cart_id: str,
    owner: str | None,
    scenario_id: str,
    delivery_kind: str = "self",
    gift_email: str | None = None,
    splits: dict[str, Any] | None = None,
    processor: str = "card",
    gift_mode: str | None = None,
    gift_anonymous: bool = False,
    leaderboard_name: str | None = None,
) -> dict[str, Any]:
    """Attempt local-sandbox payment and atomically create one purchase.

    The amount is recomputed server-side from the persisted cart; bundle
    lines are re-validated against the frozen floor. An approved attempt
    creates the purchase, its items and synthetic keys and clears the cart
    in ONE transaction via the seam's create_intent / attempt /
    consume_approval flow. Declined / retryable attempts raise
    :class:`PaymentDeclined` / :class:`PaymentRetryable` after the ledger
    records the attempt — no business rows are written and the cart stays.

    Review-surface inputs captured by walk tr-001 (see handoff-findings):
    ``processor`` is the chosen ``processor-type`` label (never an instrument
    — the sandbox scenario id remains the only payment input), ``gift_mode``
    /``gift_email``/``gift_anonymous`` are the gifting opt-in triple, and
    ``leaderboard_name`` the leaderboard opt-in. The summary quadruple
    (subtotal, charity, tax, grand total) is computed by
    :func:`order_totals` and stored on the row, so the review, the order
    record and the confirmation can never disagree.
    """

    if not isinstance(scenario_id, str) or not scenario_id.strip():
        raise ValueError("scenario_id is required")
    if processor not in PROCESSORS:
        raise ProcessorInvalid(f"unknown payment processor: {processor}")
    if gift_mode is None:
        # Legacy flat form: delivery_kind="gift" means gift-by-email.
        gift_mode = "email" if delivery_kind == "gift" else "none"
    if gift_mode not in GIFT_MODES:
        raise ValueError(f"unknown gift mode: {gift_mode}")
    delivery_kind = "self" if gift_mode == "none" else "gift"
    if gift_mode == "email":
        if not _valid_email(gift_email):
            raise GiftRecipientInvalid(
                "gift-by-email requires a correctly formatted email address"
            )
        gift_email = gift_email.strip()
    else:
        # The gift-link branch mails the link to the buyer: no recipient.
        gift_email = None
    gift_anonymous = bool(gift_anonymous) and gift_mode != "none"
    if leaderboard_name is None or leaderboard_name == "":
        leaderboard_name = None
    elif isinstance(leaderboard_name, str):
        leaderboard_name = leaderboard_name.strip()[:LEADERBOARD_NAME_MAX] or None
    else:
        raise ValueError("leaderboard_name must be a string")
    reject_payment_keys(splits)

    backend, _ = services()
    pay_currency = backend.config.payments["currency"]
    outcome: str | None = None
    order_no: str | None = None
    with backend.lifecycle.connection(transaction=True) as cx:
        cart = _ensure_cart(cx, cart_id, owner)
        view = _cart_view(cx, cart_id)
        if not view["items"]:
            raise EmptyCart("cart is empty")
        lines: list[dict[str, Any]] = []
        total_minor = 0
        for item in view["items"]:
            if item["kind"] == "bundle":
                state = _tier_state(cx, item["slug"], item["amount_minor"])
                if not state["valid"]:
                    raise BelowFloor(state["floor_minor"])
                amount = int(item["amount_minor"])
                entitlements = [
                    (row["machine_name"], row["human_name"])
                    for row in state["unlocked_items"]
                ]
            else:
                amount = int(item["unit_price_minor"]) * int(item["qty"])
                product = cx.execute(
                    "SELECT machine_name, human_name FROM hb_products"
                    " WHERE slug=?",
                    (item["slug"],),
                ).fetchone()
                entitlements = [(product["machine_name"], product["human_name"])]
            total_minor += amount
            lines.append(
                {
                    "kind": item["kind"],
                    "slug": item["slug"],
                    "name": item["name"],
                    "amount_minor": amount,
                    "qty": item["qty"],
                    "entitlements": entitlements,
                }
            )
        splits_json = _resolve_splits(
            cx,
            [line["slug"] for line in lines if line["kind"] == "bundle"],
            splits,
            total_minor,
        )
        splits_doc = json.loads(splits_json)
        charity_minor, charity_name = _charity_of(
            cx,
            [
                (line["slug"], line["amount_minor"])
                for line in lines
                if line["kind"] == "bundle"
            ],
            splits_doc.get("mode", "default"),
            splits_doc.get("allocations")
            if splits_doc.get("mode") == "custom"
            else None,
        )
        totals = order_totals(
            total_minor,
            charity_minor,
            flow=(
                "bundle"
                if any(line["kind"] == "bundle" for line in lines)
                else "store"
            ),
        )
        # The buyer is charged the summary Total (subtotal + tax line); the
        # donation split is over the pre-tax amount, exactly as captured.
        charge_minor = totals["grand_total_minor"]
        pay_owner = _payment_owner(owner, cart_id)
        fingerprint = hashlib.sha256(
            json.dumps(
                [
                    [line["kind"], line["slug"], line["amount_minor"], line["qty"]]
                    for line in lines
                ]
                + [["charge", charge_minor, charity_minor]],
                sort_keys=True,
            ).encode()
        ).hexdigest()
        cart_digest = hashlib.sha256(cart_id.encode()).hexdigest()[:24]
        seq = int(cart["order_seq"])
        flow = backend.payments.create_intent(
            owner=pay_owner,
            amount_minor=charge_minor,
            currency=pay_currency,
            fingerprint=fingerprint,
            idempotency_key=f"hb.create:{cart_digest}:{seq}:{fingerprint[:24]}",
            connection=cx,
        )
        attempt = backend.payments.attempt(
            flow_id=flow["flow_id"],
            owner=pay_owner,
            amount_minor=charge_minor,
            currency=pay_currency,
            fingerprint=fingerprint,
            scenario_id=scenario_id,
            idempotency_key=(
                f"hb.attempt:{cart_digest}:{seq}:{fingerprint[:24]}:{scenario_id}"
            ),
            connection=cx,
        )
        if attempt["status"] != "APPROVED":
            # Commit only the seam's ledger record of the failed attempt;
            # the typed error is raised after the transaction closes so no
            # business write can ever accompany a non-approved outcome.
            outcome = attempt["status"]
        else:
            consumed = backend.payments.consume_approval(
                cx,
                flow_id=flow["flow_id"],
                owner=pay_owner,
                amount_minor=charge_minor,
                currency=pay_currency,
                fingerprint=fingerprint,
            )
            cx.execute(
                "INSERT INTO hb_purchases (order_no, owner, created_at,"
                " status, total_minor, charged_minor, scenario, delivery_kind,"
                " gift_email, splits_json, payment_flow_id,"
                " payment_attempt_id, processor, gift_mode, gift_anonymous,"
                " leaderboard_name, tax_minor, charity_minor, charity_name)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    f"PENDING-{flow['flow_id']}",
                    owner,
                    FROZEN_CLOCK_UTC,
                    "Completed",
                    total_minor,
                    charge_minor,
                    scenario_id,
                    delivery_kind,
                    gift_email,
                    splits_json,
                    flow["flow_id"],
                    consumed["attempt_id"],
                    processor,
                    gift_mode,
                    1 if gift_anonymous else 0,
                    leaderboard_name,
                    totals["tax_minor"],
                    charity_minor,
                    charity_name,
                ),
            )
            purchase_id = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
            order_no = _order_no(purchase_id)
            cx.execute(
                "UPDATE hb_purchases SET order_no=? WHERE id=?",
                (order_no, purchase_id),
            )
            for line in lines:
                cx.execute(
                    "INSERT INTO hb_purchase_items (order_no, kind, slug,"
                    " human_name, amount_minor, qty) VALUES (?,?,?,?,?,?)",
                    (
                        order_no,
                        line["kind"],
                        line["slug"],
                        line["name"],
                        line["amount_minor"],
                        line["qty"],
                    ),
                )
                _insert_purchase_keys(cx, order_no, line["entitlements"])
            cx.execute(
                "DELETE FROM hb_cart_items WHERE cart_id=?", (cart_id,)
            )
            cx.execute(
                "UPDATE hb_carts SET order_seq=order_seq+1 WHERE cart_id=?",
                (cart_id,),
            )
            purchase = _purchase_dict(cx, owner, order_no)
    if outcome == "DECLINED":
        raise PaymentDeclined(scenario_id)
    if outcome is not None:
        raise PaymentRetryable(scenario_id)
    return {"placed": True, "order_no": order_no, "purchase": purchase}


# ---------------------------------------------------------------------------
# account surface: purchases / keys / library / wishlist
# ---------------------------------------------------------------------------
def _owner_clause(owner: str | None) -> tuple[str, tuple[Any, ...]]:
    if owner is None:
        return "owner IS NULL", ()
    return "owner=?", (owner,)


def _purchase_dict(
    cx: sqlite3.Connection, owner: str | None, order_no: str
) -> dict[str, Any]:
    clause, params = _owner_clause(owner)
    purchase = cx.execute(
        f"SELECT * FROM hb_purchases WHERE order_no=? AND {clause}",
        (order_no, *params),
    ).fetchone()
    if purchase is None:
        raise NotFound(f"no such order: {order_no}")
    items = cx.execute(
        "SELECT * FROM hb_purchase_items WHERE order_no=? ORDER BY id",
        (order_no,),
    ).fetchall()
    keys = cx.execute(
        "SELECT k.*, pr.payload_json FROM hb_keys k"
        " LEFT JOIN hb_products pr ON pr.machine_name=k.machine_name"
        " WHERE k.order_no=? ORDER BY k.rowid",
        (order_no,),
    ).fetchall()
    purchase_flow = (
        "bundle" if any(item["kind"] == "bundle" for item in items) else "store"
    )
    return {
        "order_no": purchase["order_no"],
        "owner": purchase["owner"],
        "created_at": purchase["created_at"],
        "status": purchase["status"],
        "currency": CURRENCY,
        # total_minor is the pre-tax item subtotal (what the donation split
        # is taken over); charged_minor is the summary Total.
        "total_minor": purchase["total_minor"],
        "subtotal_minor": purchase["total_minor"],
        # Same captured rate, captured label per flow (see TAX_FLOW_LABELS).
        "tax_flow": purchase_flow,
        "tax_label": TAX_FLOW_LABELS[purchase_flow],
        "tax_minor": purchase["tax_minor"],
        "charity_minor": purchase["charity_minor"],
        "charity_name": purchase["charity_name"],
        "grand_total_minor": purchase["total_minor"] + purchase["tax_minor"],
        "charged_minor": purchase["charged_minor"],
        "scenario": purchase["scenario"],
        "processor": purchase["processor"],
        "delivery_kind": purchase["delivery_kind"],
        "gift_mode": purchase["gift_mode"],
        "gift_email": purchase["gift_email"],
        "gift_anonymous": bool(purchase["gift_anonymous"]),
        "leaderboard_name": purchase["leaderboard_name"],
        "splits": json.loads(purchase["splits_json"])
        if purchase["splits_json"]
        else None,
        "items": [
            {
                "kind": item["kind"],
                "slug": item["slug"],
                "human_name": item["human_name"],
                "amount_minor": item["amount_minor"],
                "qty": item["qty"],
            }
            for item in items
        ],
        "keys": [
            {
                "machine_name": key["machine_name"],
                "human_name": key["human_name"],
                "revealed": bool(key["revealed"]),
                # Key material stays server-side until explicitly revealed.
                "key_code": key["key_code"] if key["revealed"] else None,
                # Delivery type for the keys table's "Type" column; empty for
                # bundle entitlements (see :func:`library`).
                "delivery_methods": (
                    json.loads(key["payload_json"]).get("delivery_methods", [])
                    if key["payload_json"]
                    else []
                ),
            }
            for key in keys
        ],
    }


def list_purchases(owner: str | None) -> list[dict[str, Any]]:
    backend, _ = services()
    clause, params = _owner_clause(owner)
    with backend.lifecycle.connection() as cx:
        rows = cx.execute(
            f"SELECT order_no FROM hb_purchases WHERE {clause} ORDER BY id DESC",
            params,
        ).fetchall()
        return [_purchase_dict(cx, owner, row["order_no"]) for row in rows]


def get_purchase(owner: str | None, order_no: str) -> dict[str, Any]:
    backend, _ = services()
    with backend.lifecycle.connection() as cx:
        return _purchase_dict(cx, owner, order_no)


def reveal_key(owner: str | None, order_no: str, machine_name: str) -> str:
    """Reveal (idempotently) one synthetic key the owner is entitled to."""

    backend, _ = services()
    clause, params = _owner_clause(owner)
    with backend.lifecycle.connection(transaction=True) as cx:
        row = cx.execute(
            "SELECT k.key_code, k.revealed FROM hb_keys k"
            f" JOIN hb_purchases p ON p.order_no=k.order_no AND p.{clause}"
            " WHERE k.order_no=? AND k.machine_name=?",
            (*params, order_no, machine_name),
        ).fetchone()
        if row is None:
            raise NotFound(f"no key for {machine_name} on {order_no}")
        if not row["revealed"]:
            cx.execute(
                "UPDATE hb_keys SET revealed=1 WHERE order_no=? AND machine_name=?",
                (order_no, machine_name),
            )
        return row["key_code"]


def library(owner: str | None) -> list[dict[str, Any]]:
    """Entitlements from completed self-delivery purchases (first-seen wins).

    Each entry also carries what the captured library controls need: the
    order timestamp (the "Recently updated" sort) and, where the entitlement
    resolves to a catalog product by machine name, its platform and DRM lists
    (the ``Platform`` select and the keys table's ``Type`` column). Bundle
    entitlements are named by the bundle's own item machine names, which the
    store catalog does not carry, so their platform lists stay empty rather
    than being guessed.
    """

    backend, _ = services()
    clause, params = _owner_clause(owner)
    with backend.lifecycle.connection() as cx:
        rows = cx.execute(
            "SELECT k.machine_name, k.human_name, k.revealed, k.order_no,"
            " p.created_at, pr.payload_json"
            " FROM hb_keys k JOIN hb_purchases p ON p.order_no=k.order_no"
            " LEFT JOIN hb_products pr ON pr.machine_name=k.machine_name"
            f" WHERE p.{clause} AND p.delivery_kind='self'"
            " AND p.status='Completed' ORDER BY p.id, k.rowid",
            params,
        ).fetchall()
    seen: set[str] = set()
    entries: list[dict[str, Any]] = []
    for row in rows:
        if row["machine_name"] in seen:
            continue
        seen.add(row["machine_name"])
        payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
        entries.append(
            {
                "machine_name": row["machine_name"],
                "human_name": row["human_name"],
                "order_no": row["order_no"],
                "revealed": bool(row["revealed"]),
                "created_at": row["created_at"],
                "platforms": payload.get("platforms", []),
                "drm": payload.get("drm", []),
                "delivery_methods": payload.get("delivery_methods", []),
            }
        )
    return entries


def wishlist_add(owner: str, slug: str) -> list[dict[str, Any]]:
    if not owner:
        raise ValueError("wishlist requires an owner")
    backend, _ = services()
    with backend.lifecycle.connection(transaction=True) as cx:
        if cx.execute(
            "SELECT 1 FROM hb_products WHERE slug=?", (slug,)
        ).fetchone() is None:
            raise NotFound(f"unknown product: {slug}")
        count = cx.execute(
            "SELECT COUNT(*) FROM hb_wishlist WHERE owner=?", (owner,)
        ).fetchone()[0]
        already = cx.execute(
            "SELECT 1 FROM hb_wishlist WHERE owner=? AND slug=?", (owner, slug)
        ).fetchone()
        if already is None and count >= MAX_WISHLIST_SIZE:
            raise WishlistLimitExceeded(
                f"wishlist is limited to {MAX_WISHLIST_SIZE} items"
            )
        cx.execute(
            "INSERT OR IGNORE INTO hb_wishlist (owner, slug, added_at)"
            " VALUES (?,?,?)",
            (owner, slug, FROZEN_CLOCK_UTC),
        )
        return _wishlist(cx, owner)


def wishlist_remove(owner: str, slug: str) -> list[dict[str, Any]]:
    backend, _ = services()
    with backend.lifecycle.connection(transaction=True) as cx:
        cx.execute(
            "DELETE FROM hb_wishlist WHERE owner=? AND slug=?", (owner, slug)
        )
        return _wishlist(cx, owner)


def wishlist_list(owner: str) -> list[dict[str, Any]]:
    backend, _ = services()
    with backend.lifecycle.connection() as cx:
        return _wishlist(cx, owner)


def _wishlist(cx: sqlite3.Connection, owner: str) -> list[dict[str, Any]]:
    """Wishlist rows carrying everything the captured wishlist entity shows.

    ``source-auth-scratch/walk-671/wishlist-populated`` renders each saved
    product as a full store entity (image, title, platform + DRM icon lists,
    discount gem with its breakdown, price button), so the row has to expose
    the same fields the search tile does.
    """

    rows = cx.execute(
        "SELECT w.slug, p.* FROM hb_wishlist w JOIN hb_products p ON p.slug=w.slug"
        " WHERE w.owner=? ORDER BY w.rowid",
        (owner,),
    ).fetchall()
    entries: list[dict[str, Any]] = []
    for row in rows:
        payload = _payload(row)
        entries.append(
            {
                "slug": row["slug"],
                "machine_name": row["machine_name"],
                "human_name": row["human_name"],
                "current_price_minor": row["current_price_minor"],
                "full_price_minor": row["full_price_minor"],
                "discount_pct": row["discount_pct"],
                "platforms": payload.get("platforms", []),
                "drm": payload.get("drm", []),
                "media": payload.get("media", {}),
            }
        )
    return entries


# --------------------------------------------------------------------------
# account preferences (/user/settings)
# --------------------------------------------------------------------------
# The captured /user/settings contact-preference form, in captured order:
# (checkbox name, its captured label, captured default state). Only
# ``abandoned_purchase_notification_emails`` arrives checked.
SUBSCRIPTION_PREFS: tuple[tuple[str, str, bool], ...] = (
    (
        "bundle_emails",
        "Main page bundles, special Humble Store sales, and important updates",
        False,
    ),
    ("monthly_emails", "Humble Choice", False),
    ("ebook_emails", "Humble Book Bundles", False),
    ("software_emails", "Humble Software Bundles", False),
    ("mobile_emails", "Humble Mobile Bundles", False),
    ("store_emails", "Humble Store sales and other store events", False),
    ("publishing_emails", "Humble Games", False),
    ("wish_list_notification_emails", "Wish list notifications", False),
    (
        "abandoned_purchase_notification_emails",
        "Incomplete purchase reminders",
        True,
    ),
    ("remind_me_notifications", "Bundle Reminders", False),
)
SUBSCRIPTION_NAMES = tuple(name for name, _label, _default in SUBSCRIPTION_PREFS)
# Captured charity-preference value on the settings page.
DEFAULT_CHARITY_PREFERENCE = "Oceana"
# Captured wallet block: currency and both amounts were zero on the walked
# account, and the wallet has no local top-up path (payments are sandbox-only).
WALLET_CURRENCY = "CAD"
WALLET_FUNDS_MINOR = 0
WALLET_EXPIRING_MINOR = 0
# Captured "Total Donated" community figure on the settings page.
COMMUNITY_DONATED_DISPLAY = "US$282,000,000"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+$")


class DeliveryEmailInvalid(ValueError):
    """The settings email field did not hold a correctly formatted address."""


def _default_prefs() -> dict[str, Any]:
    return {
        "delivery_email": None,
        "subscriptions": {
            name: default for name, _label, default in SUBSCRIPTION_PREFS
        },
        "charity_preference": DEFAULT_CHARITY_PREFERENCE,
    }


def account_prefs(owner: str | None) -> dict[str, Any]:
    """Settings-page preferences for ``owner``, defaults filled in.

    ``delivery_email`` is ``None`` until the account edits it; the caller
    falls back to the signed-in address, which is what the source shows in
    the ``Email Address`` field.
    """

    prefs = _default_prefs()
    if not owner:
        return prefs
    backend, _ = services()
    with backend.lifecycle.connection() as cx:
        row = cx.execute(
            "SELECT * FROM hb_account_prefs WHERE owner=?", (owner,)
        ).fetchone()
    if row is None:
        return prefs
    prefs["delivery_email"] = row["delivery_email"]
    prefs["charity_preference"] = (
        row["charity_preference"] or DEFAULT_CHARITY_PREFERENCE
    )
    stored = json.loads(row["subscriptions_json"] or "{}")
    for name in SUBSCRIPTION_NAMES:
        if name in stored:
            prefs["subscriptions"][name] = bool(stored[name])
    return prefs


def _write_prefs(owner: str, prefs: dict[str, Any]) -> dict[str, Any]:
    backend, _ = services()
    with backend.lifecycle.connection(transaction=True) as cx:
        cx.execute(
            "INSERT INTO hb_account_prefs (owner, delivery_email,"
            " subscriptions_json, charity_preference) VALUES (?,?,?,?)"
            " ON CONFLICT(owner) DO UPDATE SET delivery_email=excluded"
            ".delivery_email, subscriptions_json=excluded.subscriptions_json,"
            " charity_preference=excluded.charity_preference",
            (
                owner,
                prefs["delivery_email"],
                json.dumps(prefs["subscriptions"]),
                prefs["charity_preference"],
            ),
        )
    return prefs


def set_delivery_email(owner: str, email: str) -> dict[str, Any]:
    """Update the account's delivery (contact) address.

    A digital order has no postal address: the source's only editable
    delivery destination is the account's email address, whose ``Update``
    control lives on /user/settings. The vendored auth store owns the
    sign-in credential and exposes no email-change entry point, so this
    writes a clone-side delivery address that the checkout review honours;
    the sign-in address is unchanged (recorded as a known difference).
    """

    if not owner:
        raise ValueError("delivery email requires an owner")
    candidate = (email or "").strip()
    if not _EMAIL_RE.match(candidate) or len(candidate) > 254:
        raise DeliveryEmailInvalid(
            "Please enter a correctly formatted email address"
        )
    prefs = account_prefs(owner)
    prefs["delivery_email"] = candidate
    return _write_prefs(owner, prefs)


def set_contact_prefs(
    owner: str,
    subscriptions: dict[str, Any] | None = None,
    charity_preference: str | None = None,
) -> dict[str, Any]:
    """Update the contact-preference checkboxes / charity preference."""

    if not owner:
        raise ValueError("contact preferences require an owner")
    prefs = account_prefs(owner)
    if subscriptions is not None:
        if not isinstance(subscriptions, dict):
            raise ValueError("subscriptions must be an object")
        for name, value in subscriptions.items():
            if name not in prefs["subscriptions"]:
                raise ValueError(f"unknown subscription: {name}")
            prefs["subscriptions"][name] = bool(value)
    if charity_preference is not None:
        label = str(charity_preference).strip()
        if not label or len(label) > 120:
            raise ValueError("charity preference must be a short label")
        prefs["charity_preference"] = label
    return _write_prefs(owner, prefs)


def delivery_email(owner: str | None, fallback: str) -> str:
    """The address a digital order is delivered to (settings override wins)."""

    return account_prefs(owner)["delivery_email"] or fallback


# --------------------------------------------------------------------------
# accounts / sessions (library auth seam; mechanism shared with prior sites)
# --------------------------------------------------------------------------
class LoginInvalid(ValueError):
    """Login input was malformed (missing / short email or password)."""


class LoginRejected(ValueError):
    """Credentials were syntactically valid but did not authenticate."""


class AuthFlowError(ValueError):
    """An account-flow step failed; ``status`` is the HTTP code to surface."""

    def __init__(self, message: str, *, status: int = 400, code: str = "error") -> None:
        super().__init__(message)
        self.status = status
        self.code = code


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

    The returned token is resolved before it is handed back. A signed-in
    response whose token does not resolve was observed twice during the task
    audit: the caller sets a cookie for a session the store does not serve, and
    the next request looks anonymous, which would silently break the sign-in and
    end-to-end journeys. The rotation itself lives in the vendored auth store,
    which this site must not modify, so the check and one retry live here.
    """
    _, auth = services()

    def attempt() -> dict[str, Any]:
        session_token = token
        if not session_token or auth.resolve_session(session_token) is None:
            session_token = auth.create_anonymous_session()
        return auth.sign_in(session_token, email=email, password=password)

    try:
        result = attempt()
        if auth.resolve_session(result.get("session_token")) is None:
            result = attempt()
            if auth.resolve_session(result.get("session_token")) is None:
                raise LoginRejected("the signed-in session could not be established")
        return result
    except AuthValidationError as exc:
        raise LoginInvalid(str(exc)) from exc
    except AuthRateLimited as exc:
        raise LoginRejected(str(exc)) from exc
    except (AuthRejected, AuthError) as exc:
        raise LoginRejected("credentials are invalid") from exc


def logout(token: str | None) -> None:
    _, auth = services()
    auth.sign_out(token)


def _live_session(auth: Any, token: str | None) -> str:
    if token and auth.resolve_session(token) is not None:
        return token
    return auth.create_anonymous_session()


def _sandbox_code(auth: Any, token: str, purpose: str) -> str | None:
    """OTP surfaced from the offline outbox (LOCAL_ONLY) so demo flows finish.

    The deployed profile really sends mail and this is None; offline the code
    is surfaced honestly as a sandbox aid, never as real mail.
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
    except AuthError as exc:
        raise AuthFlowError("An account with that email already exists.",
                            status=409, code="conflict") from exc
    return {"session_token": st,
            "sandbox_code": _sandbox_code(auth, st, "registration"),
            "mail_mode": getattr(auth, "mail_mode", None)}


def register_complete(token: str | None, code: str) -> dict[str, Any]:
    """Verify the OTP and create the account (signs in); sign_in shape."""
    _, auth = services()
    if not token:
        raise AuthFlowError("Your session expired. Please start over.",
                            status=400, code="no_session")
    try:
        auth.verify_registration_code(token, code)
        return auth.complete_registration(token)
    except AuthValidationError as exc:
        raise AuthFlowError(str(exc), status=422, code="invalid") from exc
    except AuthError as exc:
        raise AuthFlowError("That verification code is incorrect or expired.",
                            status=400, code="bad_code") from exc


def password_reset_start(token: str | None, email: str) -> dict[str, Any]:
    """Begin password reset; generic acceptance avoids account enumeration."""
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
        pass
    return {"session_token": st,
            "sandbox_code": _sandbox_code(auth, st, "password-reset")}


def password_reset_complete(token: str | None, code: str,
                            new_password: str) -> str:
    """Verify the OTP and set the new password (signs in); returns new token."""
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
