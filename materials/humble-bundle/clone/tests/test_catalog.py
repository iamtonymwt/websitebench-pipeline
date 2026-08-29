"""Store search against the captured listing oracles and the seed money
contract (invariants ``captured-order-default-sort``, ``no-results-copy``,
``currency-cad-frozen``)."""

import json
from pathlib import Path

SEED_PATH = Path(__file__).resolve().parents[1] / "backend" / "seed_data.json"


def _seed() -> dict:
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))


def _captured(seed: dict, query_key: str) -> list[str]:
    ranked = [
        (product["search_orders"][query_key], product["slug"])
        for product in seed["products"]
        if query_key in product.get("search_orders", {})
    ]
    return [slug for _, slug in sorted(ranked)]


def test_portal_search_captured_order(db) -> None:
    """Search 'portal' reproduces the captured 29-result order exactly,
    case-insensitively, across both pages."""

    expected = _captured(_seed(), "portal")
    assert len(expected) == 29

    page0 = db.search(search="portal")
    assert page0["num_results"] == 29
    assert page0["num_pages"] == 2
    assert page0["page_size"] == 20
    assert [p["slug"] for p in page0["results"]] == expected[:20]

    page1 = db.search(search="Portal ", page=1)
    assert [p["slug"] for p in page1["results"]] == expected[20:]


def test_adventure_bestselling_order(db) -> None:
    """genre=adventure + sort=bestselling reproduces the captured 40-result
    listing (membership and order) exactly."""

    expected = _captured(_seed(), "adventure-bestselling")
    assert len(expected) == 40

    page0 = db.search(genre="adventure", sort="bestselling")
    assert page0["num_results"] == 40
    assert page0["num_pages"] == 2
    page1 = db.search(genre="adventure", sort="bestselling", page=1)
    got = [p["slug"] for p in page0["results"]] + [
        p["slug"] for p in page1["results"]
    ]
    assert got == expected


def test_no_results_copy(db) -> None:
    """The no-match probe returns an empty result set (the captured
    '0 Results' copy itself is rendered by the frontend)."""

    result = db.search(search="zzzz-no-match-websitebench")
    assert result["num_results"] == 0
    assert result["results"] == []
    assert result["num_pages"] == 0


