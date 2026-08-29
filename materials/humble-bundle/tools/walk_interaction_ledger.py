#!/usr/bin/env python3
"""Walk the humble-bundle clone route/state matrix and emit the phase-9
interaction ledger.

Every row in ``scope/interaction-ledger.json`` comes from a control this
script actually activated in a headless Chromium session against the running
loopback clone: the selector is the one the walk used, and both proofs are
re-verified against the post-action document before the row is accepted. No
proof is copied from scope prose and no proof is inferred from a selector.

Conventions (fixed so the ledger is machine-checkable):

* ``clone_url`` is the URL **where the control was activated**. For
  ``action: "state"`` rows (page loads, hover-driven panels, the anonymous
  secure-area redirect) it is the URL of the observed document. A row therefore
  reads "at ``clone_url``, do ``action`` on ``selector``, then both proofs
  hold".
* ``visible_text_proof`` is checked against a *visible* tag-stripped,
  entity-decoded serialisation of the post-action document: ``textContent`` of
  every element that is not ``display:none`` / ``visibility:hidden`` and not
  ``script`` / ``style`` / ``template`` / ``noscript``, whitespace collapsed.
  Because it is ``textContent``-derived it is **not** CSS ``text-transform``-ed
  (the 404 headline is recorded in its DOM case, not the uppercased rendering).
* ``raw_markup_proof`` is checked as an exact substring of ``page.content()``
  with ``script`` / ``style`` bodies removed.
* ``form_action`` carries the API path or navigation target behind a mutation
  and is ``null`` for pure view changes. Per-order paths are recorded as
  templates (``/api/purchase/{order_no}/reveal-key``) so no order number ever
  enters the artifact.

Viewport: 1152x900. That is the widest desktop width at which *every* control
the walk activates passes a real Playwright hit test. At the canonical capture
width (1440x900) the frozen ``#js-background-container`` hero image of the
store shell paints over the injected ``/checkout`` panel and intercepts the
pointer for the delivery radios (measured: hero spans document y 119..557, the
delivery radios sit at y 477/502). Below 1120 the frozen desktop navbar is
replaced by the mobile nav, so 1152 is the only safe band. Recorded as a
clone defect, not worked around with forced clicks.

Secret hygiene: the sandbox registration code is read out of the page only to
type it back and is never stored; key material, order numbers, session cookies
and passwords are rejected by :func:`Ledger.add` before a row is accepted.

Deterministic and re-runnable: the DB is reset through ``POST /__admin/reset``
at the start and at the end of the walk, the emitted JSON carries no clock or
run id, and two consecutive runs produce byte-identical output.

Usage::

    python tools/walk_interaction_ledger.py --base-url http://127.0.0.1:8098
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

SITE_ID = "humble-bundle"
SITE_ROOT = Path(__file__).resolve().parents[1]
LEDGER_SCHEMA = "humble-bundle.interaction-ledger.v1"
DEFAULT_BASE_URL = "http://127.0.0.1:8098"
DEFAULT_OUTPUT = SITE_ROOT / "scope" / "interaction-ledger.json"

VIEWPORT = {"width": 1152, "height": 900}
ACTION_TIMEOUT_MS = 15000
SETTLE_TIMEOUT_MS = 12000

# Seeded synthetic fixtures. The demo credential pair is the one declared by
# clone/backend/catalog_db.py (DEMO_EMAIL / DEMO_PASSWORD); the walk account is
# created and destroyed inside a single run by the bracketing admin resets.
DEMO_EMAIL = "demo.gamer@example.test"
DEMO_PASSWORD = "HumbleDemo!2026"
WALK_EMAIL = "walk.newcomer@example.test"
WALK_PASSWORD = "WalkDemo!2026"

ANCHOR_BUNDLE = "yes-chef-cooking-bundle"
PREVIEW_ENDPOINT = f"/api/bundle/{ANCHOR_BUNDLE}/preview"

ALLOWED_ACTIONS = {"click", "submit", "fill+submit", "state"}
ALLOWED_ROLES = {"visitor", "account-holder"}
MAX_PROOF_LEN = 120

# Journey ids come from scope/journeys.json; anything not listed there is a
# walk bug, not a new journey.
JOURNEY_IDS = {
    "core-671", "entry-nav", "browse", "search", "sort-compare", "detail",
    "tiers", "tiers-below-floor", "wishlist", "register", "register-invalid",
    "login-logout", "login-wrong-password", "password-recovery", "cart",
    "delivery-gift", "checkout-promo-declined", "library-keys",
    "history-manage", "no-results", "validation-permissions", "help",
    "not-found",
}

# Proof strings must never carry credential, key, order or session material.
FORBIDDEN_PROOF_PATTERNS = (
    # Synthetic key shape is SANDBOX-XXXX-XXXX-XXXX (hex groups); the
    # sandbox-<scenario> ids are deliberately not matched.
    ("sandbox key material", re.compile(r"SANDBOX-[0-9a-f]{4}-[0-9a-f]{4}", re.I)),
    ("order number", re.compile(r"\bHB20\d{6,}")),
    ("long digit run (otp/order/session)", re.compile(r"\d{6,}")),
    ("email address", re.compile(r"@")),
    ("demo password", re.compile(re.escape(DEMO_PASSWORD))),
    ("walk password", re.compile(re.escape(WALK_PASSWORD))),
    ("session token", re.compile(r"session_[A-Za-z0-9_-]{8,}")),
    ("cookie header", re.compile(r"(?i)\b(set-)?cookie\b")),
)

# Content-addressed static asset paths are sha256 digests of repo bytes: stable
# across runs, and not credential, order or session material, so they are the
# one value shape exempt from the digit-run screen.
ASSET_PATH_RE = re.compile(r"^/static/assets/[0-9a-f]{64}\.[a-z0-9]+$")

# textContent of every element that is not display:none / visibility:hidden,
# with script/style/template/noscript dropped: "tags stripped, entities
# decoded" restricted to what the browser actually paints.
VISIBLE_TEXT_JS = """() => {
  const skip = new Set(['SCRIPT', 'STYLE', 'TEMPLATE', 'NOSCRIPT']);
  const walk = (node) => {
    let out = '';
    for (const child of node.childNodes) {
      if (child.nodeType === 3) { out += child.nodeValue; continue; }
      if (child.nodeType !== 1) continue;
      if (skip.has(child.tagName)) continue;
      const cs = getComputedStyle(child);
      if (cs.display === 'none' || cs.visibility === 'hidden') continue;
      out += ' ' + walk(child) + ' ';
    }
    return out;
  };
  return walk(document.body);
}"""

HIT_TEST_JS = """(sel) => {
  const el = document.querySelector(sel);
  if (!el) return {found: false};
  el.scrollIntoView({block: 'center', inline: 'center'});
  const r = el.getBoundingClientRect();
  const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
  return {
    found: true,
    reachable: !!hit && (hit === el || el.contains(hit) || hit.contains(el)),
    blocker: hit ? (hit.id || String(hit.className) || hit.tagName) : null,
  };
}"""

SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.S | re.I)
WS_RE = re.compile(r"\s+")


class WalkError(RuntimeError):
    """A control could not be activated, or a proof did not hold."""


# ---------------------------------------------------------------------------
# clone plumbing
# ---------------------------------------------------------------------------
def admin_reset(base_url: str, token: str) -> None:
    """Restore the frozen catalog, demo account and seeded history."""
    request = urllib.request.Request(
        f"{base_url}/__admin/reset",
        method="POST",
        headers={"X-WebsiteBench-Admin-Token": token},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("reset"):
        raise WalkError(f"admin reset refused: {payload}")


def raw_redirect(base_url: str, path: str) -> tuple[int, str]:
    """GET ``path`` without following redirects; return (status, location)."""

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args: Any, **kwargs: Any) -> None:
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(f"{base_url}{path}", timeout=20) as response:
            return response.status, response.headers.get("location", "")
    except urllib.error.HTTPError as exc:  # 3xx surfaces here with no handler
        return exc.code, exc.headers.get("location", "")


# ---------------------------------------------------------------------------
# proof extraction
# ---------------------------------------------------------------------------
def visible_text(page: Page) -> str:
    return WS_RE.sub(" ", page.evaluate(VISIBLE_TEXT_JS)).strip()


def raw_markup(page: Page) -> str:
    return SCRIPT_STYLE_RE.sub("", page.content())


# Same walker as VISIBLE_TEXT_JS, inlined as a predicate. The clone serves a
# strict CSP (script-src 'self'), so building it with `new Function` is blocked.
WAIT_VISIBLE_JS = """(needle) => {
  const skip = new Set(['SCRIPT', 'STYLE', 'TEMPLATE', 'NOSCRIPT']);
  const walk = (node) => {
    let out = '';
    for (const child of node.childNodes) {
      if (child.nodeType === 3) { out += child.nodeValue; continue; }
      if (child.nodeType !== 1) continue;
      if (skip.has(child.tagName)) continue;
      const cs = getComputedStyle(child);
      if (cs.display === 'none' || cs.visibility === 'hidden') continue;
      out += ' ' + walk(child) + ' ';
    }
    return out;
  };
  return walk(document.body).replace(/\\s+/g, ' ').indexOf(needle) >= 0;
}"""


def wait_for_visible(page: Page, needle: str, timeout_ms: int = SETTLE_TIMEOUT_MS) -> None:
    """Poll the visible-text serialisation until ``needle`` shows up."""
    page.wait_for_function(WAIT_VISIBLE_JS, arg=needle, timeout=timeout_ms)


def wait_for_markup(page: Page, needle: str, timeout_ms: int = SETTLE_TIMEOUT_MS) -> None:
    page.wait_for_function(
        "(needle) => document.documentElement.outerHTML.indexOf(needle) >= 0",
        arg=needle,
        timeout=timeout_ms,
    )


def assert_reachable(page: Page, selector: str) -> None:
    """Fail loudly when another element would swallow the click."""
    result = page.evaluate(HIT_TEST_JS, selector)
    if not result.get("found"):
        raise WalkError(f"selector not present: {selector}")
    if not result.get("reachable"):
        raise WalkError(
            f"selector {selector} is covered by "
            f"{result.get('blocker')!r} and cannot be clicked"
        )


def unique(page: Page, selector: str) -> str:
    count = page.locator(selector).count()
    if count != 1:
        raise WalkError(f"selector {selector} matched {count} elements, want 1")
    return selector


# ---------------------------------------------------------------------------
# ledger
# ---------------------------------------------------------------------------
class Ledger:
    """Collects verified rows and rejects anything unproven or unsafe."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def _evidence_id(self) -> str:
        return f"led-{len(self.entries) + 1:03d}"

    @staticmethod
    def _screen(field: str, value: str) -> None:
        if len(value) >= MAX_PROOF_LEN:
            raise WalkError(f"{field} is {len(value)} chars, must stay under {MAX_PROOF_LEN}")
        content_addressed = bool(ASSET_PATH_RE.match(value))
        for label, pattern in FORBIDDEN_PROOF_PATTERNS:
            if content_addressed and label.startswith("long digit run"):
                continue
            if pattern.search(value):
                raise WalkError(f"{field} contains {label}: {value!r}")

    def add(
        self,
        page: Page | None,
        *,
        journey_id: str,
        role: str,
        state: str,
        clone_url: str,
        action: str,
        selector: str | None,
        form_action: str | None,
        visible_text_proof: str,
        raw_markup_proof: str,
        raw_source: str | None = None,
    ) -> None:
        if journey_id not in JOURNEY_IDS:
            raise WalkError(f"unknown journey id {journey_id!r}")
        if role not in ALLOWED_ROLES:
            raise WalkError(f"unknown role {role!r}")
        if action not in ALLOWED_ACTIONS:
            raise WalkError(f"unknown action {action!r}")
        self._screen("visible_text_proof", visible_text_proof)
        self._screen("raw_markup_proof", raw_markup_proof)

        if page is not None:
            # Poll first so an in-flight XHR render cannot flake the row, then
            # assert strictly against the two serialisations the ledger claims.
            try:
                wait_for_visible(page, visible_text_proof)
            except PlaywrightTimeoutError:
                pass
            if raw_source is None:
                try:
                    wait_for_markup(page, raw_markup_proof)
                except PlaywrightTimeoutError:
                    pass
            seen_text = visible_text(page)
            if visible_text_proof not in seen_text:
                raise WalkError(
                    f"visible proof missing after {action} on {selector!r}: "
                    f"{visible_text_proof!r}"
                )
            markup = raw_source if raw_source is not None else raw_markup(page)
            if raw_markup_proof not in markup:
                raise WalkError(
                    f"raw proof missing after {action} on {selector!r}: "
                    f"{raw_markup_proof!r}"
                )
        elif raw_source is not None and raw_markup_proof not in raw_source:
            raise WalkError(f"raw proof missing in supplied source: {raw_markup_proof!r}")

        self.entries.append(
            {
                "journey_id": journey_id,
                "role": role,
                "state": state,
                "clone_url": clone_url,
                "action": action,
                "selector": selector,
                "selector_provenance": "walk",
                "form_action": form_action,
                "visible_text_proof": visible_text_proof,
                "raw_markup_proof": raw_markup_proof,
                "evidence_id": self._evidence_id(),
            }
        )


