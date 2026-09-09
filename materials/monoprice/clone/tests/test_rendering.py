"""Tests for the defects a person found by opening the pages.

Four page families were visibly broken while all 39 existing tests passed, the
link-closure gate was clean, the remote-request audit read 0, and the
same-origin census attributed nothing to this project. The tests here exist
because of a specific and repeated pattern: **every check in this run asked
whether something was present, and each of these defects left it present and
unrenderable.**

Two of them also passed through a second blind spot -- the derived artifacts.
`page-shell.html`, `detail-template.html` and `search-template.json` are cut out
of frozen pages, so they carry whatever the freezer did on the day they were
cut. The freezer was fixed to stop rewriting `type="text/css"` into
`type="/text/css"`; the shell was not re-cut for weeks afterwards, and every
page built from it (cart, checkout) served a `<link>` the browser refuses to
apply. Nothing in the suite looked at the artifacts themselves, so nothing
failed. Several tests below read the artifacts on disk for that reason.
"""

from __future__ import annotations

import gzip
import json
import pathlib
import re

import pytest

CLONE_DIR = pathlib.Path(__file__).resolve().parents[1]
STATIC = CLONE_DIR / "static"
FROZEN = STATIC / "frozen"

DERIVED = ["page-shell.html", "detail-template.html", "search-template.json"]

# `type="/text/css"` -- a leading slash the URL rewriter added to a MIME type.
# A browser silently refuses to apply a stylesheet whose declared type is not a
# CSS MIME type, and never even requests it, so this produces no failed request
# and no console error.
DAMAGED_MIME = re.compile(r"""type\s*=\s*\\?["']/(?:text|application|image|font)/""",
                          re.I)


@pytest.mark.parametrize("name", DERIVED)
def test_derived_artifact_has_no_damaged_mime_types(name):
    """The bug that cost cart and checkout six stylesheets each."""
    path = STATIC / name
    if not path.exists():
        pytest.skip(f"{name} has not been built")
    hits = DAMAGED_MIME.findall(path.read_text(encoding="utf-8", errors="replace"))
    assert not hits, (
        f"{name} contains {len(hits)} damaged MIME type attributes such as "
        f"{hits[:3]}. The browser will refuse the stylesheets and scripts they "
        f"describe. This artifact is stale -- re-cut it from a freshly frozen "
        f"page (see step 6 in tools/README.md).")


@pytest.mark.parametrize("name", DERIVED)
def test_derived_artifact_carries_no_subresource_integrity(name):
    """We rewrite asset bytes, so any SRI hash left behind is a dropped file."""
    path = STATIC / name
    if not path.exists():
        pytest.skip(f"{name} has not been built")
    text = path.read_text(encoding="utf-8", errors="replace")
    assert "integrity=" not in text.lower(), (
        f"{name} still declares Subresource Integrity. patch_served_assets.py "
        f"rewrites URLs inside CSS and JS, so the hashes no longer match and "
        f"the browser discards those files -- with status 200 and no error.")


def test_frozen_listings_reveal_their_results_container():
    """A listing with products must not ship both containers hidden.

    HawkSearch hides `#existresult` and `#noresult` and lets its hosted script
    reveal the right one. That script is third-party and stripped, so a category
    page held 165 product links and displayed none of them.
    """
    if not FROZEN.exists():
        pytest.skip("nothing frozen yet")
    checked = both_hidden = 0
    offenders = []
    for path in sorted(FROZEN.rglob("*.html.gz"))[::37]:
        with gzip.open(path, "rb") as fh:
            html = fh.read().decode("utf-8", "replace")
        if 'id="existresult"' not in html:
            continue
        checked += 1
        exist = re.search(
            r"""<div\b[^>]*\bid\s*=\s*["']existresult["'][^>]*>""", html, re.I)
        nores = re.search(
            r"""<div\b[^>]*\bid\s*=\s*["']noresult["'][^>]*>""", html, re.I)
        exist_hidden = bool(exist and "display: none" in exist.group(0))
        nores_hidden = bool(nores and "display: none" in nores.group(0))
        if exist_hidden and nores_hidden:
            both_hidden += 1
            offenders.append(str(path.relative_to(FROZEN)))
    if not checked:
        pytest.skip("no listing pages in the sample")
    assert not both_hidden, (
        f"{both_hidden} of {checked} sampled listing pages hide BOTH result "
        f"containers, so they render blank however much markup they carry: "
        f"{offenders[:4]}")


