"""Cut a product-detail template out of a real frozen product page.

3,289 products kept a structured extract rather than a body, and they have to be
rendered from something. That something is a page the source actually served,
with one product's values replaced by placeholders.

The substitution points are found by **searching the markup for that product's
known values** -- its name, price, sku, image URLs -- rather than by guessing
selectors. Guessed selectors are how a template silently stops matching: the
last site had `#searchTextInput` present in every served page and absent from
every rendered one, and observations written against it recorded empty from both
the reference and the candidate, so they passed for everyone and tested nothing.

The tool refuses to write a template when a value it must substitute cannot be
found in the page. A template with a placeholder that was never inserted renders
one product's data under every product's name.

    python3 tools/extract_detail_template.py \
        --frozen-root clone/static/frozen --catalogue data/catalogue.json \
        --out clone/static/detail-template.html \
        --report scope/detail-template.json
"""

from __future__ import annotations

import argparse
import collections
import gzip
import html
import json
import pathlib
import re

PLACEHOLDER = {
    "name": "@@WB_NAME@@",
    "description": "@@WB_DESCRIPTION@@",
    "price": "@@WB_PRICE@@",
    "sku": "@@WB_SKU@@",
    "pid": "@@WB_PID@@",
    "brand": "@@WB_BRAND@@",
    "image": "@@WB_IMAGE@@",
    "gtin": "@@WB_GTIN@@",
}


def load(path: pathlib.Path) -> str:
    with gzip.open(path, "rb") as fh:
        return fh.read().decode("utf-8", "replace")


def local_asset_form(url: str) -> str | None:
    """The localised path a source asset URL becomes in a frozen page.

    The freezer rewrites references, including the ones inside embedded JSON, so
    a donor page no longer contains `https://images.monoprice.com/...`. Searching
    for the absolute URL found zero occurrences and the extractor correctly
    refused to write -- a template whose image placeholder was never inserted
    would have rendered the donor's own photographs under every other product.
    """
    import urllib.parse
    split = urllib.parse.urlsplit(url)
    if not split.netloc:
        return None
    local = urllib.parse.unquote(split.path.lstrip("/"))
    return f"/static/assets/{split.netloc.lower()}/{urllib.parse.quote(local)}"


def variants(value: str) -> list[str]:
    """The forms one value can take in served markup."""
    out = [value]
    localised = local_asset_form(value) if value.startswith("http") else None
    if localised:
        out.append(localised)
    escaped = html.escape(value, quote=True)
    if escaped != value:
        out.append(escaped)
    out.append(html.escape(value, quote=False))
    out.append(json.dumps(value)[1:-1])          # JSON-escaped, no quotes
    seen: dict[str, None] = {}
    for v in out:
        if v and v not in seen:
            seen[v] = None
    return list(seen)


def substitute(markup: str, value: str, token: str,
               tally: collections.Counter, label: str) -> str:
    replaced = 0
    for form in variants(value):
        if len(form) < 3:
            continue
        count = markup.count(form)
        if count:
            markup = markup.replace(form, token)
            replaced += count
    tally[label] = replaced
    return markup


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

    # Pick a donor that has everything a template needs: a frozen body, a name,
    # a price, a sku and at least two images. A donor missing a field would
    # produce a template with no place to put that field, and every product
    # rendered from it would be missing it too -- invisibly.
    donor = None
    product_dir = frozen_root / "product"
    for path in sorted(product_dir.glob("q__p_id=*.html.gz")) if product_dir.exists() else []:
        m = re.search(r"p_id=(\d+)", path.name)
        if not m:
            continue
        product = by_id.get(m.group(1))
        if not product:
            continue
        if (product["name"] and product["price"] and product["sku"]
                and len(product["images"]) >= 2 and product["description"]):
            donor = (path, product)
            break
    if donor is None:
        print("no frozen product page has every field a template needs")
        return 1

    path, product = donor
    markup = load(path)
    tally: collections.Counter = collections.Counter()

    # Longest first: substituting the sku before the p_id would leave the p_id
    # occurrences inside the already-replaced token untouched, and substituting
    # a short value first can corrupt a longer one that contains it.
    markup = substitute(markup, product["description"], PLACEHOLDER["description"],
                        tally, "description")
    markup = substitute(markup, product["name"], PLACEHOLDER["name"], tally, "name")
    for index, image in enumerate(product["images"]):
        markup = substitute(markup, image, f"@@WB_IMAGE_{index}@@", tally,
                            f"image_{index}")
    price_text = f"{product['price']:.2f}"
    markup = substitute(markup, price_text, PLACEHOLDER["price"], tally, "price")
    if product["gtin14"]:
        markup = substitute(markup, product["gtin14"], PLACEHOLDER["gtin"],
                            tally, "gtin")
    # Brand is deliberately NOT substituted. Every product in this catalogue is
    # brand "Monoprice" -- which is also the site name, in the logo alt text, the
    # nav, the footer and the title. Substituting it hit 31 places, so a product
    # with any other brand would have rewritten the page chrome to that brand.
    # A field that is constant across the catalogue has nothing to template.
    tally["brand_intentionally_not_substituted"] = 1
    markup = substitute(markup, product["sku"], PLACEHOLDER["sku"], tally, "sku")
    # sku and p_id are the same string for 3,857 of 3,859 products, so the sku
    # pass has already consumed the id. Only substitute separately when they
    # actually differ.
    if product["p_id"] != product["sku"]:
        markup = substitute(markup, product["p_id"], PLACEHOLDER["pid"], tally, "pid")
    else:
        tally["pid_same_as_sku"] = 1

    # The refusal. A field that was never found has no place in the template, and
    # rendering into it would leave the donor's own value showing under someone
    # else's product.
    required = ["name", "description", "price", "sku", "image_0"]
    missing = [field for field in required if tally.get(field, 0) == 0]
    report = {
        "schema_version": "monoprice.detail-template.v1",
        "donor_page": str(path.relative_to(frozen_root)),
        "donor_p_id": product["p_id"],
        "donor_name": product["name"],
        "substitutions": dict(sorted(tally.items())),
        "required_fields_missing": missing,
        "images_in_donor": len(product["images"]),
        "written": not missing,
    }
    pathlib.Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.report).write_text(json.dumps(report, indent=2) + "\n",
                                         encoding="utf-8")
    print(json.dumps(report, indent=2))
    if missing:
        print(f"\nREFUSING to write: {missing} could not be located in the donor "
              "page. A template whose placeholder was never inserted renders the "
              "donor's own data under every other product's name.")
        return 1
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markup, encoding="utf-8")
    print(f"\nwrote {out} ({len(markup)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