# ---------------------------------------------------------------------------
# walk helpers
# ---------------------------------------------------------------------------
def goto(page: Page, base_url: str, path: str) -> None:
    page.goto(f"{base_url}{path}", wait_until="load", timeout=30000)
    page.wait_for_timeout(350)


def click(page: Page, selector: str) -> None:
    unique(page, selector)
    assert_reachable(page, selector)
    page.click(selector, timeout=ACTION_TIMEOUT_MS)


def check(page: Page, selector: str) -> None:
    unique(page, selector)
    assert_reachable(page, selector)
    page.check(selector, timeout=ACTION_TIMEOUT_MS)


def uncheck(page: Page, selector: str) -> None:
    unique(page, selector)
    assert_reachable(page, selector)
    page.uncheck(selector, timeout=ACTION_TIMEOUT_MS)


def sign_in(page: Page, base_url: str, email: str, password: str) -> None:
    goto(page, base_url, "/login")
    page.fill("input[name='username']", email)
    page.fill("input[name='password']", password)
    click(page, "form[action='/processlogin'] button[type='submit']")
    page.wait_for_url(f"{base_url}/", timeout=ACTION_TIMEOUT_MS)
    page.wait_for_timeout(400)


def set_custom_amount(page: Page, value: str, expect_visible: str) -> None:
    page.fill("input.js-custom-amount", value)
    wait_for_visible(page, expect_visible)


