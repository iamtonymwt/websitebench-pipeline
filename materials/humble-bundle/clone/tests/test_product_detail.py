"""Product-detail fidelity: per-product rating / review binding and the
/store/c/{token} category namespace (audit gaps T06-3 and T03-8).

The frozen product template is Satisfactory's page, reused for every other
product and hydrated client-side. Two classes of regression are guarded here:

1. the frozen page's Steam rating and its three OpenCritic reviews must never
   stand in for another product (they did: every non-frozen product showed
   ``96% | Overwhelmingly Positive`` and Satisfactory's critic quotes), and
2. every ``/store/c/{token}`` link in the captured navigation must resolve to
   a real facet, not just the genre facet (18 nav links returned 0 results).
"""

import json
import re
from pathlib import Path

CLONE = Path(__file__).resolve().parents[1]
APP_JS = CLONE / "static" / "site" / "hb-app.js"
SEED_PATH = CLONE / "backend" / "seed_data.json"
SOURCE = (
    CLONE.parent / "source-current" / "2026-08-20.humble-bundle-r1" / "static"
)
FROZEN_PRODUCT = "satisfactory"


def _js() -> str:
    return APP_JS.read_text(encoding="utf-8")


def _js_code() -> str:
    """hb-app.js with its block comments stripped (they quote the captured
    copy on purpose, so only executable text may be searched for leaks)."""

    return re.sub(r"/\*.*?\*/", "", _js(), flags=re.S)


def _js_function(name: str) -> str:
    """The source text of one top-level ``function name(...) {...}`` block."""

    text = _js()
    start = text.index(f"\n  function {name}(")
    end = text.index("\n  }\n", start)
    return text[start:end]


# ---------------------------------------------------------------------------
# per-product rating + reviews
# ---------------------------------------------------------------------------
def test_rating_payload_is_per_product(db) -> None:
    """Every product's own Steam summary reaches the API, and the frozen
    product's numbers are not shared with anything else."""

    frozen = db.get_product(FROZEN_PRODUCT)["user_rating"]
    assert frozen == {
        "steam_percent": 0.96,
        "display_user_ratings": "steam_recent",
        "review_text": "overwhelmingly_positive",
        "steam_count": 1772,
    }

    other = db.get_product("portal-knights")["user_rating"]
    assert other == {
        "steam_percent": 0.78,
        "display_user_ratings": "steam_recent",
        "review_text": "mostly_positive",
        "steam_count": 52,
    }
    assert other != frozen

    # A product with no captured rating carries none, so the view must be
    # cleared rather than left showing the frozen page's numbers.
    assert db.get_product("abiotic-factor").get("user_rating") is None


def test_no_product_carries_critic_reviews(db) -> None:
    """Critical Reception was captured for the frozen product only, so no
    product payload may claim critic reviews (the renderer must render the
    section empty instead of reusing Satisfactory's three quotes)."""

    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    assert [p for p in seed["products"] if p.get("reviews")] == []
    assert db.get_product("portal-knights").get("reviews") in (None, [])


def test_hydrator_rebinds_rating_and_reviews() -> None:
    """hydrateProduct must rebind both sections for every non-frozen product."""

    hydrate = _js_function("hydrateProduct")
    assert "bindUserRating(product)" in hydrate
    assert "bindReviews(product)" in hydrate

    rating = _js_function("bindUserRating")
    # no rating data -> the property is emptied and hidden, never inherited
    assert "if (pct === null)" in rating
    assert "view.innerHTML = ''" in rating
    assert "holder.style.display = 'none'" in rating

    reviews = _js_function("bindReviews")
    assert "collection.innerHTML = ''" in reviews


def test_frozen_product_review_text_is_not_baked_into_the_app() -> None:
    """The frozen page owns Satisfactory's rating and critic quotes; the
    interaction layer must not carry them, or they would leak again."""

    text = _js_code()
    for leaked in (
        "Overwhelmingly Positive",
        "PC Gamer",
        "God is a Geek",
        "1,772",
        "Jonathan Bolding",
    ):
        assert leaked not in text, f"{leaked!r} is hardcoded in hb-app.js"


def test_frozen_product_page_keeps_its_own_rating() -> None:
    """Guard the other direction: the frozen template still carries the
    captured summary, which is what the frozen route is for."""

    dom = (SOURCE / "store-product-satisfactory" / "desktop" / "dom.html").read_text(
        encoding="utf-8"
    )
    assert "user-rating-view" in dom
    assert "96% of the 1,772 user reviews on Steam" in dom
    assert dom.count('class="reviews-entity entity"') == 3


