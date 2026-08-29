"""Cart semantics: the observed MAX_CART_SIZE cap (invariant ``cart-cap``),
line math, and remove/undo."""

import json
from pathlib import Path

import pytest

SEED_PATH = Path(__file__).resolve().parents[1] / "backend" / "seed_data.json"
ANCHOR = "yes-chef-cooking-bundle"


def _product_slugs(n: int) -> list[str]:
    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    return [product["slug"] for product in seed["products"][:n]]


def test_cart_size_cap(db) -> None:
    """The 21st line is refused with the typed cap error; the cart keeps 20."""

    assert db.MAX_CART_SIZE == 20
    slugs = _product_slugs(21)
    for slug in slugs[:20]:
        db.cart_add("cart-cap", "product", slug)
    assert db.cart_view("cart-cap")["count"] == 20

    with pytest.raises(db.CartLimitExceeded):
        db.cart_add("cart-cap", "product", slugs[20])
    assert db.cart_view("cart-cap")["count"] == 20

    # The cap also holds for the restore path.
    with pytest.raises(db.CartLimitExceeded):
        db.cart_restore(
            {"cart_id": "cart-cap", "kind": "product", "slug": slugs[20], "qty": 1}
        )
    assert db.cart_view("cart-cap")["count"] == 20


def test_cart_lines_and_totals(db) -> None:
    """Bundle lines carry the chosen amount; product lines price from the
    catalog; totals are integer minor sums."""

    view = db.cart_add("cart-math", "bundle", ANCHOR, amount_minor=1500)
    assert view["total_minor"] == 1500
    bundle_line = view["items"][0]
    assert bundle_line["unlocked_count"] == 7
    assert bundle_line["total_count"] == 16

    product = db.get_product("bridge-constructor-portal")
    view = db.cart_add("cart-math", "product", "bridge-constructor-portal")
    assert view["count"] == 2
    assert view["total_minor"] == 1500 + product["current_price_minor"]
    assert view["currency"] == "CAD"

    # Re-adding the same product is a no-op (one entry per title).
    view = db.cart_add("cart-math", "product", "bridge-constructor-portal")
    assert view["count"] == 2

    # Re-adding the bundle updates its amount (revalidated against the floor).
    view = db.cart_add("cart-math", "bundle", ANCHOR, amount_minor=2219)
    assert view["count"] == 2
    assert view["items"][0]["amount_minor"] == 2219
    with pytest.raises(db.BelowFloor):
        db.cart_update(
            "cart-math", view["items"][0]["item_id"], amount_minor=100
        )

    # qty updates re-price product lines server-side.
    product_line = view["items"][1]
    view = db.cart_update("cart-math", product_line["item_id"], qty=3)
    assert view["items"][1]["qty"] == 3
    assert view["items"][1]["line_total_minor"] == (
        3 * product["current_price_minor"]
    )

    with pytest.raises(db.NotFound):
        db.cart_add("cart-math", "product", "no-such-product-websitebench")


def test_cart_remove_returns_restorable_snapshot(db) -> None:
    view = db.cart_add("cart-undo", "bundle", ANCHOR, amount_minor=1803)
    item_id = view["items"][0]["item_id"]

    removed = db.cart_remove(item_id)
    assert removed["cart"]["items"] == []
    snapshot = removed["snapshot"]
    assert snapshot["slug"] == ANCHOR
    assert snapshot["amount_minor"] == 1803

    restored = db.cart_restore(snapshot)
    assert restored["count"] == 1
    assert restored["items"][0]["amount_minor"] == 1803
    assert restored["items"][0]["unlocked_count"] == 13

    with pytest.raises(db.NotFound):
        db.cart_remove(999_999)  # unknown line id