# ---------------------------------------------------------------------------
# leg 1: visitor
# ---------------------------------------------------------------------------
def walk_visitor(page: Page, base_url: str, ledger: Ledger) -> None:
    visitor = {"role": "visitor"}

    # -- entry-nav ---------------------------------------------------------
    goto(page, base_url, "/")
    ledger.add(
        page, journey_id="entry-nav", state="loaded", clone_url=f"{base_url}/",
        action="state", selector=unique(page, ".js-humble-home"), form_action=None,
        visible_text_proof="Humble 15th Anniversary Summer Sale",
        raw_markup_proof='<h2 class="title">Humble 15th Anniversary Summer Sale',
        **visitor,
    )

    bundles_dropdown = "section.tabs > .nav-dropdown-container:nth-of-type(1)"
    unique(page, bundles_dropdown)
    page.hover(bundles_dropdown, timeout=ACTION_TIMEOUT_MS)
    wait_for_markup(
        page, '<div class="navbar-item-dropdown-container nav-dropdown" style="display: block;">'
    )
    ledger.add(
        page, journey_id="entry-nav", state="nav-dropdown-open",
        clone_url=f"{base_url}/", action="state", selector=bundles_dropdown,
        form_action=None,
        visible_text_proof="Games Books Software",
        raw_markup_proof='<div class="navbar-item-dropdown-container nav-dropdown" style="display: block;">',
        **visitor,
    )

    nav_bundles = 'section.tabs .nav-dropdown-container a[href="/bundles"][role="button"]'
    click(page, nav_bundles)
    page.wait_for_url(f"{base_url}/bundles", timeout=ACTION_TIMEOUT_MS)
    wait_for_visible(page, "Humble Bundles")
    ledger.add(
        page, journey_id="entry-nav", state="loaded", clone_url=f"{base_url}/",
        action="click", selector=nav_bundles, form_action=None,
        visible_text_proof="Humble Bundles",
        raw_markup_proof="<h1>Humble Bundles</h1>",
        **visitor,
    )

    # -- browse ------------------------------------------------------------
    ledger.add(
        page, journey_id="browse", state="loaded", clone_url=f"{base_url}/bundles",
        action="state", selector=unique(page, ".intro-section-text h1"), form_action=None,
        visible_text_proof="Humble Bundles",
        raw_markup_proof="<h1>Humble Bundles</h1>",
        **visitor,
    )

    games_chip = '.page-navigation-container a[href="/games"]'
    click(page, games_chip)
    page.wait_for_url(f"{base_url}/games", timeout=ACTION_TIMEOUT_MS)
    wait_for_visible(page, "Games Bundles")
    ledger.add(
        page, journey_id="browse", state="loaded", clone_url=f"{base_url}/bundles",
        action="click", selector=games_chip, form_action=None,
        visible_text_proof="Games Bundles",
        raw_markup_proof="<h1>Games Bundles</h1>",
        **visitor,
    )

    # -- search ------------------------------------------------------------
    header_search = unique(page, "input.js-search")
    page.fill(header_search, "portal")
    page.press(header_search, "Enter")
    page.wait_for_url(f"{base_url}/store/search?search=portal", timeout=ACTION_TIMEOUT_MS)
    wait_for_visible(page, "29 Results")
    ledger.add(
        page, journey_id="search", state="results", clone_url=f"{base_url}/games",
        action="fill+submit", selector=header_search, form_action="/store/search",
        visible_text_proof="29 Results",
        raw_markup_proof='<h1 class="js-title-text">29 Results</h1>',
        **visitor,
    )

    search_url = page.url
    genre_dropdown = ".search-filters-view > div:nth-child(3) .js-filter-dropdown"
    click(page, genre_dropdown)
    wait_for_visible(page, "Adventure")
    ledger.add(
        page, journey_id="search", state="filter-dropdown-open", clone_url=search_url,
        action="click", selector=genre_dropdown, form_action=None,
        visible_text_proof="Adventure",
        raw_markup_proof='js-dropdown-options no-style-list" style="display: block;"',
        **visitor,
    )

    genre_option = 'input.js-filter-option[name="genre"][value="adventure"]'
    check(page, genre_option)
    wait_for_visible(page, "7 Results")
    ledger.add(
        page, journey_id="search", state="filtered", clone_url=search_url,
        action="click", selector=genre_option, form_action="/api/search",
        visible_text_proof="7 Results",
        raw_markup_proof='<h1 class="js-title-text">7 Results</h1>',
        **visitor,
    )

    # -- sort-compare ------------------------------------------------------
    filtered_url = page.url
    sort_dropdown = ".search-filters-view > div:nth-child(2) .js-filter-dropdown"
    click(page, sort_dropdown)
    wait_for_visible(page, "Top Discounts")
    ledger.add(
        page, journey_id="sort-compare", state="filter-dropdown-open",
        clone_url=filtered_url, action="click", selector=sort_dropdown, form_action=None,
        visible_text_proof="Top Discounts",
        raw_markup_proof='js-dropdown-options no-style-list" style="display: block;"',
        **visitor,
    )

    sort_option = 'a.js-option[data-option-value="alphabetical"]'
    click(page, sort_option)
    wait_for_markup(
        page, '<span class="current-filter-option js-current-option">Alphabetical</span>'
    )
    ledger.add(
        page, journey_id="sort-compare", state="sorted", clone_url=filtered_url,
        action="click", selector=sort_option, form_action="/api/search",
        visible_text_proof="Alphabetical",
        raw_markup_proof='<span class="current-filter-option js-current-option">Alphabetical</span>',
        **visitor,
    )

    # -- no-results --------------------------------------------------------
    no_results_url = "/store/search?search=zzzz-no-match-websitebench"
    goto(page, base_url, no_results_url)
    ledger.add(
        page, journey_id="no-results", state="no-results",
        clone_url=f"{base_url}{no_results_url}", action="state",
        selector=unique(page, "h1.js-title-text"), form_action=None,
        visible_text_proof="0 Results",
        raw_markup_proof='<h1 class="js-title-text">0 Results</h1>',
        **visitor,
    )

    # -- detail ------------------------------------------------------------
    product_url = f"{base_url}/store/satisfactory"
    goto(page, base_url, "/store/satisfactory")
    ledger.add(
        page, journey_id="detail", state="loaded", clone_url=product_url,
        action="state", selector=unique(page, ".js-human-name h1"), form_action=None,
        visible_text_proof="Satisfactory",
        raw_markup_proof='human_name-view js-admin-edit">Satisfactory',
        **visitor,
    )

    gallery_main = ".js-hb-gallery-main"
    page.wait_for_selector(gallery_main, timeout=SETTLE_TIMEOUT_MS)
    before_src = page.get_attribute(gallery_main, "src") or ""
    thumbnail = '.js-media-thumbnails [data-slick-index="0"] .thumbnail'
    click(page, thumbnail)
    page.wait_for_function(
        "([sel, before]) => { const e = document.querySelector(sel);"
        " return e && e.getAttribute('src') !== before; }",
        arg=[gallery_main, before_src],
        timeout=SETTLE_TIMEOUT_MS,
    )
    swapped = page.get_attribute(gallery_main, "src") or ""
    swapped_path = swapped[swapped.index("/static/assets/"):]
    ledger.add(
        page, journey_id="detail", state="gallery-swapped", clone_url=product_url,
        action="click", selector=thumbnail, form_action=None,
        visible_text_proof="Satisfactory",
        raw_markup_proof=swapped_path,
        **visitor,
    )

    # -- cart --------------------------------------------------------------
    cart_button = "button.js-cart.white"
    click(page, cart_button)
    wait_for_visible(page, "Your cart is empty")
    ledger.add(
        page, journey_id="cart", state="empty", clone_url=product_url,
        action="click", selector=cart_button, form_action="/api/cart",
        visible_text_proof="Your cart is empty",
        raw_markup_proof='<div class="shopping-cart-empty"><p>Your cart is empty</p></div>',
        **visitor,
    )

    # Reload: the open drawer's grayout overlays the page behind it.
    goto(page, base_url, "/store/satisfactory")
    add_to_cart = ".js-shopping-cart-button button.add"
    click(page, add_to_cart)
    wait_for_visible(page, "Satisfactory Redeem for Windows")
    ledger.add(
        page, journey_id="cart", state="populated", clone_url=product_url,
        action="click", selector=add_to_cart, form_action="/api/cart/add",
        visible_text_proof="Satisfactory Redeem for Windows Redeem for Windows Original amount",
        raw_markup_proof='<a href="/store/satisfactory" class="cart-item-name" title="Satisfactory">',
        **visitor,
    )

    # The source's own remove control, addressed through its accessible label.
    remove_button = '#js-cart-container .js-remove-from-cart[aria-label="Remove from cart"]'
    click(page, remove_button)
    wait_for_visible(page, "Removed Satisfactory")
    ledger.add(
        page, journey_id="cart", state="item-removed", clone_url=product_url,
        action="click", selector=remove_button, form_action="/api/cart/remove",
        visible_text_proof="Removed Satisfactory — Undo",
        raw_markup_proof=">Removed Satisfactory — <button",
        **visitor,
    )

    undo_button = "#js-cart-container .js-cart-notifications button"
    click(page, undo_button)
    wait_for_visible(page, "Satisfactory Redeem for Windows")
    ledger.add(
        page, journey_id="cart", state="item-restored", clone_url=product_url,
        action="click", selector=undo_button, form_action="/api/cart/restore",
        visible_text_proof="Satisfactory Redeem for Windows Redeem for Windows Original amount",
        raw_markup_proof='<a href="/store/satisfactory" class="cart-item-name" title="Satisfactory">',
        **visitor,
    )

    # The frozen store-page drawer has no working checkout control (its
    # .js-payment-button pair sits outside .checkout-section, which is the only
    # subtree hb-app.js wires). The drawer hb-app.js *constructs* on pages
    # without #js-cart-container does carry one, so the drawer-open and
    # drawer-checkout controls are walked on the home shell.
    goto(page, base_url, "/")
    cart_icon = "a.js-hb-cart-icon"
    page.wait_for_selector(cart_icon, state="visible", timeout=SETTLE_TIMEOUT_MS)
    click(page, cart_icon)
    wait_for_visible(page, "Shopping Cart Satisfactory")
    ledger.add(
        page, journey_id="cart", state="populated", clone_url=f"{base_url}/",
        action="click", selector=cart_icon, form_action="/api/cart",
        visible_text_proof="Shopping Cart Satisfactory Redeem for Windows",
        raw_markup_proof="<h1>Shopping Cart</h1>",
        **visitor,
    )

    drawer_checkout = "a.js-hb-drawer-checkout"
    click(page, drawer_checkout)
    page.wait_for_url(re.compile(r"/login\?goto=%2Fcheckout"), timeout=ACTION_TIMEOUT_MS)
    wait_for_visible(page, "Log In")
    ledger.add(
        page, journey_id="cart", state="populated", clone_url=f"{base_url}/",
        action="click", selector=drawer_checkout, form_action="/checkout",
        visible_text_proof="Don't have an account?",
        raw_markup_proof='<h1 class="header">Log In</h1>',
        **visitor,
    )

    # -- tiers -------------------------------------------------------------
    bundle_url = f"{base_url}/games/{ANCHOR_BUNDLE}"
    goto(page, base_url, f"/games/{ANCHOR_BUNDLE}")
    preset = 'label[for="preset-18.03"]'
    click(page, preset)
    wait_for_visible(page, "You will get 13 items.")
    ledger.add(
        page, journey_id="tiers", state="tier2", clone_url=bundle_url,
        action="click", selector=preset, form_action=PREVIEW_ENDPOINT,
        visible_text_proof=(
            "You will get 13 items. You're missing out on "
            "Tavern Manager Simulator and 2 more!"
        ),
        raw_markup_proof='item-count-text">You will get 13 items.',
        **visitor,
    )

    custom_amount = "input.js-custom-amount"
    # The frozen CA$15 unlock sentence is exactly 120 characters, one over the
    # per-proof budget, so it is split across the two proof fields: the raw
    # proof pins the head (with the hook that carries it) and the visible proof
    # pins the tail. Both halves are exact substrings of the rendered oracle.
    set_custom_amount(page, "15", "You will get 7 items.")
    ledger.add(
        page, journey_id="tiers", state="custom15", clone_url=bundle_url,
        action="fill+submit", selector=custom_amount, form_action=PREVIEW_ENDPOINT,
        visible_text_proof=(
            "You're missing out on Tavern Manager Simulator and 8 more! "
            "Pay at least CA$22.19 to get all items."
        ),
        raw_markup_proof=(
            'item-count-text">You will get 7 items. '
            "<strong>You're missing out</strong> on Tavern Manager Simulator"
        ),
        **visitor,
    )

    set_custom_amount(page, "5", "The minimum price for this bundle is CA$9.71.")
    ledger.add(
        page, journey_id="tiers-below-floor", state="below-floor",
        clone_url=bundle_url, action="fill+submit", selector=custom_amount,
        form_action=PREVIEW_ENDPOINT,
        visible_text_proof="The minimum price for this bundle is CA$9.71.",
        raw_markup_proof=(
            '<span class="js-error-and-infotip error-and-infotip">'
            "The minimum price for this bundle is CA$9.71."
        ),
        **visitor,
    )

    splits_toggle = ".js-splits-toggle"
    click(page, splits_toggle)
    wait_for_visible(page, "Default Donation")
    ledger.add(
        page, journey_id="tiers", state="split-open", clone_url=bundle_url,
        action="click", selector=splits_toggle, form_action=None,
        visible_text_proof="Default Donation",
        raw_markup_proof='<section class="splits-information js-splits-info" style="display: block;">',
        **visitor,
    )

    split_radio = 'input.js-split-allocation[value="custom"]'
    check(page, split_radio)
    ledger.add(
        page, journey_id="tiers", state="split-custom", clone_url=bundle_url,
        action="click", selector=split_radio, form_action=None,
        visible_text_proof="Custom Amount",
        raw_markup_proof=(
            '<input type="radio" class="light-radio-button js-split-allocation" '
            'name="split-allocation" value="custom">'
        ),
        **visitor,
    )

    # -- help --------------------------------------------------------------
    goto(page, base_url, "/support")
    ledger.add(
        page, journey_id="help", state="loaded", clone_url=f"{base_url}/support",
        action="state", selector=unique(page, ".recent-activity-header"), form_action=None,
        visible_text_proof="Recent activity",
        raw_markup_proof='<h2 class="recent-activity-header">Recent activity</h2>',
        **visitor,
    )

    category_link = 'a[href="/support/categories/200166394"]'
    click(page, category_link)
    page.wait_for_url(f"{base_url}/support/categories/200166394", timeout=ACTION_TIMEOUT_MS)
    wait_for_visible(page, "Key Redemption")
    ledger.add(
        page, journey_id="help", state="loaded", clone_url=f"{base_url}/support",
        action="click", selector=category_link, form_action=None,
        visible_text_proof="Key Redemption",
        raw_markup_proof="<h1>Key Redemption</h1>",
        **visitor,
    )

    article_link = 'a[href="/support/articles/52764568066971"]'
    click(page, article_link)
    page.wait_for_url(f"{base_url}/support/articles/52764568066971", timeout=ACTION_TIMEOUT_MS)
    wait_for_visible(page, "Redemption Instructions")
    ledger.add(
        page, journey_id="help", state="loaded",
        clone_url=f"{base_url}/support/categories/200166394", action="click",
        selector=article_link, form_action=None,
        visible_text_proof="Freedom to Create with COREL Graphics Suite 2025",
        raw_markup_proof=(
            "<h1> Freedom to Create with COREL Graphics Suite 2025 - "
            "Redemption Instructions</h1>"
        ),
        **visitor,
    )

    # -- not-found ---------------------------------------------------------
    missing = "/this-page-does-not-exist-websitebench"
    goto(page, base_url, missing)
    ledger.add(
        page, journey_id="not-found", state="not-found",
        clone_url=f"{base_url}{missing}", action="state",
        selector=unique(page, "h1.error-header"), form_action=None,
        visible_text_proof="The page you requested cannot be found",
        raw_markup_proof='<h1 class="error-header">The page you requested cannot be found</h1>',
        **visitor,
    )

    # -- validation-permissions -------------------------------------------
    status, location = raw_redirect(base_url, "/home/library")
    if status != 302:
        raise WalkError(f"anonymous /home/library returned {status}, want 302")
    ledger.add(
        None, journey_id="validation-permissions", state="secure-area-redirect",
        clone_url=f"{base_url}/home/library", action="state", selector=None,
        form_action=None,
        visible_text_proof="Don't have an account?",
        raw_markup_proof="/login?goto=%2Fhome%2Flibrary&qs=reason%3DsecureArea",
        raw_source=location,
        **visitor,
    )

    goto(page, base_url, "/login")
    login_submit = "form[action='/processlogin'] button[type='submit']"
    click(page, login_submit)
    wait_for_visible(page, "email is invalid")
    ledger.add(
        page, journey_id="validation-permissions", state="error",
        clone_url=f"{base_url}/login", action="submit", selector=login_submit,
        form_action="/api/account/login",
        visible_text_proof="email is invalid",
        raw_markup_proof='<div class="status-message js-status-message">email is invalid</div>',
        **visitor,
    )

    # -- login-wrong-password ---------------------------------------------
    page.fill("input[name='username']", DEMO_EMAIL)
    page.fill("input[name='password']", "not-the-demo-password")
    click(page, login_submit)
    wait_for_visible(page, "credentials are invalid")
    ledger.add(
        page, journey_id="login-wrong-password", state="error",
        clone_url=f"{base_url}/login", action="fill+submit", selector=login_submit,
        form_action="/api/account/login",
        visible_text_proof="credentials are invalid",
        raw_markup_proof='<div class="status-message js-status-message">credentials are invalid</div>',
        **visitor,
    )

    # -- password-recovery -------------------------------------------------
    goto(page, base_url, "/login")
    reset_control = ".js-password-reset"
    click(page, reset_control)
    wait_for_visible(page, "Password Reset")
    ledger.add(
        page, journey_id="password-recovery", state="forgot-password",
        clone_url=f"{base_url}/login", action="click", selector=reset_control,
        form_action=None,
        visible_text_proof="We'll send a password setup link to your account's email address.",
        raw_markup_proof='<h1 class="header">Password Reset</h1>',
        **visitor,
    )

    # -- register-invalid / register --------------------------------------
    # The short-password branch writes into .js-input-error, which the frozen
    # CSS keeps display:none, so it yields no gradeable visible proof (recorded
    # clone defect). The rejected-email branch surfaces in the visible
    # .js-status-message, so that is the activation walked here.
    goto(page, base_url, "/signup")
    signup_submit = "form[action='/signup'] button[type='submit']"
    page.fill("form[action='/signup'] input[name='email']", DEMO_EMAIL)
    page.fill("form[action='/signup'] input[name='password']", WALK_PASSWORD)
    click(page, signup_submit)
    wait_for_visible(page, "An account with that email already exists.")
    ledger.add(
        page, journey_id="register-invalid", state="validation-error",
        clone_url=f"{base_url}/signup", action="fill+submit", selector=signup_submit,
        form_action="/api/account/register/start",
        visible_text_proof="An account with that email already exists.",
        raw_markup_proof=(
            '<div class="status-message js-status-message">'
            "An account with that email already exists.</div>"
        ),
        **visitor,
    )

    page.fill("form[action='/signup'] input[name='email']", WALK_EMAIL)
    page.fill("form[action='/signup'] input[name='password']", WALK_PASSWORD)
    click(page, signup_submit)
    wait_for_visible(page, "Verify your email")
    ledger.add(
        page, journey_id="register", state="verification",
        clone_url=f"{base_url}/signup", action="fill+submit", selector=signup_submit,
        form_action="/api/account/register/start",
        visible_text_proof="Verify your email",
        raw_markup_proof='<h1 class="header">Verify your email</h1>',
        **visitor,
    )

    # The sandbox code stands in for the source's verification email. It is
    # read, typed back and dropped; it never reaches the ledger.
    hint = page.text_content(".js-hb-sandbox-hint") or ""
    match = re.search(r"(\d{4,10})", hint)
    if not match:
        raise WalkError("registration sandbox hint carried no code")
    verify_submit = ".js-view-body form button[type='submit']"
    page.fill(".js-view-body form input[name='code']", match.group(1))
    del hint, match
    click(page, verify_submit)
    page.wait_for_url(f"{base_url}/", timeout=ACTION_TIMEOUT_MS)
    wait_for_markup(page, 'class="user-dropdown-container nav-dropdown-container js-hb-account-menu"')
    ledger.add(
        page, journey_id="register", state="loaded", clone_url=f"{base_url}/signup",
        action="fill+submit", selector=verify_submit,
        form_action="/api/account/register/complete",
        visible_text_proof="Humble 15th Anniversary Summer Sale",
        raw_markup_proof='class="user-dropdown-container nav-dropdown-container js-hb-account-menu"',
        **visitor,
    )