def test_search_with_results_shows_the_results_container(client):
    body = client.get("/search/index", params={"keyword": "hdmi"}).text
    exist = re.search(r"""<div\b[^>]*\bid\s*=\s*["']existresult["'][^>]*>""",
                      body, re.I)
    assert exist, "the search page has no results container at all"
    assert "display: none" not in exist.group(0), (
        "the search page hides its results container while holding results. "
        "This is the defect a person reported: 316 product links in the DOM, "
        "nothing on screen.")
    assert body.count("p_id=") > 10, "search returned no product links"


def test_search_with_no_results_shows_the_empty_state(client):
    body = client.get("/search/index",
                      params={"keyword": "zzzzqqqxnothing"}).text
    exist = re.search(r"""<div\b[^>]*\bid\s*=\s*["']existresult["'][^>]*>""",
                      body, re.I)
    nores = re.search(r"""<div\b[^>]*\bid\s*=\s*["']noresult["'][^>]*>""",
                      body, re.I)
    assert exist and "display: none" in exist.group(0), (
        "a query with no matches must not show an empty results table")
    if nores:
        assert "display: none" not in nores.group(0), (
            "a query with no matches must show the source's own empty state")


# The six content-fill endpoints. Their containers are hidden until the request
# succeeds, so a wrong answer here is not a missing strip -- it is a strip that
# never appears.
FILL_ENDPOINTS = [
    "/Product/GetTab1?p_id=39165&cust_review=",
    "/Product/GetTab3?p_id=39165&cust_review=",
    "/Product/GetTab5?p_id=39165&cust_review=",
    "/home/getRecommendationsForYou",
    "/home/getTopSellers",
    "/home/getRecentlyViewed",
    "/product/GetCustomersAlsoShoppedFor?p_id=39165&cust_review=",
    "/product/getrecommendationsforyou?p_id=39165&cust_review=",
    "/product/getrecentlyviewed?p_id=39165&cust_review=",
]


@pytest.mark.parametrize("url", FILL_ENDPOINTS)
def test_content_fill_endpoint_answers_and_is_not_a_whole_page(client, url):
    r = client.get(url)
    assert r.status_code == 200, (
        f"{url} answered {r.status_code}. The container that this fills is "
        f"hidden before the request and revealed only on success, so anything "
        f"other than 200 hides it permanently.")
    assert "text/html" in r.headers.get("content-type", "")
    # Three of these used to fall through to the catch-all, which recognised
    # `p_id` and returned the entire product page -- 407 KB of full document,
    # including <html> and <head>, injected into a carousel container.
    assert "<!DOCTYPE" not in r.text[:400].upper(), (
        f"{url} returned a whole HTML document. It is injected via "
        f"`$(container).html(data)` and must be a fragment.")
    assert len(r.text) < 200_000, (
        f"{url} returned {len(r.text)} bytes, which is page-sized, not "
        f"fragment-sized")


@pytest.mark.parametrize("url", FILL_ENDPOINTS)
def test_content_fill_fragments_make_no_remote_references(client, url):
    """A fragment is injected after load, where no page-load audit can see it."""
    body = client.get(url).text
    remote = re.findall(
        r"""https?:(?:\\?/){2}(?:www\.|images\.)?monoprice\.com|"""
        r"""https?:(?:\\?/){2}cdn\.prod\.website-files\.com""", body, re.I)
    assert not remote, (
        f"{url} carries {len(remote)} references that would leave the machine. "
        f"They are injected at run time, so the remote-request audit -- which "
        f"measures page load -- would keep reporting 0.")


