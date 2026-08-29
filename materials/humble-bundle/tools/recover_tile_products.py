"""Recover every store product the frozen markup shows but the catalogue lacks.

The seed carries 75 products. The frozen pages link far more: the store listing
alone shows 125 distinct product slugs, and 83 of them answered 404 — every tile
visible, every price printed, every cover image local, and no catalogue row
behind any of them.

Extraction runs in a browser against the served clone, not over the markup with
a regular expression. A first version bounded each tile with a character window
between neighbouring product anchors and produced titles belonging to the tile
next door: `balatro` came out as "Manor Lords". A tile is a DOM subtree, and the
only reliable way to ask which title belongs to which link is to ask the DOM.

Nothing is invented. Title, current and full price, discount badge, delivery
platform, operating systems and cover image come from the tile. Genre,
developer, publisher, description and system requirements stay empty, because a
tile does not carry them and the detail pages were never visited.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys

from playwright.async_api import async_playwright

SITE = pathlib.Path(__file__).resolve().parents[1]
SEED = SITE / "clone" / "backend" / "seed_data.json"

ROUTES = ["/", "/store", "/store/search", "/store/c/action", "/bundles",
          "/games", "/books", "/software", "/membership",
          "/store/palworld", "/store/satisfactory",
          # Bundle pages carry their own product strips. Leaving them out left
          # two products linked from the 2K bundle page still answering 404.
          "/games/2k-megahits-2026-bundle", "/games/yes-chef-cooking-bundle",
          "/books/python-rust-and-data-oreilly-books"]

# Read every tile as a subtree. `closest` walks the real ancestor chain, so a
# tile can never pick up the neighbouring tile's title or price.
EXTRACT = r"""
() => {
  const OS = {windows: 'windows', osx: 'mac', linux: 'linux',
              android: 'android', switch: 'switch'};
  const money = (s) => {
    const m = /(?:CA|US|A)?\$\s*([\d,]+(?:\.\d{2})?)/.exec(s || '');
    return m ? Math.round(parseFloat(m[1].replace(/,/g, '')) * 100) : null;
  };
  const out = {};
  for (const a of document.querySelectorAll('a[href^="/store/"]')) {
    const parts = a.getAttribute('href').split('?')[0].split('/').filter(Boolean);
    if (parts.length !== 2) continue;
    const slug = parts[1];
    if (out[slug]) continue;
    const tile = a.closest('.entity, .entity-block-container, .entity-container,'
      + ' .full-tile-view, .js-entity, li') || a.parentElement;
    if (!tile) continue;

    const titleNode = tile.querySelector('.entity-title');
    const img = tile.querySelector('img.entity-image, img');
    const priceNodes = [...tile.querySelectorAll(
      '.price, .full-price, .entity-pricing .price-container *')];
    const amounts = [...new Set(priceNodes.map(n => money(n.textContent))
      .filter(v => v !== null))];
    const discount = tile.querySelector('.discount-amount, .js-discount-gem');
    const dm = discount ? /(\d{1,2})%/.exec(discount.textContent) : null;

    /* A tile inside a numbered chart carries its rank in the title node —
     * "11. Carnival Hunt". The rank is the tile's position in that list, not
     * part of the product's name, and it would be baked into the catalogue. */
    let title = titleNode ? titleNode.textContent.trim()
      : (img && img.getAttribute('alt') || '').trim();
    title = title.replace(/^\d{1,2}\.\s+/, '');
    if (!title || !amounts.length) continue;

    out[slug] = {
      title: title.slice(0, 120),
      amounts,
      discount: dm ? parseInt(dm[1], 10) : 0,
      image: img ? (img.getAttribute('src') || img.getAttribute('data-src')
        || img.getAttribute('data-lazy')) : null,
      platforms: [...new Set([...tile.querySelectorAll('.operating-system')]
        .map(n => (/hb-([a-z0-9]+)/.exec(n.className) || [])[1])
        .filter(Boolean).map(k => OS[k]).filter(Boolean))],
      drm: [...new Set([...tile.querySelectorAll('.platform')]
        .map(n => (/hb-([a-z0-9]+)/.exec(n.className) || [])[1]).filter(Boolean))],
    };
  }
  return out;
}
"""


async def collect(base: str) -> dict[str, dict]:
    found: dict[str, dict] = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await (await browser.new_context(
            viewport={"width": 1440, "height": 1400})).new_page()
        for route in ROUTES:
            try:
                resp = await page.goto(base + route, wait_until="load", timeout=40000)
            except Exception:
                continue
            if not resp or resp.status >= 400:
                continue
            await page.wait_for_timeout(1800)
            for slug, info in (await page.evaluate(EXTRACT)).items():
                found.setdefault(slug, {**info, "seen_on": route})
        await browser.close()
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8321")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = json.loads(SEED.read_text(encoding="utf-8"))
    known = {p["slug"] for p in data["products"]}
    found = asyncio.run(collect(args.base))
    missing = {s: i for s, i in found.items() if s not in known}

    added = []
    for slug, info in sorted(missing.items()):
        amounts = sorted(info["amounts"])
        current, full = amounts[0], amounts[-1]
        added.append({
            "slug": slug,
            "machine_name": slug.replace("-", "_") + "_storefront",
            "human_name": info["title"],
            "current_price_minor": current,
            "full_price_minor": full,
            "discount_pct": info["discount"] if full != current else 0,
            "platforms": info["platforms"],
            "drm": info["drm"],
            "delivery_methods": info["drm"],
            "genres": [], "developers": [], "publishers": [],
            "rating_for_current_region": None,
            "description": "",
            "system_requirements": {},
            "media": ({"standard_carousel_image": {"local": info["image"],
                                                   "source_url": None},
                       "large_capsule": {"local": info["image"],
                                         "source_url": None}}
                      if info["image"] else {}),
            "search_orders": {},
            "capture_note": (
                f"Recovered from its tile on {info['seen_on']}: title, price, "
                "discount, delivery and cover image are captured there. The "
                "detail page was never visited, so genre, developer, publisher, "
                "description and system requirements are empty rather than "
                "guessed."),
        })

    print(f"catalogue {len(known)} · tiles found {len(found)} · missing {len(added)}")
    for a in added[:10]:
        print(f"  + {a['slug'][:42]:<44} {a['human_name'][:34]:<36} "
              f"{a['current_price_minor'] / 100:>8.2f}")
    if len(added) > 10:
        print(f"  … {len(added) - 10} more")
    if args.dry_run:
        return 0
    data["products"].extend(added)
    SEED.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    print(f"\nseed_data.json: {len(known)} -> {len(data['products'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