def test_wishlist_roundtrip(db) -> None:
    owner = db.DEMO_OWNER
    assert db.wishlist_list(owner) == []
    entries = db.wishlist_add(owner, "bridge-constructor-portal")
    assert [e["slug"] for e in entries] == ["bridge-constructor-portal"]
    # Idempotent add, ordered by insertion.
    entries = db.wishlist_add(owner, "bridge-constructor-portal")
    assert len(entries) == 1
    entries = db.wishlist_add(owner, "portal-knights")
    assert [e["slug"] for e in entries] == [
        "bridge-constructor-portal",
        "portal-knights",
    ]
    entries = db.wishlist_remove(owner, "bridge-constructor-portal")
    assert [e["slug"] for e in entries] == ["portal-knights"]
    with pytest.raises(db.NotFound):
        db.wishlist_add(owner, "no-such-product-websitebench")


DRAWER_PRODUCT = "bridge-constructor-portal-portal-proficiency"


def test_store_tax_line_truncates_and_both_oracles_hold(db) -> None:
    """rounding oracle: the captured store drawer discriminates floor from
    half-up where the bundle checkout could not.

    Store drawer (walk-671, one product): Sub-Total CA$1.37, Sales Tax
    CA$0.17, Total CA$1.54. 137 * 13% = 17.81, so half-up would have shown 18
    and the source's own 137 + 17 = 154 could not hold. Bundle review
    (walk tr-001): (1500 - 75) * 13% = 185.25 -> 185, Total CA$16.85 -- true
    under floor *and* half-up, which is why it never pinned the rounding.
    """

    assert db.TAX_RATE_BP == 1300

    store = db.TAX_ORACLE_STORE
    assert store["subtotal_minor"] == 137
    assert store["tax_minor"] == 17
    assert store["grand_total_minor"] == 154
    computed = db.order_totals(
        store["subtotal_minor"], store["charity_minor"], flow="store"
    )
    assert computed["tax_minor"] == store["tax_minor"] == 17
    assert computed["grand_total_minor"] == store["grand_total_minor"] == 154
    # Negative control: the half-up the clone used to implement.
    assert (137 * 1300 + 5000) // 10000 == 18
    assert db._bp_of(137, 1300) == 17

    bundle = db.TAX_ORACLE
    assert bundle["subtotal_minor"] == 1500
    assert bundle["charity_minor"] == 75
    computed = db.order_totals(
        bundle["subtotal_minor"], bundle["charity_minor"], flow="bundle"
    )
    assert computed["taxable_minor"] == 1425
    assert computed["tax_minor"] == bundle["tax_minor"] == 185
    assert computed["grand_total_minor"] == bundle["grand_total_minor"] == 1685
    # Truncation is what floors 185.25; the exact-cent cases are unaffected.
    assert db.order_totals(1500, 0)["tax_minor"] == 195
    assert db.order_totals(1100, 0)["tax_minor"] == 143


def test_tax_label_follows_the_flow_not_a_global_constant(db) -> None:
    """The captured store drawer says ``Sales Tax:`` and the captured bundle
    review says ``HST`` -- same rate, two labels, so the label travels with
    the numbers instead of being hardcoded on one surface."""

    assert db.TAX_LABEL_STORE == "Sales Tax"
    assert db.TAX_LABEL_BUNDLE == "HST"
    assert db.order_totals(137, 0, flow="store")["tax_label"] == "Sales Tax"
    assert db.order_totals(1500, 75, flow="bundle")["tax_label"] == "HST"

    store = db.cart_add("cart-label-store", "product", DRAWER_PRODUCT)
    assert store["tax_flow"] == "store"
    assert store["tax_label"] == "Sales Tax"

    bundle = db.cart_add("cart-label-bundle", "bundle", ANCHOR, amount_minor=1500)
    assert bundle["tax_flow"] == "bundle"
    assert bundle["tax_label"] == "HST"

    # A bundle line entering a store cart moves the whole cart to the bundle
    # flow (the source never mixes them; the clone routes both through one
    # cart, so the bundle label wins).
    mixed = db.cart_add("cart-label-store", "bundle", ANCHOR, amount_minor=1500)
    assert mixed["tax_flow"] == "bundle"
    assert mixed["tax_label"] == "HST"

    # A placed store order keeps the store label on its confirmation.
    db.cart_add("cart-label-order", "product", DRAWER_PRODUCT)
    placed = db.place_order("cart-label-order", db.DEMO_OWNER, "sandbox-approved")
    purchase = db.get_purchase(db.DEMO_OWNER, placed["order_no"])
    assert purchase["tax_flow"] == "store"
    assert purchase["tax_label"] == "Sales Tax"


