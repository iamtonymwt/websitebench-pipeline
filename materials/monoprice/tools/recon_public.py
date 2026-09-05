"""Read-only public reconnaissance for the monoprice TASK_BRIEF.

Phase 2 is GET/HEAD only: no login, no form submission, no source-site state
change. This walks a handful of public pages in the one long-lived browser and
writes structured observations, so the brief's fields each carry an evidence URL
instead of an inference.

    python3 tools/recon_public.py --report scope/recon-public.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from browser_session import attach  # noqa: E402

ORIGIN = "https://www.monoprice.com"

# Page families to sample. One representative per family; capture corrects this
# later. `/cart` and `/Checkout` are under a robots Disallow rule and are
# deliberately absent -- they are never requested, here or anywhere else.
SAMPLES = [
    ("home", "/"),
    ("category-l3", "/category/cables/hdmi-cables/hdmi-cables"),
    ("category-l2", "/category/cables/hdmi-cables"),
    ("category-hub", "/category/pages/1"),
    ("product", "/product?p_id=44627"),
    ("search", "/search/index?keyword=hdmi+cable"),
    ("newsroom", "/home/newsroom"),
    ("static-page", "/pages/newproducts"),
    ("help", "/help"),
    ("about", "/about-us"),
    ("not-found", "/this-route-does-not-exist-websitebench"),
    ("product-absent", "/product?p_id=99999999"),
    ("category-absent", "/category/nope/nope/nope"),
]

OBSERVE = r"""() => {
  const meta = (sel, attr) => {
    const el = document.querySelector(sel);
    return el ? (el.getAttribute(attr) || '').slice(0, 200) : null;
  };
  const abs = (h) => { try { return new URL(h, location.href).href; } catch (e) { return null; } };

  const linkHosts = {};
  const routeShapes = {};
  for (const a of document.querySelectorAll('a[href]')) {
    const raw = a.getAttribute('href') || '';
    if (/^(mailto:|tel:|javascript:|#)/i.test(raw)) continue;
    const u = abs(raw);
    if (!u) continue;
    const p = new URL(u);
    linkHosts[p.host] = (linkHosts[p.host] || 0) + 1;
    if (p.host.endsWith('monoprice.com')) {
      const seg = p.pathname.split('/').filter(Boolean)[0] || '(root)';
      routeShapes[seg] = (routeShapes[seg] || 0) + 1;
    }
  }

  const imgHosts = {};
  for (const i of document.images) {
    const u = abs(i.currentSrc || i.src || i.getAttribute('data-src') || '');
    if (!u) continue;
    imgHosts[new URL(u).host] = (imgHosts[new URL(u).host] || 0) + 1;
  }

  const forms = [...document.querySelectorAll('form')].map(f => ({
    action: f.getAttribute('action'),
    method: (f.getAttribute('method') || 'get').toLowerCase(),
    id: f.id || null,
    controls: [...f.querySelectorAll('input,select,textarea')]
      .map(c => c.getAttribute('name')).filter(Boolean).slice(0, 12),
  })).slice(0, 12);

  const jsonld = [...document.querySelectorAll('script[type="application/ld+json"]')]
    .map(s => { try { return JSON.parse(s.textContent); } catch (e) { return null; } })
    .filter(Boolean);

  const text = document.body ? document.body.innerText : '';

  return {
    title: document.title,
    lang: document.documentElement.getAttribute('lang'),
    og_site_name: meta('meta[property="og:site_name"]', 'content'),
    og_title: meta('meta[property="og:title"]', 'content'),
    description: meta('meta[name="description"]', 'content'),
    canonical: meta('link[rel="canonical"]', 'href'),
    viewport_meta: meta('meta[name="viewport"]', 'content'),
    nodes: document.querySelectorAll('*').length,
    scroll_height: document.body ? document.body.scrollHeight : 0,
    images: document.images.length,
    links: document.querySelectorAll('a[href]').length,
    text_chars: text.length,
    text_head: text.slice(0, 400),
    currency_samples: (text.match(/[$€£]\s?[0-9][0-9,]*\.?[0-9]{0,2}/g) || []).slice(0, 5),
    link_hosts: linkHosts,
    image_hosts: imgHosts,
    route_shapes: routeShapes,
    forms,
    jsonld_types: jsonld.map(o => Array.isArray(o) ? 'Array' : (o['@type'] || 'unknown')),
    jsonld_first: jsonld.length ? JSON.stringify(jsonld[0]).slice(0, 900) : null,
    stylesheets: [...document.querySelectorAll('link[rel=stylesheet]')]
      .map(l => l.getAttribute('href')).slice(0, 40),
    // Which ids survive into the rendered DOM. Harbor selectors must come from
    // here, not from the served markup.
    rendered_ids: [...document.querySelectorAll('[id]')].map(e => e.id)
      .filter(i => i && !/^[0-9a-f]{8}-[0-9a-f]{4}/.test(i)).slice(0, 120),
    data_testids: [...new Set([...document.querySelectorAll('[data-testid],[data-at-id]')]
      .map(e => e.getAttribute('data-testid') || e.getAttribute('data-at-id')))].slice(0, 60),
  };
}"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    pages: dict[str, dict] = {}
    with attach() as (_browser, _context, page):
        for family, path in SAMPLES:
            url = urllib.parse.urljoin(ORIGIN, path)
            entry: dict = {"family": family, "path": path, "url": url}
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=90_000)
                entry["http_status"] = resp.status if resp else None
                entry["final_url"] = page.url
                page.wait_for_timeout(2_500)
                entry["observed"] = page.evaluate(OBSERVE)
            except Exception as exc:  # noqa: BLE001 - a failed sample is a result
                entry["error"] = f"{exc.__class__.__name__}: {exc}"[:300]
            pages[family] = entry
            got = entry.get("observed", {})
            print(f"{family:18s} {entry.get('http_status')} "
                  f"nodes={got.get('nodes')} imgs={got.get('images')} "
                  f"links={got.get('links')} title={str(got.get('title'))[:48]!r}")

    # The soft-404 signature. This site answers unknown products and unknown
    # category paths with 200 and a full-looking page, so status code is not a
    # usable filter and capture needs a content rule instead.
    absent = pages.get("product-absent", {}).get("observed", {}) or {}
    absent_cat = pages.get("category-absent", {}).get("observed", {}) or {}
    soft_404 = {
        "product_absent_status": pages.get("product-absent", {}).get("http_status"),
        "product_absent_title": absent.get("title"),
        "category_absent_status": pages.get("category-absent", {}).get("http_status"),
        "category_absent_title": absent_cat.get("title"),
        "true_404_status": pages.get("not-found", {}).get("http_status"),
        "true_404_title": (pages.get("not-found", {}).get("observed") or {}).get("title"),
        "rule": ("An absent product answers 200 with the title "
                 "'Products no longer Available'; an absent category answers 200 "
                 "with a title built from the requested slug. Only an unknown "
                 "root path answers 404. Capture must classify by content."),
    }

    hosts: dict[str, int] = {}
    for entry in pages.values():
        for bucket in ("link_hosts", "image_hosts"):
            for host, n in ((entry.get("observed") or {}).get(bucket) or {}).items():
                hosts[host] = hosts.get(host, 0) + n

    report = {
        "schema_version": "monoprice.recon-public.v1",
        "origin": ORIGIN,
        "method": "GET-only, single long-lived browser, no login, no submissions",
        "pages": pages,
        "soft_404": soft_404,
        "observed_hosts": dict(sorted(hosts.items(), key=lambda kv: -kv[1])),
    }
    out = pathlib.Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
