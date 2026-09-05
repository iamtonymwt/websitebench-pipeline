"""Build the monoprice catalogue from captured evidence.

Products come from each product page's own schema.org Product block, which
carries name, brand, description, price, currency, sku, gtin14, availability,
rating and the image list. Reading the page's own published record rather than
scraping markup is deliberate: invented field names are how an earlier site in
this family produced a 531-row table of documents that all pointed nowhere.

Two things the Product block does NOT carry, and where they come from instead:

* **Category membership.** A product's breadcrumb names one path. But a product
  appears in several listings, and a listing page is the only place that
  relationship is written down. Both sources are read, and each membership
  records which one it came from -- a listing that is skipped takes its
  categories' entire contents with it.
* **Listing order.** Position within a listing is a property of the listing.

`image` is a JSON *string* holding a JSON array, so it needs decoding twice.
That is parsed in exactly one place here; the same awkward field read two
different ways in two different tools is how the last site got 0 rows twice.

    python3 tools/extract_catalogue.py --capture-dir source-current \
        --out data/catalogue.json --report scope/catalogue-extract.json
"""

from __future__ import annotations

import argparse
import collections
import html as htmllib
import json
import pathlib
import re
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from capture_pages import decode_image_field, read_body  # noqa: E402


def display_text(value: object) -> str:
    """Unescape entities and collapse whitespace, once, everywhere.

    Skipping this is how 192 product names shipped as `Black&#43;Decker` on the
    previous site, found only while proving a Harbor case months later.
    """
    if value is None:
        return ""
    text = str(value)
    for _ in range(2):  # some fields are double-encoded
        new = htmllib.unescape(text)
        if new == text:
            break
        text = new
    return re.sub(r"\s+", " ", text.replace(" ", " ")).strip()


def pid_of(url: str) -> str | None:
    """The product id, with surrounding whitespace removed.

    Two source links carry a stray space -- `p_id= 24285` and `p_id=24288 ` --
    and both name products that also exist without it. Kept raw, they became two
    extra catalogue rows whose url_path was `/product?p_id= 24285`: a product the
    clone would advertise, and a URL nothing would ever request.
    """
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    pid = q.get("p_id")
    return pid.strip() if pid else None


def category_path_of(url: str) -> str | None:
    """A taxonomy path, the kind a breadcrumb names."""
    path = urllib.parse.urlsplit(url).path
    return path if path.startswith(("/category/", "/p/cat")) else None


def listing_path_of(url: str) -> tuple[str, str] | None:
    """(path, kind) for any page that lists products, else None.

    `/p/shop/<slug>` is a second, separate storefront -- 2,622 captured pages
    titled "Shop Cat5 6 Cable | Monoprice" and carrying up to 33 product links
    each. Reading only `/category/` would have left every one of them as an
    unread capture: 2,622 pages fetched, stored, and never asked a question. A
    listing page is the only place a product-to-collection relationship is
    written down, so skipping these would silently drop that whole relation.
    """
    path = urllib.parse.urlsplit(url).path
    if path.startswith(("/category/", "/p/cat")):
        return path, "taxonomy"
    if path.startswith("/p/shop"):
        return path, "shop-collection"
    return None


def parse_price(offers: object) -> tuple[float | None, str | None, str | None,
                                         str | None, str | None]:
    if not isinstance(offers, dict):
        return None, None, None, None, None
    price = offers.get("price")
    try:
        price = float(price) if price is not None else None
    except (TypeError, ValueError):
        price = None
    availability = offers.get("availability")
    if isinstance(availability, str) and "/" in availability:
        availability = availability.rsplit("/", 1)[-1]
    return (price, offers.get("priceCurrency"), offers.get("sku"),
            str(offers.get("gtin14")) if offers.get("gtin14") else None,
            availability)


