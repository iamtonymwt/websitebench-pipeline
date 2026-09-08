"""Compare what a person actually SEES on the clone against the source.

Every other gate in this run measures presence: are the references closed, does
anything leave loopback, does any same-origin request fail, do the tests pass.
All of them were green while four page families were visibly broken, because
each defect left the markup complete and only stopped it from rendering:

  * category and search held 165 and 316 product links and displayed **none**
    -- both result containers were `display:none`, waiting for a third-party
    script that had been stripped;
  * the Webflow pages lost their main stylesheet to a Subresource Integrity
    hash that no longer matched after we rewrote the file's own URLs;
  * cart and checkout rendered a 19,844px header with the megamenu fully
    expanded, because the page shell they are built from still carried
    `type="/text/css"` from a freezer bug fixed weeks earlier.

None of those produce a failed request, a console error we listened for, or a
missing file. They produce a page that looks wrong. So this tool measures the
things that look wrong, and -- the part that makes it work -- measures them on
the **source page too**, because a single page's numbers look perfectly
plausible in isolation. It was only cart's 2,418 CSS rules sitting next to the
product page's 5,684 that revealed anything at all.

Reading the source here is navigation only. No control that mutates source
state is touched; see `scope/claims.jsonl` cl-015 for why that line matters.

    python3 tools/audit_visible.py --port 8412 \
        --report scope/visible-audit.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from browser_session import attach  # noqa: E402

VIEWPORT = {"width": 1440, "height": 900}

# One representative route per family, with the source URL it was cloned from.
# A family missing from this list is a family nobody is looking at.
FAMILIES = [
    ("home", "/", "https://www.monoprice.com/"),
    ("category", "/category/cables/hdmi-cables/hdmi-cables",
     "https://www.monoprice.com/category/cables/hdmi-cables/hdmi-cables"),
    ("search", "/search/index?keyword=hdmi+cable",
     "https://www.monoprice.com/search/index?keyword=hdmi+cable"),
    ("product", "/product?p_id=39165",
     "https://www.monoprice.com/product?p_id=39165"),
    ("shop", "/p/shop/usb-c-to-usb-3-0",
     "https://www.monoprice.com/p/shop/usb-c-to-usb-3-0"),
    ("static", "/about-us", "https://www.monoprice.com/about-us"),
]

# Pages this project builds itself. There is no source page to compare against,
# so they are measured against the shell they are supposed to reuse: whatever
# `static` scores is what the chrome around them should score.
SELF_BUILT = [("cart", "/cart"), ("checkout", "/checkout")]

MEASURE = """() => {
  const vis = (e) => {
    const r = e.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    const cs = getComputedStyle(e);
    return cs.visibility !== 'hidden' && cs.display !== 'none' && cs.opacity !== '0';
  };
  let rules = 0, sheetsBlocked = 0;
  for (const s of document.styleSheets) {
    try { rules += s.cssRules.length } catch (e) { sheetsBlocked++ }
  }
  // A <link rel=stylesheet> with no .sheet was never applied: refused MIME
  // type, failed SRI, or a load error. This is the single most diagnostic
  // number in the whole tool and it costs one line.
  const links = [...document.querySelectorAll('link[rel~="stylesheet" i]')];
  const unapplied = links.filter(l => !l.sheet)
                         .map(l => (l.getAttribute('href') || '').split('/').pop());
  // Which sheets are in force, by name, so a rule-count gap can be attributed
  // to a specific file instead of being reported as a number that is simply
  // lower than the source's. A stripped third-party stylesheet is a legitimate
  // reason for a lower count; a missing first-party one is not, and the ratio
  // alone cannot tell them apart.
  const applied = [];
  for (const s of document.styleSheets) {
    let n = 0; try { n = s.cssRules.length } catch (e) { n = -1 }
    applied.push({name: s.href ? s.href.split('/').pop().split('?')[0] : 'inline',
                  rules: n});
  }
  const tiles = [...document.querySelectorAll('a[href*="p_id="]')];
  const imgs = [...document.images];
  return {
    height: document.documentElement.scrollHeight,
    text: (document.body.innerText || '').trim().length,
    rules, sheets: document.styleSheets.length, sheetsBlocked,
    stylesheetLinks: links.length,
    unappliedStylesheets: unapplied,
    appliedStylesheets: applied,
    tiles: tiles.length,
    tilesVisible: tiles.filter(vis).length,
    images: imgs.length,
    imagesVisible: imgs.filter(vis).length,
    imagesBrokenVisible: imgs.filter(i => i.complete && i.naturalWidth === 0 && vis(i)).length,
    tallest: [...document.querySelectorAll('header, nav, main, footer')]
      .map(e => ({tag: e.tagName, h: Math.round(e.getBoundingClientRect().height)}))
      .sort((a, b) => b.h - a.h).slice(0, 3),
  };
}"""


def measure(page, url: str, settle_ms: int) -> dict:
    page.goto(url, wait_until="load", timeout=120000)
    page.wait_for_timeout(settle_ms)
    return page.evaluate(MEASURE)


def compare(family: str, clone: dict, source: dict | None) -> list[str]:
    """Defects, phrased as what a person would notice."""
    out = []

    if clone["unappliedStylesheets"]:
        out.append(
            f"{len(clone['unappliedStylesheets'])} of {clone['stylesheetLinks']} "
            f"stylesheets never applied: "
            f"{', '.join(clone['unappliedStylesheets'][:6])}")
    if clone["imagesBrokenVisible"]:
        out.append(f"{clone['imagesBrokenVisible']} visible broken images")
    if clone["tiles"] and clone["tilesVisible"] == 0:
        out.append(f"{clone['tiles']} product links present, NONE visible "
                   "-- content rendered but hidden")
    if clone["text"] < 200:
        out.append(f"only {clone['text']} characters of visible text")

    if source is None:
        return out

    # Name the sheets the source has and the clone does not, before reporting a
    # rule-count ratio. "4,357 rules against 5,863" is a symptom; "hawksearch.css
    # is not here" is the cause.
    src_names = {s["name"] for s in source.get("appliedStylesheets", [])}
    clone_names = {s["name"] for s in clone.get("appliedStylesheets", [])}
    only_source = sorted(n for n in src_names - clone_names if n != "inline")
    if only_source:
        by_name = {s["name"]: s["rules"] for s in source["appliedStylesheets"]}
        detail = ", ".join(f"{n} ({by_name.get(n, '?')} rules)"
                           for n in only_source[:5])
        out.append(f"stylesheets in force on the source but not here: {detail}")

    # Ratios, not absolutes. The source is the only definition of "right" we
    # have, and a threshold picked by hand is a threshold that passes whatever
    # the clone happens to do.
    for key, low, high, label in (
        ("rules", 0.75, 1.40, "CSS rules in force"),
        ("text", 0.60, 1.80, "visible text"),
        ("height", 0.55, 1.60, "page height"),
    ):
        s, c = source[key], clone[key]
        if not s:
            continue
        ratio = c / s
        if ratio < low or ratio > high:
            out.append(f"{label} {c} vs source {s} (x{ratio:.2f})")

    if source["tilesVisible"] and not clone["tilesVisible"]:
        out.append(f"source shows {source['tilesVisible']} product tiles, "
                   "clone shows 0")
    elif source["tilesVisible"]:
        ratio = clone["tilesVisible"] / source["tilesVisible"]
        if ratio < 0.6:
            out.append(f"{clone['tilesVisible']} visible tiles vs source "
                       f"{source['tilesVisible']}")
    if clone["imagesBrokenVisible"] > source["imagesBrokenVisible"]:
        out.append(f"visible broken images {clone['imagesBrokenVisible']} vs "
                   f"source {source['imagesBrokenVisible']}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--settle-ms", type=int, default=3500)
    ap.add_argument("--skip-source", action="store_true",
                    help="clone-only pass; ratio checks are skipped and the "
                         "report records that they did not run")
    args = ap.parse_args()

    base = f"http://127.0.0.1:{args.port}"
    rows: list[dict] = []

    with attach(warm=False, page_index=0) as (browser, warm_ctx, _page):
        # The clone is measured in a context that has never seen the source, so
        # nothing it renders can be borrowed from a cookie or a cached asset.
        # Skipping this is how an earlier audit recorded 60 phantom requests.
        clone_ctx = browser.new_context(viewport=VIEWPORT, service_workers="block")
        clone_page = clone_ctx.new_page()
        source_page = None
        if not args.skip_source:
            # The source needs the warmed context: its Cloudflare clearance
            # lives there and a fresh context is answered with a challenge.
            source_page = warm_ctx.new_page()
            source_page.set_viewport_size(VIEWPORT)

        try:
            for family, path, source_url in FAMILIES:
                clone = measure(clone_page, base + path, args.settle_ms)
                source = None
                if source_page is not None:
                    try:
                        source = measure(source_page, source_url, args.settle_ms)
                    except Exception as exc:  # noqa: BLE001
                        source = None
                        print(f"  {family}: source unreadable ({type(exc).__name__})")
                rows.append({"family": family, "route": path,
                             "source_url": source_url,
                             "clone": clone, "source": source,
                             "defects": compare(family, clone, source)})

            # Self-built pages, compared to the static family's chrome.
            static = next((r for r in rows if r["family"] == "static"), None)
            for family, path in SELF_BUILT:
                clone = measure(clone_page, base + path, args.settle_ms)
                baseline = static["clone"] if static else None
                rows.append({"family": family, "route": path,
                             "source_url": None, "clone": clone,
                             "compared_against": "static family chrome",
                             "source": baseline,
                             "defects": compare(family, clone, baseline)})
        finally:
            if source_page is not None:
                source_page.close()
            clone_ctx.close()

    report = {
        "schema_version": "monoprice.visible-audit.v1",
        "viewport": VIEWPORT,
        "source_compared": not args.skip_source,
        "families": len(rows),
        "families_with_defects": sum(1 for r in rows if r["defects"]),
        "rows": rows,
    }
    pathlib.Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.report).write_text(json.dumps(report, indent=2) + "\n",
                                         encoding="utf-8")

    print(f"\n{'family':10s} {'height':>7} {'text':>7} {'rules':>6} "
          f"{'tiles vis/all':>14} {'imgs vis/all':>13} {'unapplied':>9}")
    for r in rows:
        c = r["clone"]
        print(f"{r['family']:10s} {c['height']:>7} {c['text']:>7} {c['rules']:>6} "
              f"{c['tilesVisible']:>6}/{c['tiles']:<7} "
              f"{c['imagesVisible']:>5}/{c['images']:<7} "
              f"{len(c['unappliedStylesheets']):>9}")
    bad = [r for r in rows if r["defects"]]
    if bad:
        print(f"\n{len(bad)} of {len(rows)} families have visible defects:")
        for r in bad:
            print(f"  {r['family']}")
            for d in r["defects"]:
                print(f"    - {d}")
    else:
        print(f"\nall {len(rows)} families render within tolerance of the source")
    if not report["source_compared"]:
        print("\nNOTE: --skip-source was used. The ratio checks DID NOT RUN. "
              "This pass can only catch a page that is broken in isolation.")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