# Measured on the source, not assumed. `capture_fragments.py probe` recorded:
#
#   /home/getRecommendationsForYou      14,839 bytes   12 tiles
#   /home/getTopSellers                 20,118 bytes   16 tiles
#   /product/getrecommendationsforyou   14,900 bytes   12 tiles
#   /home/getRecentlyViewed                  0 bytes    0 tiles   (no history)
#   /product/getrecentlyviewed               0 bytes    0 tiles   (no history)
#
# Without this test the three above pass every other check in this file while
# returning nothing at all, because an empty body is not a whole page, carries
# no remote references and is under the size cap. The two tests above were
# genuinely passing that way before this one was added.
NON_EMPTY_FILLS = {
    "/home/getRecommendationsForYou": 8,
    # Tab 3 is the specifications panel; it has no product links, so it is
    # checked by length in its own test below rather than by tile count.
    "/home/getTopSellers": 8,
    "/product/getrecommendationsforyou?p_id=39165&cust_review=": 8,
}


@pytest.mark.parametrize("url,min_tiles", sorted(NON_EMPTY_FILLS.items()))
def test_content_fill_endpoint_actually_returns_content(client, url, min_tiles):
    body = client.get(url).text
    tiles = len(re.findall(r"p_id=\d+", body))
    assert tiles >= min_tiles, (
        f"{url} returned {tiles} product links ({len(body)} bytes). The source "
        f"returns at least {min_tiles}. An endpoint that answers 200 with "
        f"nothing satisfies every other test here and still renders an empty "
        f"strip -- run tools/capture_fragments.py and "
        f"tools/build_frozen_fragments.py.")


def test_fragment_index_distinguishes_empty_from_missing():
    """An empty answer is a real answer and must be recorded as one."""
    index_path = STATIC / "fragments" / "index.json"
    if not index_path.exists():
        pytest.skip("fragments have not been built")
    index = json.loads(index_path.read_text(encoding="utf-8"))["fragments"]
    assert index, "the fragment index is empty"
    # The source returns nothing for `also shopped for` on some products. That
    # has to be recorded as empty-at-source rather than simply absent, or the
    # clone cannot tell "the source has no strip here" from "we failed to
    # capture it".
    assert any(v.get("empty") for v in index.values()), (
        "no fragment is recorded as empty at source, but the source returns an "
        "empty body for at least recently-viewed and for products with no "
        "also-shopped data. If none is recorded, empties are being dropped.")


def test_stripped_third_party_globals_are_shimmed(client):
    """The site's own inline code calls into stripped vendors.

    `dataLayer` (Google Tag Manager), `_satellite` (Adobe Launch) and `F9`
    (Five9 chat) are all third-party and all called by first-party inline
    script. `_satellite` broke add-to-cart entirely. `F9` was found by
    comparing thrown errors against the source rather than by reading the
    clone's console -- the source throws two of its own errors on the same
    page, so a noisy console is not by itself evidence of a clone defect.
    """
    body = client.get("/").text
    assert "data-wb-stripped-globals" in body, (
        "the stripped-globals shim is not in the served home page")
    for name in ("dataLayer", "_satellite", "F9"):
        assert name in body, f"the shim does not define {name}"


# --------------------------------------------------------------------------- #
# The variant chooser
# --------------------------------------------------------------------------- #

VARIANT_MAP = STATIC / "variant-map.json"


def _a_resolvable_variant():
    if not VARIANT_MAP.exists():
        return None
    products = json.loads(VARIANT_MAP.read_text(encoding="utf-8"))["products"]
    for pid, options in products.items():
        for value, target in options.items():
            return pid, value, target
    return None


