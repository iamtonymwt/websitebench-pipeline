"""Record which selectors exist in the *rendered* DOM, per page family.

Harbor observations are Playwright locators evaluated against a live page, and a
selector that matches nothing records empty from the reference and accepts empty
from the candidate -- so the case passes for everybody and tests nothing. On an
earlier site `#searchTextInput` was present in every page's served HTML and
absent from every rendered one, because the framework replaced the element.

So selectors are not read from markup. They are counted in the rendered page,
with their cardinality, because Playwright's locators are strict: an observation
that reads a single value must match exactly one element, while a count or list
observation wants many.

    python3 tools/dump_rendered_selectors.py --base-url http://127.0.0.1:8412 \
        --report scope/rendered-selectors.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from browser_session import attach  # noqa: E402

PROBE = r"""() => {
  const uuidish = /^[0-9a-f]{8}-[0-9a-f]{4}-/i;
  const count = (sel) => { try { return document.querySelectorAll(sel).length; } catch (e) { return -1; } };

  const ids = {};
  for (const el of document.querySelectorAll('[id]')) {
    const id = el.id;
    if (!id || uuidish.test(id)) continue;
    ids[id] = (ids[id] || 0) + 1;
  }
  const dataAt = {};
  for (const el of document.querySelectorAll('[data-at-id],[data-testid],[data-role]')) {
    const v = el.getAttribute('data-at-id') || el.getAttribute('data-testid')
              || el.getAttribute('data-role');
    if (v) dataAt[v] = (dataAt[v] || 0) + 1;
  }
  const classes = {};
  for (const el of document.querySelectorAll('[class]')) {
    for (const c of el.classList) {
      if (c.length > 2) classes[c] = (classes[c] || 0) + 1;
    }
  }

  // Candidate observation targets: things a case would plausibly assert on.
  const probes = {
    'h1': count('h1'),
    'title_text': document.title.length,
    'product_links': count('a[href*="p_id="]'),
    'add_to_cart_form': count('form[action="/cart"]'),
    'add_to_cart_button': count('#addCart'),
    'qty_input': count('#add-to-cart-qty'),
    'search_input': count('#keyword'),
    'search_form': count('form[action="/search/index"]'),
    'cart_table_rows': count('.wb-table tbody tr'),
    'cart_total': count('[data-cart-total]'),
    'checkout_total': count('[data-checkout-total]'),
    'order_reference': count('[data-order-reference]'),
    'order_total': count('[data-order-total]'),
    'minicart_count': count('[data-cart-count]'),
    'breadcrumb': count('.breadcrumb, #breadcrumb, [class*="breadcrumb"]'),
    'hawk_list_rows': count('table.hawk-list-table tr'),
    'item_price': count('[class*="price"]'),
  };

  const top = (obj, n) => Object.entries(obj).sort((a, b) => b[1] - a[1]).slice(0, n);
  return {
    url: location.pathname + location.search,
    title: document.title.slice(0, 90),
    nodes: document.querySelectorAll('*').length,
    probes,
    unique_ids: Object.entries(ids).filter(([, n]) => n === 1).map(([k]) => k).slice(0, 120),
    duplicated_ids: top(Object.fromEntries(Object.entries(ids).filter(([, n]) => n > 1)), 30),
    data_attributes: top(dataAt, 40),
    common_classes: top(classes, 40),
  };
}"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--settle-ms", type=int, default=4000)
    args = ap.parse_args()

    site_dir = pathlib.Path(__file__).resolve().parent.parent
    catalogue = json.loads((site_dir / "data" / "catalogue.json").read_text(encoding="utf-8"))
    a_product = catalogue["products"][0]["url_path"]
    a_category = next(c["path"] for c in catalogue["categories"]
                      if c.get("kind") == "taxonomy")
    a_shop = next((c["path"] for c in catalogue["categories"]
                   if c.get("kind") == "shop-collection"), "/p/shop")

    pages = {
        "home": "/",
        "category": a_category,
        "shop-collection": a_shop,
        "product": a_product,
        "search": "/search/index?keyword=hdmi+cable",
        "search-empty": "/search/index?keyword=zzzqqqnope",
        "cart-empty": "/cart",
        "checkout-empty": "/checkout",
        "not-found": "/definitely-not-a-real-route-websitebench",
        "absent-product": "/product?p_id=99999999",
    }

    base = args.base_url.rstrip("/")
    out: dict[str, dict] = {}
    with attach(warm=False, page_index=0) as (browser, _shared, _p):
        context = browser.new_context(viewport={"width": 1440, "height": 900},
                                      locale="en-US", timezone_id="UTC",
                                      service_workers="block")
        page = context.new_page()
        # The absent-product page navigates itself away. The source does the
        # same thing -- its "Products no longer Available" page carries a
        # setTimeout that sets location.href = "/" -- so this is faithful, not a
        # defect. But it means anything measured after a settle on that page is
        # measuring the *home page*: the first dump reported node counts and
        # selector cardinalities for /product?p_id=99999999 that were identical
        # to home's, down to the character count of the title.
        #
        # Any Harbor case on this page has to observe before the redirect fires,
        # and the two-run agreement check would not catch getting it wrong:
        # both runs redirect, so both would agree on the wrong page.
        SELF_NAVIGATING = {"absent-product"}
        for family, path in pages.items():
            page.goto(base + path, wait_until="domcontentloaded", timeout=90_000)
            if family not in SELF_NAVIGATING:
                page.wait_for_timeout(args.settle_ms)
            out[family] = page.evaluate(PROBE)
            out[family]["measured_before_settle"] = family in SELF_NAVIGATING
            probes = out[family]["probes"]
            interesting = {k: v for k, v in probes.items() if v not in (0, -1)}
            print(f"{family:16s} nodes={out[family]['nodes']:5d}  "
                  f"{json.dumps(interesting)[:110]}")

        # The cart with something in it: an empty cart shows none of the
        # controls a cart case needs to observe.
        pid = catalogue["products"][0]["p_id"]
        page.goto(base + f"/product?p_id={pid}", wait_until="domcontentloaded",
                  timeout=90_000)
        page.evaluate("""async (pid) => {
            const body = new URLSearchParams({p_id: pid, qty: '2'});
            await fetch('/cart', {method: 'POST', body});
        }""", pid)
        page.goto(base + "/cart", wait_until="domcontentloaded", timeout=90_000)
        page.wait_for_timeout(args.settle_ms)
        out["cart-populated"] = page.evaluate(PROBE)
        print(f"{'cart-populated':16s} nodes={out['cart-populated']['nodes']:5d}  "
              f"{json.dumps({k: v for k, v in out['cart-populated']['probes'].items() if v not in (0, -1)})[:110]}")
        context.close()

    report = {"schema_version": "monoprice.rendered-selectors.v1",
              "base_url": base, "pages": out,
              "note": ("Counts are from the rendered DOM. Playwright locators are "
                       "strict: a single-value observation needs exactly one "
                       "match. Anything listed under duplicated_ids cannot be "
                       "used without an nth.")}
    pathlib.Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.report).write_text(json.dumps(report, indent=2) + "\n",
                                         encoding="utf-8")
    print(f"\nwrote {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
