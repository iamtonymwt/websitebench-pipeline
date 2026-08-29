"""Signed-in account surfaces: the captured controls, the settings-page
preferences and the honesty markers (audit gaps G10, G14, G15, G16, G17 and
T01-T08 gap 8).

The authenticated walk observed every /home interior EMPTY, so the layout,
control set and column headers are the reproduced part and the rows are the
clone's own seeded history. These tests pin (a) the data each captured control
needs, (b) the preference writes the settings page performs, and (c) the
structural facts the renderer must not regress.
"""

import re
from pathlib import Path

import pytest

CLONE = Path(__file__).resolve().parents[1]
APP_JS = CLONE / "static" / "site" / "hb-app.js"


def _js() -> str:
    return APP_JS.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# /user/settings preferences (G10)
# ---------------------------------------------------------------------------
def test_contact_preference_defaults_match_the_capture(db) -> None:
    """Ten checkboxes in captured order; only the incomplete-purchase
    reminder arrives checked."""

    names = [name for name, _label, _default in db.SUBSCRIPTION_PREFS]
    assert names == [
        "bundle_emails",
        "monthly_emails",
        "ebook_emails",
        "software_emails",
        "mobile_emails",
        "store_emails",
        "publishing_emails",
        "wish_list_notification_emails",
        "abandoned_purchase_notification_emails",
        "remind_me_notifications",
    ]
    prefs = db.account_prefs(db.DEMO_OWNER)
    assert [n for n, on in prefs["subscriptions"].items() if on] == [
        "abandoned_purchase_notification_emails"
    ]
    assert prefs["charity_preference"] == "Oceana"
    assert prefs["delivery_email"] is None


def test_delivery_email_update_is_a_real_local_write(db) -> None:
    """The Email Address control is the only editable delivery destination
    for a digital order, so it must persist and take effect."""

    owner = db.DEMO_OWNER
    assert db.delivery_email(owner, owner) == owner

    db.set_delivery_email(owner, "  Delivery.Target@example.test ")
    assert db.account_prefs(owner)["delivery_email"] == "Delivery.Target@example.test"
    assert db.delivery_email(owner, owner) == "Delivery.Target@example.test"

    for bad in ("", "not-an-email", "a@b", "a b@example.test", "x@example"):
        with pytest.raises(db.DeliveryEmailInvalid):
            db.set_delivery_email(owner, bad)
    # a rejected edit leaves the stored address untouched
    assert db.delivery_email(owner, owner) == "Delivery.Target@example.test"


def test_contact_preferences_update_and_validate(db) -> None:
    owner = db.DEMO_OWNER
    prefs = db.set_contact_prefs(
        owner, subscriptions={"bundle_emails": True}, charity_preference="Direct Relief"
    )
    assert prefs["subscriptions"]["bundle_emails"] is True
    # untouched boxes keep their captured defaults
    assert prefs["subscriptions"]["monthly_emails"] is False
    assert prefs["subscriptions"]["abandoned_purchase_notification_emails"] is True
    assert prefs["charity_preference"] == "Direct Relief"
    assert db.account_prefs(owner)["charity_preference"] == "Direct Relief"

    with pytest.raises(ValueError):
        db.set_contact_prefs(owner, subscriptions={"not_a_real_list": True})
    with pytest.raises(ValueError):
        db.set_contact_prefs(owner, charity_preference="  ")


def test_reset_restores_the_captured_preference_defaults(db) -> None:
    owner = db.DEMO_OWNER
    db.set_delivery_email(owner, "elsewhere@example.test")
    db.set_contact_prefs(owner, subscriptions={"store_emails": True})
    db.reset()
    prefs = db.account_prefs(owner)
    assert prefs["delivery_email"] is None
    assert prefs["subscriptions"]["store_emails"] is False


def test_wallet_block_is_the_captured_zero_state(db) -> None:
    assert db.WALLET_CURRENCY == "CAD"
    assert db.WALLET_FUNDS_MINOR == 0
    assert db.WALLET_EXPIRING_MINOR == 0
    assert db.COMMUNITY_DONATED_DISPLAY == "US$282,000,000"