def test_variant_selection_returns_the_other_product(client):
    """Clicking a variant used to navigate the visitor to an error page.

    `/product/selectpid` answered 404, and the site's own handler does
    `location.href = '/StaticContent/generalerror'` on error -- which the clone
    also answers 404. So the whole interaction ended on a 404 page.
    """
    pick = _a_resolvable_variant()
    if pick is None:
        pytest.skip("variant map has not been built")
    pid, value, target = pick
    r = client.post("/product/selectpid",
                    json={"PID": pid, "changedVal": value, "vals": [value]})
    assert r.status_code == 200, f"selectpid answered {r.status_code}"
    body = r.json()
    assert body["p_id"] == target, (
        f"selecting {value} on {pid} resolved to {body['p_id']}, expected "
        f"{target}")
    assert body["resolved"] is True
    # Non-empty or the site's own guard redirects to its general error page.
    assert body["descPartialView"], (
        "descPartialView is empty, which sends the site's handler to "
        "/StaticContent/generalerror even though we answered 200")
    for key in ("imagePartialView", "infoPartialView"):
        assert len(body[key]) > 200, (
            f"{key} is {len(body[key])} bytes -- the partial extraction "
            f"returned little or nothing, so the panel would be replaced with "
            f"an empty container")


def test_variant_selection_of_an_unresolved_option_keeps_the_page(client):
    """An option we cannot resolve must not produce a different product."""
    pick = _a_resolvable_variant()
    if pick is None:
        pytest.skip("variant map has not been built")
    pid = pick[0]
    r = client.post("/product/selectpid",
                    json={"PID": pid, "changedVal": "@@no-such-value@@",
                          "vals": []})
    assert r.status_code == 200
    body = r.json()
    assert body["p_id"] == pid and body["resolved"] is False, (
        "an unresolvable option must return the current product, not a guess. "
        "A wrong product under the right variant label looks correct.")
    assert body["infoPartialView"], "the current product's panel came back empty"


def test_partial_extraction_returns_the_whole_panel():
    """The depth walk, tested directly on nested markup.

    A regex to the next `</div>` cuts at the first nested close and returns the
    panel's first child, which would still be non-empty and would still pass a
    length check.
    """
    import app as clone_module
    markup = ('<div id="infoPartial"><div class="a"><div class="b">deep</div>'
              '</div><span>tail</span></div><div id="after">no</div>')
    got = clone_module._extract_partial(markup, "infoPartial")
    assert got == ('<div class="a"><div class="b">deep</div></div>'
                   '<span>tail</span>'), got
    assert "after" not in got
    assert clone_module._extract_partial(markup, "missing") == ""


# --------------------------------------------------------------------------- #
# Facet filtering
# --------------------------------------------------------------------------- #

def test_facet_parameter_actually_filters(client):
    """Following a filter link must change which products come back.

    Not "fewer products": facets are applied before the page limit, so a
    filtered search fills a full page of 24 from the wider matching set, exactly
    as an unfiltered one does. The first version of this test asserted
    `filtered < unfiltered` and passed only because the search page was also
    rendering 24 of the donor page's own products at the time.

    What must be true is that the products are different, and that every one of
    them actually carries the value that was filtered on.
    """
    wide = _result_ids(client, keyword="hdmi cable")
    narrow = _result_ids(client, keyword="hdmi cable",
                         v_master_Length_uFilter="6ft")
    assert narrow, "the 6ft filter returned nothing"
    assert set(narrow) != set(wide), (
        "the filtered result set is identical to the unfiltered one, so the "
        "facet parameter is being ignored")

    import app as clone_module
    with clone_module.connection() as conn:
        names = [conn.execute("SELECT name FROM products WHERE p_id = ?",
                              (pid,)).fetchone()[0].lower() for pid in narrow]
    misses = [n for n in names if not re.search(r"(?<![a-z0-9])6ft(?![a-z0-9])", n)]
    assert not misses, (
        f"{len(misses)} of {len(names)} products returned for a Length=6ft "
        f"filter do not carry 6ft as a token: {misses[:3]}")


def test_facet_value_ampersand_encoding_is_decoded(client):
    """The source writes `&` as ` mand ` inside a facet value."""
    import app as clone_module
    assert clone_module.decode_facet_value("AV mand Computer Adapters") == (
        "AV & Computer Adapters")
    # A value with no `mand` must survive untouched, including one that merely
    # contains the letters.
    assert clone_module.decode_facet_value("Command Cables") == "Command Cables"


