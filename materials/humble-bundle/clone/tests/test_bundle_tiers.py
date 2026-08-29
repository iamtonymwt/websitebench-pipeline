"""Anchor-bundle tier engine against the frozen thresholds (invariant
``tier-engine-oracle``)."""

import pytest

ANCHOR = "yes-chef-cooking-bundle"


def test_custom_15_unlocks_tier1(db) -> None:
    """$15 (1500 minor) yields 7 items and the captured missing-out facts:
    "You're missing out on Tavern Manager Simulator and 8 more! Pay at
    least CA$22.19 to get all items." (7 unlocked of 16 => missing 9)."""

    preview = db.tier_preview(ANCHOR, 1500)
    assert preview["valid"] is True
    assert preview["floor_minor"] == 971
    assert preview["unlocked_tier_ids"] == ["initial"]
    assert preview["unlocked_count"] == 7
    assert preview["total_count"] == 16
    assert preview["missing_count"] == 9
    assert preview["missing_first_name"] == "Tavern Manager Simulator"
    assert preview["next_threshold_minor"] == 2219


def test_below_floor_rejected(db) -> None:
    """Below-floor amounts are invalid in preview and rejected by the cart.

    ``next_threshold_minor`` is always the all-items threshold, never the
    floor: CA$9.71 unlocks 7 of 16 items, so reporting it as the price that
    "gets all items" was a lie. Below the floor the caller renders the
    captured minimum-price sentence off ``valid``/``floor_minor`` instead.
    """

    preview = db.tier_preview(ANCHOR, 500)
    assert preview["valid"] is False
    assert preview["floor_minor"] == 971
    assert preview["unlocked_tier_ids"] == []
    assert preview["unlocked_count"] == 0
    assert preview["missing_count"] == 16
    assert preview["next_threshold_minor"] == 2219

    with pytest.raises(db.BelowFloor) as excinfo:
        db.cart_add("cart-below-floor", "bundle", ANCHOR, amount_minor=500)
    assert excinfo.value.floor_minor == 971
    assert db.cart_view("cart-below-floor")["items"] == []


def test_exact_thresholds_unlock_cumulatively(db) -> None:
    """Frozen tiers CA$9.71 / 18.03 / 22.19 unlock 7 / 13 / 16 cumulative."""

    at_floor = db.tier_preview(ANCHOR, 971)
    assert at_floor["valid"] is True
    assert at_floor["unlocked_count"] == 7
    assert at_floor["missing_count"] == 9
    assert at_floor["missing_first_name"] == "Tavern Manager Simulator"
    assert at_floor["next_threshold_minor"] == 2219

    mid = db.tier_preview(ANCHOR, 1803)
    assert mid["unlocked_tier_ids"] == ["initial", "bt13"]
    assert mid["unlocked_count"] == 13
    assert mid["missing_count"] == 3
    assert mid["missing_first_name"] == "Tavern Manager Simulator"
    assert mid["next_threshold_minor"] == 2219

    top = db.tier_preview(ANCHOR, 2219)
    assert top["unlocked_tier_ids"] == ["initial", "bt13", "bt16"]
    assert top["unlocked_count"] == 16
    assert top["missing_count"] == 0
    assert top["missing_first_name"] is None
    assert top["next_threshold_minor"] is None


def test_fixed_tier_bundle_and_listing(db) -> None:
    """2K bundle is one fixed CA$21.16 tier of 15; listing keeps tile order."""

    preview = db.tier_preview("2k-megahits-2026-bundle", 2116)
    assert preview["valid"] is True
    assert preview["unlocked_count"] == 15
    assert preview["total_count"] == 15
    assert preview["missing_count"] == 0

    below = db.tier_preview("2k-megahits-2026-bundle", 2115)
    assert below["valid"] is False

    listing = db.bundles_listing()
    assert set(listing) == {"books", "games", "software"}
    assert sum(len(tiles) for tiles in listing.values()) == 57
    games = [tile["slug"] for tile in listing["games"]]
    assert games[0] == "2k-megahits-2026-bundle"
    assert games[1] == "yes-chef-cooking-bundle"

    bundle = db.get_bundle(ANCHOR)
    assert bundle["msrp_minor"] == 28853
    assert bundle["preset_prices_minor"] == [971, 1803, 2219, 3000, 3500, 4000]
    assert bundle["tier_order"] == ["bt16", "bt13", "initial"]
    assert [t["tier_id"] for t in bundle["tiers"]] == ["bt16", "bt13", "initial"]
    assert bundle["charity"]["name"] == "Farmlink Project"


def test_item_count_line_keeps_the_captured_emphasis() -> None:
    """The captured .js-item-count-text wraps its middle clause in <strong>,
    so the message has to be built as nodes rather than assigned as text.

    Source: interactive/bundle-anchor-custom15/dom.html
    `You will get 7 items. <strong>You're missing out</strong> on Tavern
    Manager Simulator and 8 more! Pay at least CA$22.19 to get all items.`
    """

    import re
    from pathlib import Path

    clone = Path(__file__).resolve().parents[1]
    app_js = (clone / "static" / "site" / "hb-app.js").read_text(encoding="utf-8")
    start = app_js.index("function unlockMessageNodes(")
    body = app_js[start : app_js.index("\n  }\n", start)]
    assert "el('strong', { text: \"You're missing out\" })" in body
    assert "'You will get ' + p.unlocked_count + ' items. '" in body
    # below the floor the trailing clause names the floor as the minimum
    assert "' more! The minimum price for this bundle is '" in body
    assert "money(p.floor_minor)" in body
    # and the old flat-string assignment is gone
    assert not re.search(r"countText\.textContent\s*=", app_js)

    source = (
        clone.parent
        / "source-current"
        / "2026-08-20.humble-bundle-r1"
        / "interactive"
        / "bundle-anchor-custom15"
        / "dom.html"
    ).read_text(encoding="utf-8")
    assert (
        "You will get 7 items. <strong>You're missing out</strong> on Tavern "
        "Manager Simulator and 8 more! Pay at least CA$22.19 to get all items."
    ) in source