def test_currency_formatting(db) -> None:
    """Money stays integer minor units in the captured CAD everywhere
    (rendering CA$x.xx is the frontend's job)."""

    seed = _seed()
    assert seed["currency"] == "CAD"
    assert db.CURRENCY == "CAD"

    def assert_minor_ints(node, path="$"):
        if isinstance(node, dict):
            for key, value in node.items():
                if key.endswith("_minor"):
                    values = value if isinstance(value, list) else [value]
                    for item in values:
                        assert isinstance(item, int) and not isinstance(
                            item, bool
                        ), f"{path}.{key} is not integer minor: {value!r}"
                assert_minor_ints(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, item in enumerate(node):
                assert_minor_ints(item, f"{path}[{index}]")

    assert_minor_ints(seed)

    product = db.get_product("bridge-constructor-portal")
    assert isinstance(product["current_price_minor"], int)
    assert isinstance(product["full_price_minor"], int)
    bundle = db.get_bundle("yes-chef-cooking-bundle")
    assert bundle["currency"] == "CAD"
    assert all(isinstance(v, int) for v in bundle["preset_prices_minor"])


def test_sorts_and_filters_deterministic(db) -> None:
    """Documented fallbacks: discount desc, alphabetical, badge-first newest,
    onsale/new filters, and global-rank substring matching."""

    discount = db.search(sort="discount")
    pcts = [p["discount_pct"] for p in discount["results"]]
    assert pcts == sorted(pcts, reverse=True)
    assert discount["num_results"] == 156

    alpha = db.search(sort="alphabetical")
    names = [p["human_name"].casefold() for p in alpha["results"]]
    assert names == sorted(names)

    newest = db.search(sort="newest")
    badged = [bool(p.get("cta_badge")) for p in newest["results"]]
    assert badged[:7] == [True] * 7  # the 7 badged products lead

    onsale = db.search(filter="onsale")
    assert onsale["num_results"] > 0
    assert all(p["discount_pct"] > 0 for p in onsale["results"])

    new = db.search(filter="new")
    assert new["num_results"] == 7
    assert all(p.get("cta_badge") for p in new["results"])

    substring = db.search(search="simulator")
    assert substring["num_results"] > 0
    assert all(
        "simulator" in p["human_name"].lower() for p in substring["results"]
    )


def test_portal_suggest_captured_order(db) -> None:
    """suggest('portal') serves the frozen header-search panel in captured
    order with the captured prices/discounts/icons and localized row images.

    The captured panel's first row is a *software* bundle
    (/software/massive-unreal-engine-bundle-software) whose detail page is
    outside the frozen subset, so serving it would dead-end on the branded
    404 — the single most prominent row of the panel the source's own
    trajectory used. The seed keeps the row (it is the evidence record); the
    served panel drops it, and only it, leaving the four captured store rows
    in captured order.
    """

    rows = db.suggest("portal", limit=5)
    assert [row["name"] for row in rows] == [
        "Bridge Constructor Portal",
        "Zanzarah: The Hidden Portal",
        "Spellrune: Realm of Portals",
        "Portal Knights",
    ]
    assert [row["kind"] for row in rows] == ["product"] * 4
    assert all(
        not row["href"].startswith(("/books/", "/software/")) for row in rows
    )

    assert [row.get("price_display") for row in rows] == [
        "CA$1.39",
        "CA$1.11",
        "CA$11.49",
        "CA$5.56",
    ]
    assert [row["discount_pct"] for row in rows] == [90, 90, None, 80]
    assert rows[0]["platform_icons"] == ["steam", "windows", "osx", "linux"]
    assert rows[0]["delivery_separator"] is True
    assert rows[2]["cta_badge"] == "earlyaccess"
    assert all("?" not in row["href"] for row in rows)
    assert all(
        row["img"]["local"].startswith("/static/assets/") for row in rows
    )

    # Normalized-query hit; the seed still holds the panel exactly as captured.
    assert db.suggest("  Portal ") == rows
    captured = _seed()["suggest_orders"]["portal"]
    assert len(captured) == 5
    assert captured[0]["kind"] == "bundle"
    assert captured[0]["href"] == "/software/massive-unreal-engine-bundle-software"
    assert captured[0]["action_text"] == "View"
    assert "price_display" not in captured[0]
    assert captured[0]["description"].startswith("Modular Legendary Forge")
    assert captured[1:] == rows

    # The Spellrune row's product backs a normal catalog entry (lookup 5
    # re-confirmed the detail-1 harvest entry; captured portal rank 7).
    spellrune = db.get_product("spellrune-realm-of-portals")
    assert spellrune["current_price_minor"] == 1149
    assert spellrune["search_orders"] == {"portal": 7}


def test_suggest_rows(db) -> None:
    """Non-captured queries fall back deterministically — listing bundles
    first, then global-rank products — in the same row shape, capped at 5."""

    mixed = db.suggest("shantae", limit=5)
    assert [(row["kind"], row["name"]) for row in mixed] == [
        ("bundle", "Shantae & Heroic Heroines"),
        ("product", "Shantae Advance: Risky Revolution Deluxe Edition"),
    ]
    assert mixed[0]["href"] == "/games/shantae-heroic-heroines"
    assert mixed[0]["action_text"] == "View"
    assert mixed[0]["img"]["local"].startswith("/static/assets/")
    product = mixed[1]
    assert product["href"] == "/store/shantae-advance-risky-revolution-deluxe"
    assert product["price_display"].startswith("CA$")
    assert "action_text" not in product
    assert isinstance(product["platform_icons"], list)
    assert isinstance(product["delivery_separator"], bool)
    assert product["img"]["local"].startswith("/static/assets/")

    # "edition" also matches two *software* listing tiles, whose detail pages
    # are out of subset, so the cap is filled from the products instead of
    # spending two rows on links that would 404.
    capped = db.suggest("edition", limit=5)
    assert len(capped) == 5
    assert [row["kind"] for row in capped] == ["product"] * 5
    by_rank = db.search(search="edition")["results"]
    assert [row["name"] for row in capped] == [
        p["human_name"] for p in by_rank[:5]
    ]

    assert db.suggest("") == []
    assert db.suggest("zzzz-no-match-websitebench") == []


def test_alphabetical_sort_differs_from_captured_order(db) -> None:
    """Negative of captured-order-default-sort: a different sort key must not
    accidentally reproduce the pinned bestselling order."""

    import backend.catalog_db as db_mod

    def all_pages(**kw):
        out = []
        page = 0
        while True:
            r = db_mod.search(page=page, **kw)
            out.extend(p["slug"] for p in r["results"])
            page += 1
            if page >= r["num_pages"]:
                return out

    captured = all_pages(search="portal")
    alpha = all_pages(search="portal", sort="alphabetical")
    assert captured != alpha
    assert sorted(alpha) == sorted(captured)


def test_seed_money_is_integer_cad_only(db) -> None:
    """Negative of currency-cad-frozen: every *_minor field in the seed is an
    integer and the seed currency is CAD."""

    import json
    from pathlib import Path

    seed = json.loads(
        (Path(__file__).resolve().parents[1] / "backend" / "seed_data.json").read_text()
    )
    assert seed["currency"] == "CAD"

    def walk(node, path=""):
        if isinstance(node, dict):
            for k, v in node.items():
                if k.endswith("_minor") and v is not None:
                    vals = v if isinstance(v, list) else [v]
                    for item in vals:
                        assert isinstance(item, int), f"{path}.{k} = {v!r}"
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(seed)
