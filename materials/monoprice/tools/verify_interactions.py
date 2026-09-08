"""Drive every control on the clone once, in one browser context.

The gates in this run measure pages, not controls, and that gap has now cost
the same thing twice. Add to Cart was dead for a day while 39 tests passed,
because every test POSTs to `/cart` directly -- testing the endpoint and never
the button. The facet sidebar was reported by a person as "the box on the left
does not work either" while its markup was complete, correctly styled, and
holding real hrefs inside a container nothing could open.

So this drives the controls: the search box, a facet group, Add to Cart, the
variant chooser, and checkout. Each check states what a person would see if it
failed, because "assert 200" is what let the dead button through.

It uses ONE context and ONE page for everything and never navigates more than
it must -- opening and closing pages per assertion is its own problem on this
machine.

    python3 tools/verify_interactions.py --port 8412 \
        --report scope/interaction-check.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from browser_session import attach  # noqa: E402

VIEWPORT = {"width": 1440, "height": 900}


def check_facet_toggle(page, base: str) -> dict:
    """A collapsed facet group must open when its heading is clicked."""
    page.goto(f"{base}/search/index?keyword=hdmi+cable", wait_until="load",
              timeout=120000)
    page.wait_for_timeout(2500)
    # Only a heading a person can see counts. The search page renders the facet
    # sidebar TWICE -- once for desktop and once inside a hidden mobile filter
    # panel -- so there are 78 headings, not 39, and the first collapsed one is
    # in the panel nobody can click. Testing that one reported the toggle broken
    # while it worked: a check that drives an invisible control tests nothing,
    # which is the same mistake as testing an endpoint instead of a button.
    before = page.evaluate("""() => {
      const heads = [...document.querySelectorAll('.hawk-groupHeading')];
      const visible = heads.filter(h => h.getBoundingClientRect().height > 0);
      const collapsed = visible.filter(h => h.classList.contains('plus'));
      return {headings: heads.length, visibleHeadings: visible.length,
              collapsed: collapsed.length,
              label: collapsed.length ? collapsed[0].textContent.trim().slice(0, 30) : null};
    }""")
    if not before["collapsed"]:
        return {"name": "facet_toggle", "ok": False,
                "detail": "no collapsed facet group to click",
                "before": before}
    # The site's own handler animates with jQuery `slideDown('fast')`, so the
    # panel is display:block with a height of a few pixels for ~200ms after the
    # click. Measuring immediately reports 0 visible links on a panel that is
    # opening correctly -- and reading `display` mid-animation is exactly what
    # made a redundant shim look necessary.
    page.evaluate("""() => {
      const h = [...document.querySelectorAll('.hawk-groupHeading')]
        .filter(x => x.getBoundingClientRect().height > 0)
        .find(x => x.classList.contains('plus'));
      window.__wbFacetHeading = h;
      window.__wbFacetBefore = (function () {
        let c = h.nextElementSibling;
        while (c && String(c.className).indexOf('hawk-navGroupContent') === -1) c = c.nextElementSibling;
        return c ? getComputedStyle(c).display : null;
      })();
      h.click();
    }""")
    page.wait_for_timeout(900)
    opened = page.evaluate("""() => {
      const h = window.__wbFacetHeading;
      let c = h.nextElementSibling;
      while (c && String(c.className).indexOf('hawk-navGroupContent') === -1) {
        c = c.nextElementSibling;
      }
      const was = window.__wbFacetBefore;
      const now = c ? getComputedStyle(c).display : null;
      const links = c ? c.querySelectorAll('a[href]').length : 0;
      const visibleLinks = c ? [...c.querySelectorAll('a[href]')]
        .filter(a => a.getBoundingClientRect().height > 0).length : 0;
      return {was, now, links, visibleLinks,
              heading_class: h.className,
              href: c && c.querySelector('a[href]') ? c.querySelector('a[href]').getAttribute('href') : null};
    }""")
    ok = (opened["was"] == "none" and opened["now"] != "none"
          and opened["visibleLinks"] > 0)
    return {"name": "facet_toggle", "ok": ok,
            "detail": (f"clicked '{before['label']}': display {opened['was']} -> "
                       f"{opened['now']}, {opened['visibleLinks']} of "
                       f"{opened['links']} filter links now visible"),
            "filter_href": opened["href"], "before": before,
            "after": opened}


def check_facet_link_filters(page, base: str, href: str | None) -> dict:
    """Following a facet link must narrow the result set."""
    if not href:
        return {"name": "facet_link_filters", "ok": False,
                "detail": "no facet link to follow"}
    page.goto(f"{base}/search/index?keyword=hdmi+cable", wait_until="load",
              timeout=120000)
    page.wait_for_timeout(2000)
    wide = page.evaluate(
        "() => document.querySelectorAll('a[href*=\"p_id=\"]').length")
    page.goto(base + href if href.startswith("/") else href,
              wait_until="load", timeout=120000)
    page.wait_for_timeout(2000)
    narrow = page.evaluate("""() => ({
      tiles: document.querySelectorAll('a[href*="p_id="]').length,
      visible: [...document.querySelectorAll('a[href*="p_id="]')]
        .filter(a => a.getBoundingClientRect().height > 0).length,
      title: document.title.slice(0, 60)
    })""")
    # Strictly narrower, and not empty. `<=` was the original assertion and it
    # passed while the handler ignored every facet parameter and returned the
    # identical 316 results under a filtered heading -- equality satisfies
    # "narrower or equal", so the check could not tell filtering from no
    # filtering at all. A filter that returns nothing is equally broken, hence
    # both bounds.
    ok = 0 < narrow["visible"] and narrow["tiles"] < wide
    return {"name": "facet_link_filters", "ok": ok,
            "detail": (f"unfiltered {wide} tiles -> filtered {narrow['tiles']} "
                       f"({narrow['visible']} visible)"),
            "after": narrow}


def check_search_box(page, base: str) -> dict:
    """Typing a term and pressing Enter must reach the results page."""
    page.goto(base + "/", wait_until="load", timeout=120000)
    page.wait_for_timeout(2000)
    typed = page.evaluate("""() => {
      const f = document.querySelector('input[name="keyword"], #search-field, input[type="search"]');
      return f ? {found: true, name: f.getAttribute('name'), id: f.id} : {found: false};
    }""")
    if not typed.get("found"):
        return {"name": "search_box", "ok": False,
                "detail": "no search field on the home page"}
    selector = ('input[name="keyword"]' if typed.get("name") == "keyword"
                else "#" + typed["id"] if typed.get("id")
                else 'input[type="search"]')
    page.fill(selector, "hdmi cable")
    page.press(selector, "Enter")
    page.wait_for_timeout(3000)
    url = page.url
    tiles = page.evaluate("""() => [...document.querySelectorAll('a[href*="p_id="]')]
      .filter(a => a.getBoundingClientRect().height > 0).length""")
    ok = "search" in url.lower() and tiles > 0
    return {"name": "search_box", "ok": ok,
            "detail": f"Enter went to {url[len(base):][:60]} with {tiles} visible tiles"}


def check_add_to_cart(page, base: str, p_id: str) -> dict:
    """The button, not the endpoint.

    This is the check that was missing when Add to Cart was dead: five stacked
    causes, all downstream of the click, and every unit test green because they
    all POST to /cart directly.
    """
    page.context.clear_cookies()
    page.goto(f"{base}/product?p_id={p_id}", wait_until="load", timeout=120000)
    page.wait_for_timeout(3000)
    found = page.evaluate("""() => {
      const b = [...document.querySelectorAll('button, a, input[type="submit"]')]
        .filter(e => /add to cart/i.test(e.textContent || e.value || ''))
        .filter(e => e.getBoundingClientRect().height > 0);
      return {count: b.length, text: b.length ? (b[0].textContent || b[0].value).trim().slice(0, 30) : null};
    }""")
    if not found["count"]:
        return {"name": "add_to_cart", "ok": False,
                "detail": "no visible Add to Cart control on the product page"}
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).split("\n")[0][:110]))
    page.evaluate("""() => {
      const b = [...document.querySelectorAll('button, a, input[type="submit"]')]
        .filter(e => /add to cart/i.test(e.textContent || e.value || ''))
        .filter(e => e.getBoundingClientRect().height > 0);
      b[0].click();
    }""")
    page.wait_for_timeout(3500)
    page.goto(base + "/cart", wait_until="load", timeout=120000)
    page.wait_for_timeout(1500)
    cart = page.evaluate("""() => ({
      text: (document.body.innerText || '').slice(0, 400),
      rows: document.querySelectorAll('form[action="/cart/remove"]').length
    })""")
    ok = cart["rows"] > 0
    return {"name": "add_to_cart", "ok": ok,
            "detail": (f"clicked '{found['text']}'; cart holds {cart['rows']} "
                       f"line(s)"),
            "page_errors": errors[:4]}


def check_variant_switch(page, base: str, variant_map: dict) -> dict:
    """Clicking a variant value must change the displayed product."""
    pick = None
    for pid, options in variant_map.items():
        for value, target in options.items():
            pick = (pid, value, target)
            break
        if pick:
            break
    if pick is None:
        return {"name": "variant_switch", "ok": False,
                "detail": "variant map is empty"}
    pid, value, target = pick
    page.goto(f"{base}/product?p_id={pid}", wait_until="load", timeout=120000)
    page.wait_for_timeout(2500)
    got = page.evaluate("""async ([value, pid]) => {
      const opt = [...document.querySelectorAll('[data-mp-attrval]')]
        .find(e => e.getAttribute('data-mp-attrval') === value);
      if (!opt) return {found: false};
      const r = await fetch('/product/selectpid', {
        method: 'POST',
        headers: {'Content-Type': 'application/json; charset=utf-8'},
        body: JSON.stringify({vals: [value], PID: pid, changedVal: value})
      });
      const data = await r.json();
      return {found: true, status: r.status, p_id: data.p_id,
              resolved: data.resolved,
              info: (data.infoPartialView || '').length,
              image: (data.imagePartialView || '').length,
              desc: (data.descPartialView || '').length};
    }""", [value, pid])
    if not got.get("found"):
        return {"name": "variant_switch", "ok": False,
                "detail": f"no clickable option '{value}' on product {pid}"}
    ok = (got["status"] == 200 and got["p_id"] == target and got["resolved"]
          and got["info"] > 200 and got["desc"] > 0)
    return {"name": "variant_switch", "ok": ok,
            "detail": (f"selecting '{value}' on {pid} resolved to {got['p_id']} "
                       f"(expected {target}); info panel {got['info']} bytes, "
                       f"desc {got['desc']}")}


def check_checkout(page, base: str, p_id: str) -> dict:
    """Add an item, check out, and land on a real order."""
    page.context.clear_cookies()
    page.goto(f"{base}/product?p_id={p_id}", wait_until="load", timeout=120000)
    page.wait_for_timeout(2500)
    page.evaluate("""async (pid) => {
      await fetch('/cart', {method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: new URLSearchParams({p_id: pid, quantity: '1'}).toString()});
    }""", p_id)
    page.goto(base + "/checkout", wait_until="load", timeout=120000)
    page.wait_for_timeout(1500)
    form = page.evaluate("""() => ({
      form: document.querySelectorAll('form[action="/checkout"]').length,
      scenario: document.querySelectorAll('form[action="/checkout"] select[name="scenario"]').length,
      options: [...document.querySelectorAll('select[name="scenario"] option')]
        .map(o => o.value).slice(0, 6)
    })""")
    if not form["scenario"]:
        return {"name": "checkout", "ok": False,
                "detail": ("no scenario select inside the checkout form -- this "
                           "is what an empty cart looks like two steps later"),
                "form": form}
    approved = next((o for o in form["options"] if "approve" in o.lower()),
                    form["options"][0] if form["options"] else None)
    page.select_option('form[action="/checkout"] select[name="scenario"]', approved)
    page.click('form[action="/checkout"] button[type="submit"]')
    page.wait_for_timeout(3000)
    after = page.evaluate("""() => ({url: location.pathname,
      text: (document.body.innerText || '').slice(0, 300)})""")
    ok = "/order/" in after["url"]
    return {"name": "checkout", "ok": ok,
            "detail": f"scenario '{approved}' -> {after['url']}",
            "options": form["options"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--product", default="39165")
    args = ap.parse_args()

    base = f"http://127.0.0.1:{args.port}"
    vm_path = pathlib.Path("clone/static/variant-map.json")
    variant_map = (json.loads(vm_path.read_text(encoding="utf-8"))["products"]
                   if vm_path.exists() else {})

    results = []
    with attach(warm=False, page_index=0) as (browser, _shared, _page):
        ctx = browser.new_context(viewport=VIEWPORT, service_workers="block")
        page = ctx.new_page()
        try:
            facet = check_facet_toggle(page, base)
            results.append(facet)
            results.append(check_facet_link_filters(page, base,
                                                    facet.get("filter_href")))
            results.append(check_search_box(page, base))
            results.append(check_add_to_cart(page, base, args.product))
            results.append(check_variant_switch(page, base, variant_map))
            results.append(check_checkout(page, base, args.product))
        finally:
            ctx.close()

    failed = [r for r in results if not r["ok"]]
    report = {"schema_version": "monoprice.interaction-check.v1",
              "base_url": base, "checks": len(results),
              "failed": len(failed), "results": results}
    pathlib.Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.report).write_text(json.dumps(report, indent=2) + "\n",
                                         encoding="utf-8")
    for r in results:
        print(f"  {'PASS' if r['ok'] else 'FAIL'}  {r['name']:22s} {r['detail']}")
        for e in r.get("page_errors") or []:
            print(f"          page error: {e}")
    print(f"\n{len(results) - len(failed)} of {len(results)} controls work")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
