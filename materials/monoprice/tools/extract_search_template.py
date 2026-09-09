"""Cut a search-results template out of a real frozen search page.

The clone has to answer `/search/index?keyword=<anything>`, not only the 139
keywords that happened to be captured. What it must not do is invent the markup:
class names written from an idea of "what a results grid looks like" produce a
page that is styled by nothing, because the stylesheet is real and the class
names are not. That is exactly how the last site shipped three page types with
no layout at all.

So the grid is taken from a page the source served. One result tile is isolated,
its product's values are replaced with placeholders, and the app repeats that
tile for each hit.

Finding the tile: a captured search page carries many `p_id=` links. The tile is
the smallest repeating block that contains exactly one of them. It is located by
taking the markup between consecutive product links and walking outward to the
enclosing element that both share.

The tool refuses to write unless the isolated tile round-trips: it must contain
the product's name, its price and its link, and repeating it twice must produce
markup with two product links.

    python3 tools/extract_search_template.py --frozen-root clone/static/frozen \
        --catalogue data/catalogue.json --out clone/static/search-template.json \
        --report scope/search-template.json
"""

from __future__ import annotations

import argparse
import gzip
import json
import pathlib
import re
import urllib.parse

RESULTS_MARK = "@@WB_RESULTS@@"
COUNT_MARK = "@@WB_RESULT_COUNT@@"
QUERY_MARK = "@@WB_QUERY@@"
TILE_FIELDS = {"name": "@@WB_TILE_NAME@@", "price": "@@WB_TILE_PRICE@@",
               "pid": "@@WB_TILE_PID@@", "image": "@@WB_TILE_IMAGE@@"}


def load(path: pathlib.Path) -> str:
    with gzip.open(path, "rb") as fh:
        return fh.read().decode("utf-8", "replace")


ROW = re.compile(r"<tr\b[^>]*>.*?</tr\s*>", re.I | re.S)