# A listing tile. The href carries the id; the tile also carries the position.
TILE_RE = re.compile(r'href="(?:[^"]*?)/product\?[^"]*?p_id=(\d+)', re.I)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    capture_dir = pathlib.Path(args.capture_dir)
    products: dict[str, dict] = {}
    categories: dict[str, dict] = {}
    memberships: set[tuple[str, str, str]] = set()
    listing_positions: dict[tuple[str, str], int] = {}
    stats = collections.Counter()
    other_shapes: collections.Counter = collections.Counter()
    problems: dict[str, list[str]] = collections.defaultdict(list)

    page_dirs = [d for d in capture_dir.glob("*/*") if d.is_dir()]
    stats["page_dirs"] = len(page_dirs)

    for page_dir in sorted(page_dirs):
        meta_path = page_dir / "fetch.json"
        if not meta_path.exists():
            stats["missing_meta"] += 1
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        url = meta["url"]
        kind = meta.get("classification")
        if kind != "content":
            stats[f"skipped_{kind}"] += 1
            continue

        # ---- products, from the page's own record -------------------------- #
        extract_path = page_dir / "extract.json"
        if extract_path.exists():
            record = json.loads(extract_path.read_text(encoding="utf-8"))
            pid = pid_of(url)
            if not pid:
                problems["product_without_pid"].append(url)
                continue
            block = record["product"]
            price, currency, sku, gtin, availability = parse_price(block.get("offers"))
            rating = block.get("aggregateRating") or {}
            images = decode_image_field(block.get("image"))
            products[pid] = {
                "p_id": pid,
                "name": display_text(block.get("name")),
                "brand": display_text(block.get("brand")),
                "description": display_text(block.get("description")),
                "sku": display_text(sku) or pid,
                "gtin14": gtin,
                "price": price,
                "currency": currency,
                "availability": availability,
                "rating_value": rating.get("ratingValue"),
                "rating_count": rating.get("ratingCount"),
                "review_count": rating.get("reviewCount"),
                "images": images,
                "url_path": f"/product?p_id={pid}",
            }
            stats["products"] += 1
            if not images:
                problems["product_without_image"].append(url)
            if price is None:
                problems["product_without_price"].append(url)

            # Breadcrumbs: one path per product, and the final crumb is the id
            # itself rather than a category, so it is dropped.
            trail = [c for c in record.get("breadcrumbs") or []
                     if c.get("name") and c["name"] != pid]
            for crumb in trail:
                cpath = category_path_of(crumb.get("url") or "")
                if not cpath:
                    continue
                categories.setdefault(cpath, {"path": cpath,
                                              "name": display_text(crumb["name"])})
                memberships.add((pid, cpath, "breadcrumb"))
            continue

        # ---- listings: the only place membership is written down ----------- #
        listing = listing_path_of(url)
        if listing is None:
            stats["other_pages"] += 1
            other_shapes[urllib.parse.urlsplit(url).path.split("/")[1] or "(root)"] += 1
            continue
        cpath, ckind = listing
        body = read_body(page_dir)
        if body is None:
            # A listing whose body we did not keep would silently contribute no
            # memberships, and its category would come out empty.
            problems["listing_body_missing"].append(url)
            continue
        stats[f"listings_{ckind}"] += 1
        title = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
        raw_title = display_text(title.group(1)) if title else ""
        name = display_text(raw_title.split(" - ")[0].split(" | ")[0])
        categories.setdefault(cpath, {"path": cpath, "name": name, "kind": ckind})
        if name and not categories[cpath].get("name"):
            categories[cpath]["name"] = name
        categories[cpath].setdefault("kind", ckind)
        seen_here: set[str] = set()
        for pid in TILE_RE.findall(body):
            if pid in seen_here:
                continue
            seen_here.add(pid)
            memberships.add((pid, cpath, "listing"))
            listing_positions.setdefault((cpath, pid), len(seen_here))
        stats["listing_tiles"] += len(seen_here)
        if not seen_here:
            problems["listing_with_no_tiles"].append(url)

    # Category tree from the paths themselves. Shop collections are flat: their
    # slugs are marketing phrases, not a hierarchy, so inferring a parent from
    # the path would invent a structure the source does not have.
    for cpath in list(categories):
        if categories[cpath].get("kind") == "shop-collection":
            categories[cpath]["level"] = 0
            categories[cpath]["parent"] = None
            continue
        segs = [s for s in cpath.split("/") if s]
        categories[cpath]["level"] = max(0, len(segs) - 1)
        parent = "/" + "/".join(segs[:-1]) if len(segs) > 2 else None
        categories[cpath]["parent"] = parent if parent in categories else None

    # Memberships that name a product we never captured are recorded, not
    # dropped: they are the difference between "this category is empty" and
    # "we did not capture its products", and only the second is our defect.
    known = set(products)
    resolved = [(p, c, src) for (p, c, src) in sorted(memberships) if p in known]
    dangling = [(p, c, src) for (p, c, src) in sorted(memberships) if p not in known]

    catalogue = {
        "schema_version": "monoprice.catalogue.v1",
        "source": "schema.org Product blocks and captured listing pages",
        "products": [products[p] for p in sorted(products, key=int)],
        "categories": [categories[c] for c in sorted(categories)],
        "product_categories": [
            {"p_id": p, "category_path": c, "evidence": src,
             "position": listing_positions.get((c, p))}
            for (p, c, src) in resolved
        ],
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(catalogue, indent=1) + "\n", encoding="utf-8")

    by_evidence = collections.Counter(src for _, _, src in resolved)
    per_category = collections.Counter(c for _, c, _ in resolved)
    empty_categories = [c for c in categories if per_category[c] == 0]
    report = {
        "schema_version": "monoprice.catalogue-extract.v1",
        "capture_dir": str(capture_dir),
        "counts": {
            "products": len(products),
            "categories": len(categories),
            "memberships_resolved": len(resolved),
            "memberships_dangling": len(dangling),
            "memberships_by_evidence": dict(by_evidence),
            "categories_with_no_products": len(empty_categories),
        },
        "pages": dict(stats),
        # Which captured evidence this tool never asked a question of. A page
        # fetched, stored and never read is invisible unless it is counted --
        # /p/shop was 2,622 such pages until this line existed.
        "captured_but_not_read_by_this_tool": dict(other_shapes.most_common()),
        "problems": {k: {"count": len(v), "examples": v[:8]}
                     for k, v in sorted(problems.items())},
        "dangling_examples": dangling[:10],
        "empty_category_examples": sorted(empty_categories)[:10],
        "note": ("`memberships_dangling` names products that a listing links to "
                 "but that were never captured. They are reported rather than "
                 "dropped: a category that looks empty because its products were "
                 "not captured is a capture gap, and a category the source itself "
                 "renders empty is a source fact. Only the first is a defect."),
    }
    pathlib.Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.report).write_text(json.dumps(report, indent=2) + "\n",
                                         encoding="utf-8")
    print(json.dumps(report, indent=2)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