def test_unknown_facet_value_does_not_silently_return_everything(client):
    """A facet nothing matches must return the empty state, not everything.

    Counted against the page's own baseline rather than against zero: the search
    template carries product links of its own in the surrounding chrome, so a
    page with no results still contains 24 `p_id=` references. Asserting zero
    fails on a correct page, which is its own kind of useless check.
    """
    def ids(**params):
        body = client.get("/search/index", params=params).text
        return set(re.findall(r"p_id=(\d+)", body))

    baseline = ids(keyword="zzzzqqqxnothing")          # nothing matches at all
    unfiltered = ids(keyword="hdmi cable")
    impossible = ids(keyword="hdmi cable", v_Color_uFilter="@@nosuchcolor@@")

    assert len(unfiltered) > len(baseline), "the unfiltered search found nothing"
    assert impossible == baseline, (
        f"an unmatchable facet returned {len(impossible) - len(baseline)} "
        f"products beyond the page's own chrome, so the parameter was dropped "
        f"rather than applied")


def test_product_tab_panels_carry_content(client):
    """The tabs are most of a product page's text.

    They were missed entirely by the first endpoint inventory because
    `mp_productPage_more.js` writes their URL as `tabUrl:` rather than `url:`.
    Without them the product page rendered 920 characters against the source's
    7,134.
    """
    tab3 = client.get("/Product/GetTab3",
                      params={"p_id": "39165", "cust_review": ""}).text
    assert len(tab3) > 1000, (
        f"GetTab3 returned {len(tab3)} bytes for a product that has "
        f"specifications on the source. This is the specifications panel.")
    for tab in ("/Product/GetTab1", "/Product/GetTab5"):
        body = client.get(tab, params={"p_id": "39165", "cust_review": ""}).text
        assert len(body) > 100, f"{tab} returned {len(body)} bytes"


def test_product_page_triggers_its_own_content_fills(client):
    """The call that starts the fills must survive third-party stripping.

    `productPageStuff.initialize({...,"unbxdVersion":2})` contains the substring
    `unbxd`, which is a third-party host hint, and the stripper was testing that
    hint against the whole text of every inline script. It deleted the site's
    own trigger, so no product page filled anything -- no recommendations, no
    tabs -- while the scripts that do the filling were still loaded.
    """
    body = client.get("/product", params={"p_id": "39165"}).text
    assert "productPageStuff.initialize" in body, (
        "the product page no longer calls productPageStuff.initialize, so none "
        "of its content fills will run")
    assert "unbxdVersionValue" in body, (
        "the unbxdVersionValue declaration is gone; initialize() guards the "
        "recommendation fills on it matching")
    assert "mp_productPage_more" in body, "the filler script is not loaded"

    # The template is cut from one donor product, so the trigger arrives with
    # the donor's id baked into it. If the substitution missed it, every
    # template-rendered product would fetch the donor's recommendations and the
    # donor's specifications -- under its own name, which looks correct.
    call = re.search(r"productPageStuff\.initialize\(\s*(\{[^}]*\})", body)
    assert call, "could not read the initialize() arguments"
    assert '"p_id":"39165"' in call.group(1).replace(" ", ""), (
        f"the product page triggers its fills with {call.group(1)[:80]} -- that "
        f"is not this product's id, so it would show another product's tabs")


# --------------------------------------------------------------------------- #
# Third-party stripping, in both directions
# --------------------------------------------------------------------------- #
#
# This has now been broken both ways in one session. Matching vendor names as
# substrings deleted the site's own code (`unbxdVersion`, `mp_unbxd_search.css`);
# narrowing to hosts then let an inline loader through that assembles its URL at
# run time, putting 114 remote requests back into a clone that had none. Both
# directions are asserted here, on the frozen output rather than on the
# function, because the output is what ships.

THIRD_PARTY_IN_FROZEN = [
    "google-analytics.com", "googletagmanager.com", "adobedtm.com",
    "onetrust.com", "criteo.com", "hotjar.com", "facebook.net",
]