# ---------------------------------------------------------------------------
# account interiors: the data the captured controls act on (G14, G17)
# ---------------------------------------------------------------------------
def test_library_rows_carry_what_the_captured_controls_need(db) -> None:
    """The Platform select and the Recently-updated sort need per-entry
    platform lists and an order timestamp."""

    entries = db.library(db.DEMO_OWNER)
    assert entries, "the demo account is seeded with entitlements"
    assert all(entry["created_at"] for entry in entries)

    by_name = {entry["human_name"]: entry for entry in entries}
    product_entry = by_name["Bridge Constructor Portal"]
    assert sorted(product_entry["platforms"]) == ["linux", "mac", "windows"]
    assert product_entry["delivery_methods"] == ["steam"]

    # bundle entitlements are named by the bundle's own item machine names,
    # which the store catalog does not carry: no guessed platforms
    bundle_entry = by_name["Brewmaster: Beer Brewing Simulator"]
    assert bundle_entry["platforms"] == []
    assert bundle_entry["delivery_methods"] == []

    # the Platform select offers only values that actually occur
    offered = sorted({os for e in entries for os in e["platforms"]})
    assert offered == ["linux", "mac", "windows"]


def test_keys_rows_carry_a_type_for_the_captured_column(db) -> None:
    """The keys table's first column is Type; product entitlements resolve
    to their delivery method, bundle entitlements to nothing."""

    purchases = {p["order_no"]: p for p in db.list_purchases(db.DEMO_OWNER)}
    product_order = purchases[db.DEMO_PRODUCT_ORDER_NO]
    assert [k["delivery_methods"] for k in product_order["keys"]] == [["steam"]]

    bundle_order = purchases[db.DEMO_BUNDLE_ORDER_NO]
    assert bundle_order["keys"]
    assert all(k["delivery_methods"] == [] for k in bundle_order["keys"])


def test_purchases_total_column_is_the_charged_total(db) -> None:
    """G17: the source labels the column Total, so it must show the same
    figure the purchase detail calls Total — not the pre-tax subtotal."""

    for purchase in db.list_purchases(db.DEMO_OWNER):
        detail = db.get_purchase(db.DEMO_OWNER, purchase["order_no"])
        assert purchase["charged_minor"] == detail["charged_minor"]
        assert detail["charged_minor"] == detail["total_minor"] + detail["tax_minor"]
        # the pre-tax subtotal is a different number, which is the bug
        assert detail["charged_minor"] != detail["subtotal_minor"]


def test_wishlist_rows_carry_the_captured_entity_fields(db) -> None:
    """The captured wishlist row is a full store entity: image, platform and
    DRM icon lists, the discount gem and its price pair."""

    db.wishlist_add(db.DEMO_OWNER, "portal-knights")
    row = db.wishlist_list(db.DEMO_OWNER)[0]
    assert row["slug"] == "portal-knights"
    assert row["machine_name"]
    assert row["platforms"] == ["windows"]
    assert row["drm"] == ["steam"]
    assert row["discount_pct"] == 80
    assert row["full_price_minor"] > row["current_price_minor"]
    assert row["media"].get("standard_carousel_image")


# ---------------------------------------------------------------------------
# renderer structure (G14, G15, G16, T01-T08 gap 8)
# ---------------------------------------------------------------------------
def test_account_tabbar_is_the_captured_four_tabs() -> None:
    """The captured nav.tabbar has exactly Purchases / Library /
    Keys & Entitlements / Coupons — no Wishlist, no Back to Store."""

    text = _js()
    block = text[text.index("var ACCOUNT_TABS = ["):]
    block = block[: block.index("];")]
    labels = re.findall(r"'([^']+)', '/(?:home|store)/", block)
    assert labels == ["Purchases", "Library", "Keys & Entitlements", "Coupons"]
    # the clone used to append Wishlist and a Back to Store link the source
    # tabbar does not carry; the tab strip builder must add neither
    start = text.index("function accountTabbar(")
    builder = text[start : text.index("\n  }\n", start)]
    assert "Back to Store" not in builder
    assert "Wishlist" not in builder


