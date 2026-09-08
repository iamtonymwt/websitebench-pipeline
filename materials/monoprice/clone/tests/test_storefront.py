"""Tests for the monoprice clone.

Every test here corresponds to something that was actually broken at some point
in this build, and most were found by driving the site rather than by reading
the code. A test that has never failed is a guess; these have all failed once.
"""

from __future__ import annotations

import gzip
import json
import pathlib
import re
import sqlite3

import pytest

SITE_DIR = pathlib.Path(__file__).resolve().parents[2]
FROZEN_ROOT = SITE_DIR / "clone" / "static" / "frozen"
ASSET_ROOT = SITE_DIR / "source-assets"


# --------------------------------------------------------------------------- #
# Serving
# --------------------------------------------------------------------------- #

def test_home_is_served_and_is_not_blank(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.text
    assert "Monoprice" in body
    # An empty page has no broken links and makes no requests, so every closure
    # gate passes it. The floor is what stops "green" meaning "blank".
    assert len(body) > 100_000, "home page is suspiciously small"
    assert body.count("<img") > 20


def test_gzip_only_when_the_client_asks_for_it(client):
    """Frozen pages are stored compressed; that must not leak to every caller.

    Sending Content-Encoding: gzip unconditionally made every page unreadable to
    any client that does not advertise gzip, and the first smoke test read
    binary and concluded the pages were empty.
    """
    plain = client.get("/", headers={"Accept-Encoding": "identity"})
    assert plain.status_code == 200
    assert "gzip" not in plain.headers.get("content-encoding", "")
    assert "<html" in plain.text.lower()

    compressed = client.get("/", headers={"Accept-Encoding": "gzip"})
    assert compressed.status_code == 200
    assert "<html" in compressed.text.lower()


def test_absent_product_answers_200_like_the_source(client):
    """The source answers 200 for an id it no longer sells, not 404.

    1,906 ids are in this state. Answering 404 would be a difference the source
    does not have.
    """
    response = client.get("/product?p_id=99999999")
    assert response.status_code == 200
    assert "no longer available" in response.text.lower()


def test_unknown_route_answers_the_sites_own_404(client):
    response = client.get("/definitely-not-a-real-route-websitebench")
    assert response.status_code == 404
    # Not IIS's "Detailed Error - 404.0" page: that is the *server's* 404, not
    # the site's, and it was served here until the donor was chosen by title.
    assert "httperror404" in response.text.lower().replace(" ", "")
    assert "detailed error" not in response.text.lower()


def test_product_url_variants_reach_the_same_page(client):
    """The source serves /product and /product/index, and hangs tracking
    parameters off its own links. All of them have to resolve here."""
    canonical = client.get("/product?p_id=10145")
    assert canonical.status_code == 200
    for variant in ("/product/index?p_id=10145",
                    "/product?p_id=10145&page_type=homepage&promo_type=x",
                    "/Product?p_id=10145"):
        response = client.get(variant)
        assert response.status_code == 200, variant
        assert "10145" in response.text, variant


def test_specific_routes_are_reachable_not_swallowed_by_the_catch_all():
    """FastAPI matches in declaration order.

    A route declared after `/{full_path:path}` never runs. On an earlier site a
    /api/cart route existed and had never once executed.
    """
    import app as clone_app

    paths = [getattr(route, "path", "") for route in clone_app.app.routes]
    catch_all = next(i for i, p in enumerate(paths) if p == "/{full_path:path}")
    for specific in ("/cart", "/checkout", "/search/index", "/api/suggest",
                     "/cart/minicart", "/order/{order_id}"):
        assert specific in paths, f"{specific} is not registered"
        assert paths.index(specific) < catch_all, (
            f"{specific} is declared after the catch-all and can never run")


# --------------------------------------------------------------------------- #
# Catalogue
# --------------------------------------------------------------------------- #

def test_product_names_are_not_html_encoded(catalogue):
    """192 product names shipped as `Black&#43;Decker` on the previous site."""
    offenders = [p["p_id"] for p in catalogue["products"]
                 if re.search(r"&(?:#\d+|[a-z]{2,8});", p["name"])]
    assert not offenders, f"{len(offenders)} product names still carry entities"


def test_every_product_has_a_price_and_a_sku(catalogue):
    missing = [p["p_id"] for p in catalogue["products"]
               if p["price"] is None or not p["sku"]]
    assert not missing, f"{len(missing)} products without price or sku"


def test_product_ids_carry_no_stray_whitespace(catalogue):
    """Two source links carry `p_id= 24285`, naming products that also exist
    without the space. Kept raw they became duplicate rows whose url_path was
    a URL nothing would ever request."""
    bad = [p["p_id"] for p in catalogue["products"] if p["p_id"] != p["p_id"].strip()]
    assert not bad, bad


def test_category_membership_comes_from_both_sources(catalogue):
    """A listing page is the only place the product-to-category relation is
    written down. Reading only breadcrumbs drops it silently."""
    evidence = {m["evidence"] for m in catalogue["product_categories"]}
    assert "breadcrumb" in evidence
    assert "listing" in evidence
    listing = sum(1 for m in catalogue["product_categories"]
                  if m["evidence"] == "listing")
    assert listing > 10_000, f"only {listing} memberships from listings"


def test_shop_collections_are_in_the_catalogue(catalogue):
    """2,622 /p/shop pages were captured and read by nothing until they were."""
    shop = [c for c in catalogue["categories"] if c.get("kind") == "shop-collection"]
    assert len(shop) > 1_000, f"only {len(shop)} shop collections"


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #

def test_search_returns_matching_products(client):
    response = client.get("/search/index?keyword=hdmi+cable")
    assert response.status_code == 200
    ids = set(re.findall(r"p_id=(\d+)", response.text))
    assert len(ids) > 10, f"only {len(ids)} products in results"


def test_search_reflects_the_query_not_the_donor_page(client):
    """The template's donor was a `clearance/overstock` search, and its query is
    baked into the page 25 times as text and 284 times URL-encoded."""
    response = client.get("/search/index?keyword=speaker+wire")
    assert response.status_code == 200
    title = re.search(r"<title[^>]*>(.*?)</title>", response.text, re.I | re.S)
    assert title is not None
    assert "speaker wire" in title.group(1).lower()
    assert "clearance" not in title.group(1).lower()


def test_type_ahead_is_answered_locally(client):
    """On the source this is a cross-origin call on every keystroke -- a remote
    request no page-load audit can observe."""
    response = client.get("/api/suggest?q=hdmi")
    assert response.status_code == 200
    payload = response.json()
    assert payload["suggestions"], "no suggestions for a common term"
    assert all("/product?p_id=" in s["url"] for s in payload["suggestions"])


def test_type_ahead_ignores_a_one_character_query(client):
    assert client.get("/api/suggest?q=h").json()["suggestions"] == []


# --------------------------------------------------------------------------- #
# Commerce
# --------------------------------------------------------------------------- #

def test_add_to_cart_then_cart_shows_the_item(client):
    client.post("/cart", data={"p_id": "10145", "qty": "2"})
    cart = client.get("/cart")
    assert cart.status_code == 200
    assert "10145" in cart.text
    assert 'value="2"' in cart.text


def test_declined_payment_places_no_order_and_keeps_the_cart(client):
    client.post("/cart", data={"p_id": "10145", "qty": "1"})
    response = client.post("/checkout", data={
        "scenario": "sandbox-declined", "ship_name": "T", "ship_city": "C",
        "ship_state": "CA", "ship_postal": "91730"})
    assert response.status_code == 200
    assert "declined" in response.text.lower()
    assert "data-order-reference" not in response.text
    # The goods must still be there. Emptying the cart on a failed payment makes
    # a failure look like a success to everything downstream.
    assert "10145" in client.get("/cart").text


def test_approved_payment_places_an_order_and_empties_the_cart(client):
    client.post("/cart", data={"p_id": "10145", "qty": "1"})
    response = client.post("/checkout", data={
        "scenario": "sandbox-approved", "ship_name": "Test Shopper",
        "ship_city": "Rancho", "ship_state": "CA", "ship_postal": "91730"})
    assert response.status_code == 200
    # The payment result field is `status`, not `outcome`. Reading a key that
    # does not exist made every purchase take the declined branch.
    assert "data-order-reference" in response.text
    assert "data-order-total" in response.text
    assert "cart is empty" in client.get("/cart").text.lower()


def test_the_order_records_no_payment_details(backend):
    """The boundary is in the schema, not in a comment promising not to store."""
    with backend.lifecycle.connection() as connection:
        columns = {row[1].lower() for row in
                   connection.execute("PRAGMA table_info(orders)").fetchall()}
        columns |= {row[1].lower() for row in
                    connection.execute("PRAGMA table_info(order_lines)").fetchall()}
    forbidden = {"card", "card_number", "pan", "cvv", "cvc", "expiry",
                 "exp_month", "exp_year", "token", "account_number"}
    assert not (columns & forbidden), columns & forbidden


def test_checkout_page_requests_no_card_details(client):
    client.post("/cart", data={"p_id": "10145", "qty": "1"})
    body = client.get("/checkout").text
    for name in ("card", "cvv", "cvc", "expiry", "cardnumber"):
        assert f'name="{name}"' not in body.lower(), name


def test_minicart_is_answered(client):
    """The header fetches this on every page load; it was 404ing on 27 of 60
    audited routes."""
    response = client.get("/cart/minicart")
    assert response.status_code == 200
    assert "data-cart-count" in response.text


# --------------------------------------------------------------------------- #
# Assets and closure
# --------------------------------------------------------------------------- #

def test_stylesheets_are_served_with_the_right_media_type(client):
    response = client.get(
        "/static/assets/www.monoprice.com/assets/css/bootstrap.min.css")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")


def test_runtime_injected_scripts_are_served_at_the_source_paths(client):
    """RequireJS and /src/index.js build these URLs at run time, so no rewriting
    reaches them. /Scripts/Footer.js defines the element that renders the whole
    footer and appears in no page's markup."""
    for path in ("/Scripts/Footer.js", "/Scripts/lit-all.min.js",
                 "/src/index.js", "/assets/js/mp_productpage.js"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["content-type"].startswith(
            ("application/javascript", "text/javascript")), path


def test_served_css_contains_no_absolute_source_urls():
    """A stylesheet's own url() references are not reachable by the freezer,
    which rewrites HTML. 89 of them pointed at the source until patched."""
    offenders = []
    for path in (ASSET_ROOT / "www.monoprice.com").rglob("*.css"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(
                r"https?://(?:images|www)\.monoprice\.com/[^\s\"')]+", text):
            # A reference left alone because we do not hold the bytes is
            # deliberate; rewriting it to a local 404 would be worse.
            target = match.group(0).split("monoprice.com/", 1)[1]
            host = "images.monoprice.com" if "//images." in match.group(0) \
                else "www.monoprice.com"
            if (ASSET_ROOT / host / target).is_file():
                offenders.append((path.name, match.group(0)[:80]))
    assert not offenders, f"{len(offenders)} rewritable absolute refs remain"


def test_frozen_pages_are_stored_compressed():
    plain = list(FROZEN_ROOT.rglob("*.html"))
    assert not plain, f"{len(plain)} uncompressed frozen pages on disk"
    assert len(list(FROZEN_ROOT.rglob("*.html.gz"))) > 5_000


def test_the_error_pages_exist_and_are_the_sites_own():
    not_found = FROZEN_ROOT / "_error" / "not-found.html.gz"
    absent = FROZEN_ROOT / "_error" / "absent-product.html.gz"
    assert not_found.is_file() and absent.is_file()
    with gzip.open(not_found, "rb") as handle:
        text = handle.read().decode("utf-8", "replace").lower()
    assert "httperror404" in text.replace(" ", "")


def test_no_robots_disallowed_path_was_captured():
    """The wishlist writer is linked as /product/ProductSavedListUpdate, which
    does not match /ProductSavedListUpdate as a prefix. 3,745 such URLs reached
    the queue before the check became per-segment."""
    import sys
    sys.path.insert(0, str(SITE_DIR / "tools"))
    from capture_pages import disallowed

    queue = json.loads((SITE_DIR / "scope" / "capture-queue.json").read_text())
    captured = [url for url, entry in queue["entries"].items()
                if entry.get("state") == "done"]
    import urllib.parse
    bad = [u for u in captured if disallowed(urllib.parse.urlsplit(u).path)]
    assert not bad, f"{len(bad)} robots-disallowed paths were captured: {bad[:3]}"


def test_detail_template_has_every_placeholder_filled(client):
    """A placeholder that was never substituted renders the donor's own data
    under another product's name -- or prints the token as a URL."""
    response = client.get("/product?p_id=48458")
    assert response.status_code == 200
    assert "@@WB_" not in response.text


def test_search_template_has_every_placeholder_filled(client):
    response = client.get("/search/index?keyword=cable")
    assert response.status_code == 200
    assert "@@WB_" not in response.text


@pytest.mark.parametrize("path", ["/", "/cart", "/checkout"])
def test_content_security_policy_is_sent(client, path):
    """Widening a strip list is a race against the next injection technique; the
    header refuses the request before it leaves the machine."""
    response = client.get(path)
    policy = response.headers.get("content-security-policy", "")
    assert "default-src 'self'" in policy


def test_declared_absent_services_answer_json_404_not_empty_200(client):
    """An empty success tells the caller it worked, and it then reads fields
    that are not there. On the previous site that blanked every product page."""
    for path in ("/v1/inventory/x", "/api/live-chat", "/securemetrics/collect"):
        response = client.get(path)
        assert response.status_code == 404, path
        assert response.headers["content-type"].startswith("application/json"), path


def test_catalogue_and_database_agree(backend, catalogue):
    with backend.lifecycle.connection() as connection:
        connection.row_factory = sqlite3.Row
        count = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    assert count == len(catalogue["products"])


# --------------------------------------------------------------------------- #
# Controls, not endpoints
# --------------------------------------------------------------------------- #

def test_cart_accepts_the_path_the_sites_own_script_posts_to(client):
    """minicart.js posts to `/Cart`, with a capital C.

    FastAPI paths are case-sensitive, so this was answered 404 and the Add to
    Cart button did nothing -- the core commerce action, dead. Every test in
    this file passed throughout, because they all POST to `/cart` directly:
    they tested the endpoint and never the control.
    """
    for path in ("/cart", "/Cart", "/CART", "/cart/index", "/Cart/Index"):
        response = client.post(path, data={"p_id": "10145", "qty": "1"},
                               follow_redirects=True)
        assert response.status_code == 200, f"{path} -> {response.status_code}"
        assert "10145" in response.text, f"{path} did not add the item"


def test_the_sites_own_scripts_are_present_to_wire_the_controls(client):
    """The Add to Cart control is an <a>, wired by minicart.js.

    Without the script the element is inert: it renders, it is visible, it has
    the right text, and clicking it does nothing. No closure gate can see that.
    """
    response = client.get("/assets/js/minicart.js")
    assert response.status_code == 200
    assert "Cart" in response.text