# ---------------------------------------------------------------------------
# /store/c/{token} -> facet mapping
# ---------------------------------------------------------------------------
def _facet_vocabularies() -> dict[str, set[str]]:
    """The Genre / Platform / DRM values the captured search page offers."""

    dom = (SOURCE / "store-search" / "desktop" / "dom.html").read_text(
        encoding="utf-8"
    )
    vocab: dict[str, set[str]] = {"genre": set(), "platform": set(), "drm": set()}
    for name, value in re.findall(
        r'class="js-filter-option" name="(genre|platform|drm)" value="([^"]+)"', dom
    ):
        vocab[name].add(value)
    return vocab


def _category_links() -> list[str]:
    """Every /store/c/{token} destination in the captured navigation."""

    dom = (SOURCE / "home" / "desktop" / "dom.html").read_text(encoding="utf-8")
    return sorted(set(re.findall(r'href="/store/c/([^"]+)"', dom)))


def _resolve(token: str, vocab: dict[str, set[str]]) -> tuple[str | None, str | None]:
    """The mapping hb-app.js applies: genre -> platform -> drm, 'all' = none."""

    if token == "all":
        return None, None
    for facet in ("genre", "platform", "drm"):
        if token in vocab[facet]:
            return facet, token
    return "genre", token


def test_every_nav_category_link_resolves_to_a_captured_facet() -> None:
    """All 16 captured /store/c/{token} links land on a real facet (or mean
    'every product'), so none of them can silently mean genre=windows."""

    vocab = _facet_vocabularies()
    assert len(vocab["genre"]) == 17
    assert len(vocab["platform"]) == 11
    assert len(vocab["drm"]) == 7

    resolved = {token: _resolve(token, vocab) for token in _category_links()}
    assert resolved == {
        "all": (None, None),
        "action": ("genre", "action"),
        "adventure": ("genre", "adventure"),
        "indie": ("genre", "indie"),
        "racing": ("genre", "racing"),
        "rpg": ("genre", "rpg"),
        "simulation": ("genre", "simulation"),
        "strategy": ("genre", "strategy"),
        # the nav files Virtual Reality under Top Genres and `vr` is a
        # captured Genre value, not a platform
        "vr": ("genre", "vr"),
        "linux": ("platform", "linux"),
        "mac": ("platform", "mac"),
        "oculus-rift": ("platform", "oculus-rift"),
        "switch2": ("platform", "switch2"),
        # `switch` is both a platform and a DRM value; the nav lists it under
        # Top Platforms, which is why genre -> platform -> drm is the order
        "switch": ("platform", "switch"),
        "windows": ("platform", "windows"),
        "steam": ("drm", "steam"),
    }


def test_category_mapping_matches_the_hydrator(db) -> None:
    """The resolved facet is the one the search API actually filters on, so
    the platform and DRM categories stop returning an empty grid."""

    vocab = _facet_vocabularies()
    counts = {}
    for token in _category_links():
        facet, value = _resolve(token, vocab)
        kwargs = {facet: value} if facet else {}
        counts[token] = db.search(**kwargs)["num_results"]

    # 156, from 69. The frozen markup showed products the catalogue never had:
    # the store listing alone linked 125 distinct slugs and only 42 resolved,
    # so 83 tiles were visible, priced, illustrated, and led to a 404.
    # `tools/recover_tile_products.py` reads each tile as a DOM subtree and
    # writes only what the tile carries — title, prices, discount, delivery and
    # cover image. Genre, developer, publisher and description stay empty,
    # which is why the genre facets below barely move while the platform and
    # delivery facets rise with the whole catalogue.
    assert counts["all"] == 156  # every seeded product
    assert counts["adventure"] == 40  # the captured genre oracle
    assert counts["windows"] == 150
    assert counts["steam"] == 142
    assert counts["mac"] == 34
    assert counts["linux"] == 28
    assert counts["switch"] == 2
    assert counts["oculus-rift"] == 1
    # honest zeros: the authorized subset seeds no switch2 product and no
    # product tagged with the `vr` genre
    assert counts["switch2"] == 0
    assert counts["vr"] == 0
    # regression: none of the platform / DRM categories may read as a genre
    assert db.search(genre="windows")["num_results"] == 0
    assert db.search(genre="steam")["num_results"] == 0


def test_hydrator_resolves_categories_over_all_three_facets() -> None:
    """searchPage must consult every facet vocabulary, and treat `all` as
    'no facet' rather than genre=all."""

    text = _js()
    assert "inFacetVocab('genre', token)" in text
    assert "inFacetVocab('platform', token)" in text
    assert "inFacetVocab('drm', token)" in text
    assert "if (token === 'all')" in text