# ---------------------------------------------------------------------------
# leg 2: account holder
# ---------------------------------------------------------------------------
def walk_account_holder(page: Page, base_url: str, ledger: Ledger) -> None:
    holder = {"role": "account-holder"}

    # -- login-logout (sign in) -------------------------------------------
    goto(page, base_url, "/login")
    login_submit = "form[action='/processlogin'] button[type='submit']"
    page.fill("input[name='username']", DEMO_EMAIL)
    page.fill("input[name='password']", DEMO_PASSWORD)
    click(page, login_submit)
    page.wait_for_url(f"{base_url}/", timeout=ACTION_TIMEOUT_MS)
    # The source's signed-in navbar carries no display name — it swaps the
    # Sign Up / Log In pair for a user-circle icon whose panel holds the
    # account routes — so the signed-in proof is that account panel, opened.
    page.wait_for_selector(
        ".js-hb-account-menu .js-user-dropdown-container-2021",
        timeout=SETTLE_TIMEOUT_MS,
    )
    click(page, ".js-hb-account-menu .js-user-dropdown-container-2021")
    wait_for_visible(page, "Keys & Entitlements")
    ledger.add(
        page, journey_id="login-logout", state="loaded", clone_url=f"{base_url}/login",
        action="fill+submit", selector=login_submit, form_action="/api/account/login",
        visible_text_proof="Keys & Entitlements",
        raw_markup_proof='class="navbar-item-dropdown-container user-dropdown'
                         ' user-item-dropdown-container',
        **holder,
    )
    page.keyboard.press("Escape")
    click(page, "body")

    # -- wishlist ----------------------------------------------------------
    product_url = f"{base_url}/store/satisfactory"
    goto(page, base_url, "/store/satisfactory")
    wishlist_button = ".js-wishlist-container .js-wishlist-button"
    page.wait_for_selector(wishlist_button, timeout=SETTLE_TIMEOUT_MS)
    click(page, wishlist_button)
    wait_for_markup(page, '<div class="wishlist-button js-wishlist-button saved">')
    # The saved control swaps its own label on :hover ("Remove from wishlist"),
    # so park the pointer before proving the resting label.
    page.mouse.move(2, 2)
    wait_for_visible(page, "On wishlist")
    ledger.add(
        page, journey_id="wishlist", state="populated", clone_url=product_url,
        action="click", selector=wishlist_button, form_action="/api/wishlist/add",
        visible_text_proof="On wishlist",
        raw_markup_proof='<div class="wishlist-button js-wishlist-button saved">',
        **holder,
    )

    # the source serves the wishlist under /store/, not /home/ (handoff tr-001)
    goto(page, base_url, "/store/wishlist")
    wait_for_visible(page, "Satisfactory")
    ledger.add(
        page, journey_id="wishlist", state="populated",
        clone_url=f"{base_url}/store/wishlist", action="state",
        selector=unique(page, ".js-hb-account"), form_action="/api/wishlist",
        visible_text_proof="Satisfactory",
        raw_markup_proof='class="container js-hb-account"',
        **holder,
    )

    # -- cart drawer, signed in (the captured populated drawer) -------------
    # The source's populated drawer is an authenticated surface: the totals
    # block (Sub-Total / Sales Tax / Total), the wallet-credit line and the
    # email identity block only exist once signed in, so they are walked here
    # rather than in the anonymous cart journey. The store flow's tax label is
    # `Sales Tax`; the bundle review below shows the same rate as `HST`.
    goto(page, base_url, "/store/satisfactory")
    drawer_add = ".js-shopping-cart-button button.add"
    click(page, drawer_add)
    wait_for_visible(page, "Sales Tax:")
    ledger.add(
        page, journey_id="cart", state="populated-signed-in", clone_url=product_url,
        action="click", selector=drawer_add, form_action="/api/cart/add",
        visible_text_proof=(
            "Sub-Total: Original amount CA$51.99 Discounted amount CA$36.39 "
            "Sales Tax: CA$4.73"
        ),
        raw_markup_proof='<p class="total-heading">Sales Tax:</p>',
        **holder,
    )
    ledger.add(
        page, journey_id="cart", state="rewards-and-identity", clone_url=product_url,
        action="state",
        selector=unique(page, "#js-cart-container .js-rewards-total-holder"),
        form_action="/api/cart",
        visible_text_proof="Wallet Credit Earned CA$3.64",
        raw_markup_proof='<input type="text" class="email-input js-email" name="email"',
        **holder,
    )

    # Remove it again through the source's own control so the cart is empty for
    # the bundle checkout below (proof stays on the clone-invented undo, which
    # the known-difference list discloses).
    drawer_remove = '#js-cart-container .js-remove-from-cart[aria-label="Remove from cart"]'
    click(page, drawer_remove)
    wait_for_visible(page, "Your cart is empty")
    ledger.add(
        page, journey_id="cart", state="item-removed-signed-in", clone_url=product_url,
        action="click", selector=drawer_remove, form_action="/api/cart/remove",
        visible_text_proof="Removed Satisfactory — Undo",
        raw_markup_proof='class="js-hb-cart-undo"',
        **holder,
    )

    # -- core-671: bundle at CA$15 straight into checkout ------------------
    bundle_url = f"{base_url}/games/{ANCHOR_BUNDLE}"
    goto(page, base_url, f"/games/{ANCHOR_BUNDLE}")
    set_custom_amount(page, "15", "You will get 7 items.")
    bundle_checkout = ".js-checkout-button"
    click(page, bundle_checkout)
    page.wait_for_url(f"{base_url}/checkout", timeout=ACTION_TIMEOUT_MS)
    wait_for_visible(page, "Yes Chef! - Cooking Bundle")
    ledger.add(
        page, journey_id="core-671", state="review", clone_url=bundle_url,
        action="submit", selector=bundle_checkout, form_action="/api/cart/add",
        visible_text_proof="Yes Chef! - Cooking Bundle",
        # the review total is now the tax-inclusive Total the source shows
        raw_markup_proof='<span class="js-hb-checkout-total">CA$16.85</span>',
        **holder,
    )

    checkout_url = f"{base_url}/checkout"

    # -- delivery-gift -----------------------------------------------------
    # the source gates gifting behind an opt-in that reveals an
    # email-versus-link choice, rather than a self/gift radio pair (tr-001)
    gift_optin = 'input[name="gifting-enabled"]'
    check(page, gift_optin)
    wait_for_markup(page, 'name="gift-type" value="gift-recipient-email"')
    ledger.add(
        page, journey_id="delivery-gift", state="review", clone_url=checkout_url,
        action="click", selector=gift_optin, form_action=None,
        visible_text_proof="This purchase is a gift",
        raw_markup_proof='name="gift-type" value="gift-recipient-email"',
        **holder,
    )
    uncheck(page, gift_optin)

    # The source's review carries no split-mode control; the mode chosen on the
    # bundle page carries through, so this journey is covered there instead.

    # -- payment method: the source blocks the submit until one is chosen --
    processor_radio = 'input[name="processor-type"][value="alipay"]'
    check(page, processor_radio)
    ledger.add(
        page, journey_id="checkout-promo-declined", state="review",
        clone_url=checkout_url, action="click", selector=processor_radio,
        form_action=None,
        visible_text_proof="Payment Method",
        raw_markup_proof='name="processor-type" value="alipay"',
        **holder,
    )

    # -- checkout-promo-declined ------------------------------------------
    declined_radio = 'input[name="hb-scenario"][value="sandbox-declined"]'
    check(page, declined_radio)
    ledger.add(
        page, journey_id="checkout-promo-declined", state="review",
        clone_url=checkout_url, action="click", selector=declined_radio,
        form_action=None,
        visible_text_proof="Sandbox declined",
        raw_markup_proof='<input type="radio" name="hb-scenario" value="sandbox-declined">',
        **holder,
    )

    place_order = ".js-hb-place-order"
    click(page, place_order)
    wait_for_visible(page, "Your payment was declined.")
    ledger.add(
        page, journey_id="checkout-promo-declined", state="payment-declined",
        clone_url=checkout_url, action="click", selector=place_order,
        form_action="/api/checkout",
        visible_text_proof=(
            "Your payment was declined. Choose a different payment option "
            "and try again."
        ),
        raw_markup_proof='class="js-hb-checkout-error" style="display: block;',
        **holder,
    )

    approved_radio = 'input[name="hb-scenario"][value="sandbox-approved"]'
    check(page, approved_radio)
    ledger.add(
        page, journey_id="core-671", state="review", clone_url=checkout_url,
        action="click", selector=approved_radio, form_action=None,
        visible_text_proof="Sandbox approved",
        raw_markup_proof='<input type="radio" name="hb-scenario" value="sandbox-approved"',
        **holder,
    )

    click(page, place_order)
    wait_for_visible(page, "Thank you for your order!")
    ledger.add(
        page, journey_id="core-671", state="confirmation", clone_url=checkout_url,
        action="click", selector=place_order, form_action="/api/checkout",
        visible_text_proof="Thank you for your order!",
        raw_markup_proof="<h1>Thank you for your order!</h1>",
        **holder,
    )

    # -- library-keys ------------------------------------------------------
    library_link = '.js-hb-confirmation a[href="/home/library"]'
    click(page, library_link)
    page.wait_for_url(f"{base_url}/home/library", timeout=ACTION_TIMEOUT_MS)
    wait_for_markup(page, "<h1>Humble Library</h1>")
    ledger.add(
        page, journey_id="library-keys", state="populated", clone_url=checkout_url,
        action="click", selector=library_link, form_action="/api/library",
        visible_text_proof="Humble Library",
        raw_markup_proof="<h1>Humble Library</h1>",
        **holder,
    )

    library_url = f"{base_url}/home/library"
    # The library interior now reproduces the captured .hb-download-list split:
    # rows in .js-subproducts-holder, the selected entitlement's downloads and
    # its key control in .js-details-holder.
    reveal_button = ".js-library-holder .js-details-holder button"
    click(page, reveal_button)
    page.wait_for_function(
        "(sel) => { const b = document.querySelector(sel);"
        " return b && getComputedStyle(b).display === 'none'; }",
        arg=reveal_button,
        timeout=SETTLE_TIMEOUT_MS,
    )
    # The rebuilt library shows one entitlement at a time, so the activated
    # control leaves no sibling carrying its label. The proof is the offline
    # hint that persists beside the revealed code, never key material.
    ledger.add(
        page, journey_id="library-keys", state="key-revealed", clone_url=library_url,
        action="click", selector=reveal_button,
        form_action="/api/purchase/{order_no}/reveal-key",
        visible_text_proof="No download payload exists in this clone",
        raw_markup_proof='class="fine-print js-hb-offline-hint"',
        **holder,
    )

    keys_tab = 'nav.tabbar a[href="/home/keys"]'
    click(page, keys_tab)
    page.wait_for_url(f"{base_url}/home/keys", timeout=ACTION_TIMEOUT_MS)
    wait_for_markup(page, "<h1>Keys &amp; Entitlements</h1>")
    ledger.add(
        page, journey_id="library-keys", state="populated", clone_url=library_url,
        action="click", selector=keys_tab, form_action="/api/purchases",
        visible_text_proof="Keys & Entitlements",
        raw_markup_proof="<h1>Keys &amp; Entitlements</h1>",
        **holder,
    )

    # -- history-manage ----------------------------------------------------
    purchases_tab = 'nav.tabbar a[href="/home/purchases"]'
    click(page, purchases_tab)
    page.wait_for_url(f"{base_url}/home/purchases", timeout=ACTION_TIMEOUT_MS)
    wait_for_markup(page, "<h1>Purchased Products</h1>")
    ledger.add(
        page, journey_id="history-manage", state="populated",
        clone_url=f"{base_url}/home/keys", action="click", selector=purchases_tab,
        form_action="/api/purchases",
        visible_text_proof="Purchased Products",
        raw_markup_proof="<h1>Purchased Products</h1>",
        **holder,
    )

    # The purchases interior now uses the captured .results > .body row list
    # under the Product / Date / Total heading columns.
    newest_row = ".js-purchase-holder .results .body > a:first-child"
    click(page, newest_row)
    wait_for_visible(page, "All purchases")
    ledger.add(
        page, journey_id="history-manage", state="purchase-detail",
        clone_url=f"{base_url}/home/purchases", action="click", selector=newest_row,
        form_action="/api/purchase/{order_no}",
        visible_text_proof="← All purchases",
        raw_markup_proof="<h2>Keys</h2>",
        **holder,
    )

    # -- login-logout (account menu + sign out) ---------------------------
    goto(page, base_url, "/")
    menu_trigger = ".js-hb-account-menu .js-user-dropdown-container-2021"
    page.wait_for_selector(menu_trigger, timeout=SETTLE_TIMEOUT_MS)
    click(page, menu_trigger)
    wait_for_visible(page, "Logout")
    ledger.add(
        page, journey_id="login-logout", state="nav-dropdown-open",
        clone_url=f"{base_url}/", action="click", selector=menu_trigger,
        form_action=None,
        visible_text_proof="Logout",
        raw_markup_proof='class="navbar-item-dropdown-item js-navbar-logout"',
        **holder,
    )

    logout_control = ".js-hb-account-menu .js-navbar-logout"
    click(page, logout_control)
    page.wait_for_function(
        "() => { const a = document.querySelector('a.js-account-login');"
        " return a && getComputedStyle(a).display !== 'none'; }",
        timeout=SETTLE_TIMEOUT_MS,
    )
    ledger.add(
        page, journey_id="login-logout", state="loaded", clone_url=f"{base_url}/",
        action="click", selector=logout_control, form_action="/api/account/logout",
        visible_text_proof="Log In",
        raw_markup_proof="js-account-login logged-out desktop button-title navbar-login",
        **holder,
    )


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
def run_walk(base_url: str, admin_token: str) -> Ledger:
    ledger = Ledger()
    admin_reset(base_url, admin_token)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                visitor_ctx = browser.new_context(viewport=VIEWPORT)
                try:
                    walk_visitor(visitor_ctx.new_page(), base_url, ledger)
                finally:
                    visitor_ctx.close()
                holder_ctx = browser.new_context(viewport=VIEWPORT)
                try:
                    walk_account_holder(holder_ctx.new_page(), base_url, ledger)
                finally:
                    holder_ctx.close()
            finally:
                browser.close()
    finally:
        admin_reset(base_url, admin_token)
    return ledger


