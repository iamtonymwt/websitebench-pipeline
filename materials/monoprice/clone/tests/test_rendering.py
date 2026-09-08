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