def find_tiles(html: str) -> list[tuple[int, int, str]]:
    """Candidate repeating blocks, each for exactly one product.

    The first version looked for the last `<div|li|article>` between two
    consecutive product links, and found nothing usable. Two things were wrong,
    and looking at the markup settled both: results are a `<table
    class="hawk-list-table">` of `<tr>` rows, not divs -- and one product
    contributes *five* links (image, sale badge, title, and so on), so "between
    two consecutive links" is a boundary inside a single tile, not between two.

    A tile is a `<tr>` whose product links all name the same id.
    """
    # Innermost rows only, found by walking depth rather than by a non-greedy
    # `<tr>.*?</tr>`.
    #
    # That pattern, started on an OUTER layout row, ends at the first inner
    # `</tr>` -- a span that begins before `<div id="existresult">` and ends
    # inside the first product row. It contains exactly one product id, so it
    # passed for a tile. The median filter happened to reject it for being
    # 21,384 bytes, which is the only reason the page kept its results
    # container; removing every "tile" then deleted `#existresult` outright and
    # the search page had nowhere to put results.
    #
    # A real tile contains no nested row. That is the whole rule.
    rows: list[tuple[int, int, str]] = []
    stack: list[int] = []
    for m in re.finditer(r"<(/?)tr\b[^>]*>", html, re.I):
        if not m.group(1):
            stack.append(m.start())
        elif stack:
            start = stack.pop()
            block = html[start:m.end()]
            if len(re.findall(r"<tr\b", block, re.I)) != 1:
                continue
            ids = set(re.findall(r'href="/product\?p_id=(\d+)"', block))
            if len(ids) == 1:
                rows.append((start, m.end(), block))
    rows.sort()
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frozen-root", required=True)
    ap.add_argument("--catalogue", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    frozen_root = pathlib.Path(args.frozen_root)
    catalogue = json.loads(pathlib.Path(args.catalogue).read_text(encoding="utf-8"))
    by_id = {p["p_id"]: p for p in catalogue["products"]}

    search_dir = frozen_root / "search" / "index"
    candidates = sorted(search_dir.glob("*.html.gz")) if search_dir.exists() else []
    # Pick the donor with the most distinct known products, not the first one
    # that passes a threshold.
    #
    # An earlier version rejected any page containing "unable to find search
    # results" -- and rejected all 422, because that phrase is a *hidden template
    # block present on every search page*, shown or hidden by HawkSearch. It
    # never discriminated between a page with results and a page without; it just
    # matched everything. The count of distinct products the catalogue knows is
    # the signal: the promotional keyword pages carry 4, a real search carries 25.
    scored: list[tuple[int, tuple[int, int], pathlib.Path, str, list[str]]] = []
    for path in candidates:
        html = load(path)
        links = re.findall(r'href="/product\?p_id=(\d+)"', html)
        known = [pid for pid in links if pid in by_id]
        # Prefer a donor whose own URL selected no facets.
        #
        # Every facet link in the sidebar preserves the facets already selected
        # on the page it was captured from. The first donor chosen here was
        # `?Number_of_Channels_uFilter=2&keyword=clearance/overstock`, so every
        # filter link on every search the clone served carried
        # `Number_of_Channels_uFilter=2` -- and no HDMI cable has that, so
        # clicking any filter returned nothing at all. The sidebar looked right
        # and was inert.
        #
        # Paging is avoided for the same kind of reason: a `pgNum=3` donor bakes
        # page three's paging state into every page.
        from_url = urllib.parse.unquote(path.name)
        penalty = (len(re.findall(r"_uFilter=", from_url)),
                   1 if "pgNum=" in from_url else 0)
        scored.append((len(set(known)), penalty, path, html, known))
    # Most products first, then fewest inherited facets, then no paging.
    scored.sort(key=lambda row: (-row[0], row[1]))
    chosen = None
    if scored and scored[0][0] >= 8:
        _, _, path_best, html_best, known_best = scored[0]
        chosen = (path_best, html_best, known_best)
    report_distinct = scored[0][0] if scored else 0

    report: dict = {"schema_version": "monoprice.search-template.v1",
                    "candidates": len(candidates)}
    if chosen is None:
        report["error"] = ("no frozen search page carries at least 8 distinct "
                           "products the catalogue knows")
        report["best_donor_distinct_products"] = report_distinct
        pathlib.Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        return 1

    path, html, known = chosen
    route_map = json.loads((frozen_root / "route-map.json").read_text())["routes"]
    route = str(path.relative_to(frozen_root)).removesuffix(".html.gz")
    donor_url = next((u for u, r in route_map.items() if r == route), "")
    tiles = find_tiles(html)
    # Every result row, before the median filter narrows the list to a
    # representative shape. The filter exists to choose which row to TEMPLATE;
    # it must not decide which rows to REMOVE. Using the filtered list left the
    # one row the filter rejected -- p_id 44695, 21,384 bytes against a median
    # band -- sitting in the page, and every search on the clone opened with
    # that product.
    all_result_rows = list(tiles)
    report["donor_page"] = str(path.relative_to(frozen_root))
    report["product_links_in_donor"] = len(known)
    report["tile_candidates"] = len(tiles)
    report["best_donor_distinct_products"] = report_distinct

    # Pick a tile whose product we know everything about, so every placeholder
    # has a value to be replaced from -- and which is the *repeating* unit. Rows
    # differ in size, and the odd one out is the wrapper: on the first donor the
    # largest row was the whole results area, header and sort controls included.
    # Selecting near the median of the row sizes picks the shape that repeats.
    if len(tiles) >= 3:
        sizes = sorted(len(block) for _, _, block in tiles)
        median = sizes[len(sizes) // 2]
        tiles = [t for t in tiles if abs(len(t[2]) - median) <= 0.25 * median]
        report["tiles_after_median_filter"] = len(tiles)

    picked = None
    for start, end, block in tiles:
        found = re.search(r'href="/product\?p_id=(\d+)"', block)
        if not found:
            continue
        product = by_id.get(found.group(1))
        if not product or not product["name"] or product["price"] is None:
            continue
        if product["name"] not in block and product["name"][:40] not in block:
            continue
        picked = (start, end, block, product)
        break

    if picked is None:
        report["error"] = ("no candidate tile contained a known product's name "
                           "and price; the tile boundary is probably wrong")
        pathlib.Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        return 1

    start, end, block, product = picked
    tile = block
    subs = {}

    # The result row shows a *truncated* title -- the picker matched on a 40
    # character prefix, and substituting the full name replaced nothing while
    # reporting success. Find the longest prefix that is actually present, and
    # record its length so the app truncates the same way the source does.
    name = product["name"]
    name_len = 0
    for length in range(len(name), 9, -1):
        if name[:length] in tile:
            name_len = length
            break
    if name_len:
        subs["name"] = tile.count(name[:name_len])
        subs["name_truncated_at"] = name_len if name_len < len(name) else None
        tile = tile.replace(name[:name_len], TILE_FIELDS["name"])
    else:
        subs["name"] = 0

    subs["pid"] = tile.count(product["p_id"])
    tile = tile.replace(product["p_id"], TILE_FIELDS["pid"])
    price_text = f"{product['price']:.2f}"
    subs["price"] = tile.count(price_text)
    tile = tile.replace(price_text, TILE_FIELDS["price"])
    for image in product["images"]:
        local = "/static/assets/images.monoprice.com/" + image.split("images.monoprice.com/")[-1]
        if local in tile:
            subs["image"] = tile.count(local)
            tile = tile.replace(local, TILE_FIELDS["image"])
            break

    # The refusal: the tile has to actually be a tile.
    checks = {
        "tile_has_name": TILE_FIELDS["name"] in tile,
        "tile_has_pid": TILE_FIELDS["pid"] in tile,
        "tile_has_price": TILE_FIELDS["price"] in tile,
        # 20k was a guess and it rejected a genuine 23k row. These rows
        # carry an image, a rating widget, a price block and an
        # add-to-cart form; the cap exists only to catch a runaway that
        # swallowed the whole page, so it is set well above the real size.
        "tile_not_absurdly_large": len(tile) < 60_000,
        "repeating_yields_two_links":
            len(re.findall(r"@@WB_TILE_PID@@", tile * 2)) >= 2,
    }
    report["substitutions"] = subs
    report["tile_bytes"] = len(tile)
    report["checks"] = checks
    failed = [k for k, ok in checks.items() if not ok]
    report["failed_checks"] = failed
    if failed:
        report["written"] = False
        pathlib.Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        print(f"\nREFUSING to write: {failed}")
        return 1

    # Replace EVERY result row, not just the one that was templated.
    #
    # This line used to be `html[:start] + RESULTS_MARK + html[end:]`, which
    # removed the single row we had turned into a tile and left the donor's other
    # 24 rows sitting in the page. Every search on the clone then rendered the
    # donor's products above its own results: `hdmi cable`, `speaker` and
    # `keyboard` all began with p_id 44695. It also doubled the page -- the
    # visible-content audit measured 2.67x the source's text and blamed the facet
    # sidebar, because 24 extra product rows look like ordinary page weight.
    #
    # The rows come from ROW.finditer, so they do not overlap, and the picked one
    # is among them. Rebuild the page around them in one pass.
    rows_to_drop = sorted((s, e) for s, e, _ in all_result_rows)
    pieces: list[str] = []
    cursor = 0
    replaced_at = None
    for s, e in rows_to_drop:
        if s < cursor:                       # defensive: never happens for <tr>
            continue
        pieces.append(html[cursor:s])
        if s == start:
            pieces.append(RESULTS_MARK)
            replaced_at = s
        cursor = e
    pieces.append(html[cursor:])
    page = "".join(pieces)
    report["result_rows_removed"] = len(rows_to_drop)
    report["results_mark_placed"] = replaced_at is not None

    # The refusal. A donor product link left in the page is a product the clone
    # advertises on every search regardless of the query.
    leftover = re.findall(r'href="/product\?p_id=(\d+)"', page)
    report["donor_product_links_left"] = len(leftover)
    if leftover or replaced_at is None:
        report["written"] = False
        report["leftover_examples"] = sorted(set(leftover))[:8]
        pathlib.Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        print(f"\nREFUSING to write: {len(leftover)} donor product links remain "
              f"in the template page, or the results mark was never placed. "
              f"Every search would show those products.")
        return 1

    # The donor's own query is baked into the page 25 times as text and 284
    # times URL-encoded -- in the title, the heading, the breadcrumb and every
    # facet link. Left alone, every search on the clone would be titled
    # "Search - CLEARANCE/OVERSTOCK".
    donor_query = urllib.parse.parse_qs(
        urllib.parse.urlsplit(donor_url).query).get("keyword", [""])[0]
    query_subs = {}
    if donor_query:
        for form, mark in ((donor_query, QUERY_MARK),
                           (donor_query.upper(), QUERY_MARK + "_UPPER"),
                           (urllib.parse.quote(donor_query, safe=""), QUERY_MARK + "_ENC"),
                           (urllib.parse.quote_plus(donor_query), QUERY_MARK + "_PLUS")):
            count = page.count(form)
            if count:
                page = page.replace(form, mark)
                query_subs[mark] = count
    report["query_substitutions"] = query_subs
    # The result count is NOT substituted. "224" appears 300 times in this page,
    # and most of them are not the count -- they occur inside product ids, prices
    # and asset names. Replacing all of them would corrupt the page to fix a
    # number. The difference is recorded in scope/claims.jsonl instead.
    report["result_count_not_substituted"] = True
    payload = {"schema_version": "monoprice.search-template.v1",
               "page": page, "tile": tile,
               "name_truncate_at": subs.get("name_truncated_at"),
               "donor_page": str(path.relative_to(frozen_root)),
               "donor_url": donor_url,
               "donor_p_id": product["p_id"]}
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    report["written"] = True
    report["page_bytes"] = len(page)
    pathlib.Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