def test_frozen_pages_reference_no_third_party_host():
    if not FROZEN.exists():
        pytest.skip("nothing frozen yet")
    offenders = []
    pages = sorted(FROZEN.rglob("*.html.gz"))[::53]
    for path in pages:
        with gzip.open(path, "rb") as fh:
            html = fh.read().decode("utf-8", "replace").lower()
        for host in THIRD_PARTY_IN_FROZEN:
            if host in html:
                offenders.append(f"{path.relative_to(FROZEN)}: {host}")
    assert not offenders, (
        f"{len(offenders)} frozen pages still name a third-party host, which "
        f"means a loader survived and will fetch at run time: {offenders[:5]}")


def test_frozen_product_pages_keep_their_own_trigger():
    """First-party code that merely mentions a vendor must survive."""
    if not FROZEN.exists():
        pytest.skip("nothing frozen yet")
    product_dir = FROZEN / "product"
    if not product_dir.exists():
        pytest.skip("no frozen product pages")
    checked = with_trigger = 0
    for path in sorted(product_dir.glob("q__p_id=*.html.gz"))[::7]:
        with gzip.open(path, "rb") as fh:
            html = fh.read().decode("utf-8", "replace")
        if "mp_productPage_more" not in html:
            continue          # absent-product pages do not carry the filler
        checked += 1
        if "productPageStuff.initialize" in html:
            with_trigger += 1
    if not checked:
        pytest.skip("no product page in the sample carries the filler script")
    assert with_trigger == checked, (
        f"{checked - with_trigger} of {checked} product pages load the filler "
        f"script but no longer call productPageStuff.initialize -- the trigger "
        f"was stripped, so their recommendations and tab panels never load. It "
        f"contains the substring 'unbxd', which is a third-party host hint.")


# --------------------------------------------------------------------------- #
# Sort, page size, and the donor's own results
# --------------------------------------------------------------------------- #

def _result_ids(client, **params):
    """Product ids inside the results container only."""
    body = client.get("/search/index", params=params).text
    segment = body.split('id="existresult"', 1)[-1]
    out = []
    for m in re.finditer(r"p_id=(\d+)", segment):
        if m.group(1) not in out:
            out.append(m.group(1))
    return out


def test_search_page_shows_no_products_from_the_donor_page():
    """Every search used to open with the donor's own first product.

    `extract_search_template.py` replaced only the one row it had templated and
    left the donor's other 24 rows in the page, so `hdmi cable`, `speaker` and
    `keyboard` all began with p_id 44695. It also inflated the page enough that
    the visible-content audit read 2.67x the source's text and blamed the facet
    sidebar.
    """
    path = STATIC / "search-template.json"
    if not path.exists():
        pytest.skip("search template has not been built")
    template = json.loads(path.read_text(encoding="utf-8"))
    leftover = re.findall(r'href="/product\?p_id=(\d+)"', template["page"])
    assert not leftover, (
        f"the search template still carries {len(leftover)} product links of "
        f"its own ({sorted(set(leftover))[:5]}); they appear on every search "
        f"regardless of the query")


def test_sort_changes_the_order(client):
    default = _result_ids(client, keyword="hdmi cable")
    assert len(default) > 5, "not enough results to test sorting"
    for sort in ("title asc", "sellingPrice asc", "sellingPrice desc",
                 "rating_count desc,sort_rating desc",
                 "first_instock_date desc,sku desc"):
        ordered = _result_ids(client, keyword="hdmi cable", sort=sort)
        assert ordered, f"sort={sort!r} returned nothing"
        assert ordered != default, (
            f"sort={sort!r} produced the same order as Best Match. The control "
            f"navigates to a URL this handler must read; ignoring the parameter "
            f"reloads an identical page and looks broken.")


def test_price_sort_is_actually_ordered(client):
    import app as clone_module
    for sort, ascending in (("sellingPrice asc", True), ("sellingPrice desc", False)):
        ids = _result_ids(client, keyword="hdmi cable", sort=sort)
        with clone_module.connection() as conn:
            prices = []
            for pid in ids[:12]:
                row = conn.execute("SELECT price FROM products WHERE p_id = ?",
                                   (pid,)).fetchone()
                if row and row[0] is not None:
                    prices.append(row[0])
        pairs = list(zip(prices, prices[1:]))
        ok = all(a <= b for a, b in pairs) if ascending else \
             all(a >= b for a, b in pairs)
        assert ok, f"{sort} produced {prices[:8]}, which is not ordered"