def test_wishlist_is_rendered_without_the_account_tab_strip() -> None:
    """The source serves the wishlist as a store page; the clone must not
    inject the /home tab strip there."""

    text = _js()
    start = text.index("if (onStoreWishlist) {")
    branch = text[start : text.index("return;", start)]
    assert "accountTabbar" not in branch
    assert "renderWishlist(wishHost)" in branch


def test_captured_account_controls_are_all_present() -> None:
    """Every control the authenticated capture shows on the three account
    interiors is constructed by the renderer."""

    text = _js()
    for marker in (
        # library
        "'switch-platform', 'switch-platform', 'js-platform', 'Platform'",
        "'search', 'search', 'js-search'",
        "'sort-order', 'sort-order', 'js-sort-order', 'Sort'",
        "'download-method', 'download-method', 'js-download-method', 'Download method'",
        "js-subproducts-holder",
        "js-details-holder",
        # purchases
        "'purchase-search', 'purchase-search'",
        "'purchase-sort', 'purchase-sort'",
        "text: 'Product'",
        "text: 'Date'",
        "text: 'Total'",
        # keys
        "'key-search', 'key-search', 'js-key-search'",
        "'key-sort', 'key-sort', 'js-key-sort'",
        "id: 'hide-redeemed'",
        "Hide redeemed keys & entitlements",
        "unredeemed-keys-table",
        "text: 'Type'",
        "text: 'Game'",
        "text: 'Key or Entitlement'",
        # wishlist
        "My Wish List",
        "Share Wish List",
        "wishlist-share-social-media",
        "remove-wishlist",
        "Discount Breakdown",
        # captured empty-state copy stays reachable
        "var ACCOUNT_EMPTY = 'Nothing found'",
        "bottom-tab-shortcuts",
    ):
        assert marker in text, f"missing captured control: {marker!r}"


def test_seeded_interiors_are_labelled_as_the_clones_own_construction() -> None:
    """G15: the populated views must say the rows are seeded demo data."""

    text = _js()
    assert "var SEEDED_NOTE =" in text
    assert "Seeded demo data" in text
    # every populated interior renders the marker
    for func in ("renderLibrary", "renderPurchases", "renderKeys", "renderPurchaseDetail"):
        start = text.index(f"function {func}(")
        body = text[start : text.index("\n  }\n", start)]
        assert "seededNote()" in body, f"{func} does not label its seeded rows"


# ---------------------------------------------------------------------------
# suggest destinations (T01-T08 gap 6)
# ---------------------------------------------------------------------------
def test_suggest_rows_only_offer_routes_the_clone_serves(db) -> None:
    """The captured `portal` panel's first row is a software bundle whose
    detail page is out of subset; offering it dead-ends on the branded 404."""

    rows = db.suggest("portal")
    assert rows, "the captured panel still returns rows"
    for row in rows:
        assert not row["href"].startswith(("/books/", "/software/"))
        section, slug = row["href"].lstrip("/").split("/", 1)
        if section == "store":
            assert db.get_product(slug) is not None
        else:
            assert section == "games"
            assert db.get_bundle(slug) is not None

    # the captured order of the surviving rows is untouched
    assert [row["href"] for row in rows] == [
        "/store/bridge-constructor-portal",
        "/store/zanzarah-the-hidden-portal",
        "/store/spellrune-realm-of-portals",
        "/store/portal-knights",
    ]


def test_fallback_suggest_keeps_in_subset_bundles(db) -> None:
    """A bundle row whose detail route the clone does serve is still offered."""

    rows = db.suggest("yes chef")
    assert rows[0]["kind"] == "bundle"
    assert rows[0]["href"] == "/games/yes-chef-cooking-bundle"
    assert db.get_bundle("yes-chef-cooking-bundle") is not None
