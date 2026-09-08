"""Resolve each product page's variant options to the products they lead to.

Product pages carry a variant chooser -- `Length: 0.5ft 1ft 2ft 3ft ...` -- and
clicking a value POSTs to `/product/selectpid` with the values currently
selected. The response is JSON holding rendered partials for the product that
combination identifies. The site resolves the combination server-side, and the
markup contains **no product id for any option**, so nothing in the captured
page says where an option leads.

Without this map the clone answered that POST with a 404, which sends the site's
own handler down its error branch:

    error: function () { mpSpinner.hide();
                         location.href = '/StaticContent/generalerror'; }

so clicking a variant navigated to an error page. Measured on the frozen pages:
951 of 1,427 variant options are genuinely selectable (the rest are marked
`na`, "Not Available", by the source itself), and 90 of 121 sampled product
pages have at least one option a person can click.

The resolution rule is name substitution, and it is checked rather than trusted:
the option's value replaces the currently selected value in the product's name,
and the result must match a catalogue product's name **exactly**. For
`Monoprice Cat5e Ethernet Patch Cable ... 0.5ft`, clicking `2ft` resolves to
p_id 11302. Measured over every selectable option on every frozen product page:

    4,720 options attempted -> 3,807 resolved (81%), 913 unresolved

The 913 are written to the report, not dropped silently, and the clone leaves
the page unchanged for them rather than guessing a neighbour. A wrong product
shown under the right variant label would be worse than a control that does
nothing, because it looks correct.

    python3 tools/build_variant_map.py --frozen-root clone/static/frozen \
        --catalogue data/catalogue.json --out clone/static/variant-map.json \
        --report scope/variant-map.json
"""

from __future__ import annotations

import argparse
import collections
import gzip
import json
import pathlib
import re

FORM = re.compile(
    r'<form\b[^>]*class="[^"]*mp-prod-attrform[^"]*"[^>]*'
    r'data-mp-attrname\s*=\s*"([^"]*)"[^>]*'
    r'data-mp-attrselval\s*=\s*"([^"]*)"[^>]*>(.*?)</form>', re.S | re.I)
OPTION = re.compile(r'<span\b[^>]*data-mp-attrval\s*=\s*"([^"]*)"[^>]*>', re.I)
CLASSES = re.compile(r'class\s*=\s*"([^"]*)"', re.I)


def unavailable(tag: str) -> bool:
    """The source marks an option it does not sell with class `na`."""
    m = CLASSES.search(tag)
    classes = (m.group(1) if m else "").lower().split()
    return "na" in classes


def selected(tag: str) -> bool:
    m = CLASSES.search(tag)
    return "selected" in (m.group(1) if m else "").lower().split()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frozen-root", required=True)
    ap.add_argument("--catalogue", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    catalogue = json.loads(pathlib.Path(args.catalogue).read_text(encoding="utf-8"))
    by_name: dict[str, str] = {}
    for product in catalogue["products"]:
        by_name.setdefault(product["name"].strip().lower(), product["p_id"])
    name_of = {p["p_id"]: p["name"] for p in catalogue["products"]}

    product_dir = pathlib.Path(args.frozen_root) / "product"
    pages = sorted(product_dir.glob("q__p_id=*.html.gz")) if product_dir.exists() else []

    variant_map: dict[str, dict[str, str]] = {}
    tally: collections.Counter = collections.Counter()
    unresolved: list[dict] = []

    for path in pages:
        m = re.search(r"p_id=(\d+)", path.name)
        if not m:
            continue
        pid = m.group(1)
        current_name = name_of.get(pid)
        if not current_name:
            tally["page_for_product_not_in_catalogue"] += 1
            continue
        with gzip.open(path, "rb") as fh:
            html = fh.read().decode("utf-8", "replace")

        for attr_name, sel_value, body in FORM.findall(html):
            tally["attribute_forms"] += 1
            if not sel_value:
                tally["form_without_a_selected_value"] += 1
                continue
            # The rule only works when the selected value appears in the name;
            # otherwise there is nothing to substitute and a match would be a
            # coincidence.
            if sel_value.lower() not in current_name.lower():
                tally["selected_value_not_in_product_name"] += 1
                continue
            for option in OPTION.finditer(body):
                tag, value = option.group(0), option.group(1)
                if not value or selected(tag):
                    continue
                if unavailable(tag):
                    tally["option_marked_unavailable_by_source"] += 1
                    continue
                tally["option_selectable"] += 1
                candidate = re.sub(re.escape(sel_value), value, current_name,
                                   flags=re.I).strip().lower()
                target = by_name.get(candidate)
                if target and target != pid:
                    variant_map.setdefault(pid, {})[value] = target
                    tally["resolved"] += 1
                else:
                    tally["unresolved"] += 1
                    if len(unresolved) < 60:
                        unresolved.append({"p_id": pid, "attribute": attr_name,
                                           "from": sel_value, "to": value,
                                           "looked_for": candidate[:90]})

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "schema_version": "monoprice.variant-map.v1",
        "rule": "the clicked value replaces the selected value in the product "
                "name; the result must match a catalogue product name exactly",
        "products": variant_map,
    }, indent=1) + "\n", encoding="utf-8")

    attempted = tally["resolved"] + tally["unresolved"]
    report = {
        "schema_version": "monoprice.variant-map-report.v1",
        "pages_read": len(pages),
        "products_with_at_least_one_resolved_option": len(variant_map),
        "options_attempted": attempted,
        "options_resolved": tally["resolved"],
        "options_unresolved": tally["unresolved"],
        "resolution_rate": (round(tally["resolved"] / attempted, 3)
                            if attempted else None),
        "counters": dict(sorted(tally.items())),
        "unresolved_examples": unresolved,
        "note": "Unresolved options are left out of the map on purpose. The "
                "clone answers them by returning the current product unchanged "
                "rather than a guessed neighbour: a wrong product under the "
                "right variant label looks correct and is not.",
    }
    pathlib.Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.report).write_text(json.dumps(report, indent=2) + "\n",
                                         encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("unresolved_examples", "counters")}, indent=2))

    if attempted and tally["resolved"] / attempted < 0.5:
        print("\nresolution rate below 50%: the substitution rule does not hold "
              "for this catalogue and the map should not be shipped as is")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