def test_page_size_is_honoured(client):
    assert len(_result_ids(client, keyword="hdmi cable")) == 24
    assert len(_result_ids(client, keyword="hdmi cable", rows="50")) == 50
    # An unoffered size falls back rather than being trusted.
    assert len(_result_ids(client, keyword="hdmi cable", rows="9999")) == 24
    assert len(_result_ids(client, keyword="hdmi cable", rows="nonsense")) == 24


def test_sorted_listing_url_is_not_a_404(client):
    """The category page's own js_sort navigates to a URL like this."""
    r = client.get("/category/cables/hdmi-cables/hdmi-cables",
                   params={"menuDisStr": "hdmi cables",
                           "sort": "sellingPrice asc", "TotalProducts": "36"})
    assert r.status_code == 200, (
        f"choosing a sort on a category page answered {r.status_code}; the "
        f"listing is frozen so the order does not change, but it must still "
        f"render (claim cl-024)")


# --------------------------------------------------------------------------- #
# Sorting a captured listing
# --------------------------------------------------------------------------- #

CATEGORY = "/category/cables/video-cables/displayport-&-mini-displayport-cables"


def _listing_prices(client, **params):
    import app as clone_module
    body = client.get(CATEGORY, params=params).text
    segment = body.split('id="existresult"', 1)[-1]
    seen, prices = [], []
    with clone_module.connection() as conn:
        for m in re.finditer(r"p_id=(\d+)", segment):
            pid = m.group(1)
            if pid in seen:
                continue
            seen.append(pid)
            row = conn.execute("SELECT price FROM products WHERE p_id = ?",
                               (pid,)).fetchone()
            if row and row[0] is not None:
                prices.append(row[0])
    return prices


def test_category_listing_sorts_by_price():
    """A category page is frozen markup, so its rows are permuted in place.

    This was first recorded as a limitation and shipped that way; a person
    pointed out that choosing "Price: Highest to Lowest" changed nothing. The
    two responses were byte-identical.
    """
    from fastapi.testclient import TestClient
    import app as clone_module
    with TestClient(clone_module.app) as client:
        desc = _listing_prices(client, menuDisStr="x",
                               sort="sellingPrice desc", TotalProducts="22")
        asc = _listing_prices(client, menuDisStr="x",
                              sort="sellingPrice asc", TotalProducts="22")
    assert len(desc) > 3, "not enough priced products in this listing"
    assert all(a >= b for a, b in zip(desc, desc[1:])), f"not descending: {desc[:8]}"
    assert all(a <= b for a, b in zip(asc, asc[1:])), f"not ascending: {asc[:8]}"


def test_sorting_a_listing_only_reorders_it(client):
    """Permuting rows must not add, drop or alter any markup."""
    plain = client.get(CATEGORY).text
    sortd = client.get(CATEGORY, params={"menuDisStr": "x",
                                         "sort": "sellingPrice desc",
                                         "TotalProducts": "22"}).text
    assert len(plain) == len(sortd), (
        f"sorting changed the page size from {len(plain)} to {len(sortd)}; it "
        f"is supposed to move existing rows, not rewrite them")
    assert plain.count("<img") == sortd.count("<img")
    assert set(re.findall(r"p_id=(\d+)", plain)) == set(
        re.findall(r"p_id=(\d+)", sortd))
    assert plain != sortd, "sorting produced an identical page"


def test_sort_dropdown_shows_the_active_sort(client):
    body = client.get(CATEGORY, params={"menuDisStr": "x",
                                        "sort": "sellingPrice desc",
                                        "TotalProducts": "22"}).text
    chosen = re.search(r"<option\b[^>]*\bselected\b[^>]*>([^<]*)</option>",
                       body, re.I)
    assert chosen, "no option is marked selected"
    assert "highest" in chosen.group(1).lower(), (
        f"the dropdown reads {chosen.group(1).strip()!r} while the URL sorts by "
        f"price descending")