def test_drawer_row_and_totals_data_matches_the_capture_shape(db) -> None:
    """The captured drawer renders a title, per-platform redemption lines, an
    original/discounted pair, three total rows, a wallet-credit line and a
    Humble Choice coupon offer -- every one of them from this payload."""

    view = db.cart_add("cart-drawer", "product", DRAWER_PRODUCT)
    line = view["items"][0]
    assert line["name"] == "Bridge Constructor Portal - Portal Proficiency"
    assert line["machine_name"] == (
        "bridgeconstructor_portal_portalproficiency_storefront"
    )
    # Redemption lines and the DRM icon come from the catalog, not the DOM.
    assert sorted(line["platforms"]) == ["linux", "mac", "windows"]
    assert line["drm"] == ["steam"]
    # The struck-through original and the discounted current price.
    assert line["unit_full_price_minor"] > line["unit_price_minor"]
    assert line["line_full_total_minor"] == line["unit_full_price_minor"]
    assert view["original_total_minor"] == line["line_full_total_minor"]
    assert line["discount_pct"] == 75  # captured "-75% OFF" on this product

    # Three total rows: sub-total, tax, grand total -- and Total includes tax,
    # which is exactly what the old single "Total: <subtotal>" row got wrong.
    assert view["subtotal_minor"] == line["line_total_minor"]
    assert view["grand_total_minor"] == view["subtotal_minor"] + view["tax_minor"]
    assert view["grand_total_minor"] > view["subtotal_minor"]

    # Wallet credit and the membership coupon are server-computed, not blank.
    assert view["rewards_label"] == "Wallet Credit Earned"
    assert view["rewards_rate_bp"] == db.WALLET_CREDIT_BP == 1000
    assert view["rewards_credit_minor"] == db._bp_of_nearest(
        view["subtotal_minor"], db.WALLET_CREDIT_BP
    )
    assert view["rewards_credit_minor"] > 0
    assert view["choice_coupon_minor"] == db.CHOICE_COUPON_MINOR == 195

    # Captured wallet-credit oracle: 137 -> 14 is the NEAREST cent, where the
    # tax line on the same 137 truncates to 17.
    oracle = db.WALLET_CREDIT_ORACLE
    assert db._bp_of_nearest(oracle["subtotal_minor"], db.WALLET_CREDIT_BP) == (
        oracle["credit_minor"]
    )
    assert oracle["credit_minor"] == 14
    assert db._bp_of(oracle["subtotal_minor"], db.WALLET_CREDIT_BP) == 13

    # An empty cart leaves both holders with nothing to render.
    empty = db.cart_view("cart-drawer-empty")
    assert empty["rewards_credit_minor"] == 0
    assert empty["choice_coupon_minor"] == 0
    assert empty["original_total_minor"] == 0


def test_bundle_cart_offers_no_store_rewards_or_coupon(db) -> None:
    """Both drawer extras were captured on the store flow only; the bundle
    review shows the Humble Choice upsell checkbox instead."""

    view = db.cart_add("cart-bundle-extras", "bundle", ANCHOR, amount_minor=1500)
    assert view["rewards_credit_minor"] == 0
    assert view["choice_coupon_minor"] == 0
    # A pay-what-you-want line has no undiscounted original to strike through.
    assert view["original_total_minor"] == view["subtotal_minor"] == 1500


def test_account_payload_identifies_by_normalized_email(db) -> None:
    """The drawer's identity block shows the account's EMAIL, and the payload
    it reads exposes that address as ``email_normalized`` -- there is no
    ``email`` key to fall back from into the display name."""

    state = db.login(None, db.DEMO_EMAIL, db.DEMO_PASSWORD)
    account = state["account"]
    assert account["email_normalized"] == db.DEMO_EMAIL
    assert "email" not in account
    assert account["display_name"] and account["display_name"] != db.DEMO_EMAIL