def build_document(base_url: str, ledger: Ledger) -> dict[str, Any]:
    return {
        "schema_version": LEDGER_SCHEMA,
        "site_id": SITE_ID,
        "authority": "diagnostic-only",
        "clone_base_url": base_url,
        "generated_by": "tools/walk_interaction_ledger.py",
        "walk": {
            "browser": "chromium (playwright, headless)",
            "viewport": f"{VIEWPORT['width']}x{VIEWPORT['height']}",
            "selector_provenance": "walk",
            "clone_url_semantics": (
                "URL where the control was activated; for action=state the URL "
                "of the observed document"
            ),
            "visible_text_semantics": (
                "textContent of elements that are not display:none / "
                "visibility:hidden, whitespace collapsed (not CSS "
                "text-transform-ed)"
            ),
            "raw_markup_semantics": (
                "exact substring of the served document markup with "
                "script/style bodies removed"
            ),
            "reset_endpoint": "POST /__admin/reset (start and end of walk)",
        },
        "entries": ledger.entries,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--admin-token", default="local-dev-admin")
    args = parser.parse_args(argv)

    base_url = args.base_url.rstrip("/")
    try:
        ledger = run_walk(base_url, args.admin_token)
    except WalkError as exc:
        print(f"walk failed: {exc}", file=sys.stderr)
        return 1

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(build_document(base_url, ledger), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    counts: dict[str, int] = {}
    for entry in ledger.entries:
        counts[entry["journey_id"]] = counts.get(entry["journey_id"], 0) + 1
    print(f"entries: {len(ledger.entries)} -> {output}")
    for journey in sorted(counts):
        print(f"  {journey:26s} {counts[journey]}")
    missing = sorted(JOURNEY_IDS - set(counts))
    print(f"journeys without an entry: {missing if missing else 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
