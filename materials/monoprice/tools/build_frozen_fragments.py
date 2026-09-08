"""Localise the captured AJAX fragments so the clone can serve them.

`capture_fragments.py` saves what the source returns, which is raw markup full
of absolute `https://images.monoprice.com/...` and `https://www.monoprice.com/...`
references. Serving that as-is would inject remote references into the page at
run time and quietly undo the property the whole run is built on -- 0 remote
requests across every audited route. It would also be invisible: the injection
happens after load, so a page-load audit sees nothing.

So fragments go through the same reference rewriting as pages, using the
freezer's own `Localiser` and `freeze_page`. Reusing them rather than writing a
second rewriter is deliberate: this site already produced one bug from parsing
the same thing in two places, and a fragment rewriter that drifts from the page
rewriter would be a rewriter that localises 96% of references and leaves the
rest calling a CDN.

`freeze_page`'s two injections -- the stripped-globals shim and the search
submit fix -- are guarded on finding `<head` and `</body>`, which a fragment has
neither of, so they are no-ops here. The report asserts that.

    python3 tools/build_frozen_fragments.py --fragments scope/fragments.json \
        --assets-dir source-assets --catalogue data/catalogue.json \
        --out-root clone/static/fragments --report scope/frozen-fragments.json
"""

from __future__ import annotations

import argparse
import collections
import gzip
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from build_frozen_pages import Localiser, freeze_page  # noqa: E402

BASE = "https://www.monoprice.com/"
# Anything still pointing at one of these after rewriting is a reference that
# would leave the machine.
REMOTE = re.compile(r"https?:(?:\\?/){2}(?:www\.|images\.)?monoprice\.com|"
                    r"https?:(?:\\?/){2}cdn\.prod\.website-files\.com", re.I)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fragments", required=True)
    ap.add_argument("--assets-dir", required=True)
    ap.add_argument("--catalogue", required=True)
    ap.add_argument("--out-root", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    manifest = json.loads(pathlib.Path(args.fragments).read_text(encoding="utf-8"))
    catalogue = json.loads(pathlib.Path(args.catalogue).read_text(encoding="utf-8"))
    served_products = {p["p_id"] for p in catalogue["products"]}
    served_routes = {c["path"] for c in catalogue["categories"]}
    assets_dir = pathlib.Path(args.assets_dir)
    src_root = pathlib.Path(manifest["root"])
    out_root = pathlib.Path(args.out_root)

    tally: collections.Counter = collections.Counter()
    index: dict[str, dict] = {}
    still_remote: list[str] = []
    empty = 0

    for key, entry in manifest["fragments"].items():
        src = src_root / entry["file"]
        if not src.exists():
            tally["missing_capture"] += 1
            continue
        with gzip.open(src, "rb") as fh:
            raw = fh.read().decode("utf-8", "replace")

        if not raw.strip():
            # An empty fragment is a real answer: the source returns nothing for
            # `also shopped for` on some products, and nothing for recently
            # viewed when the session has no history. Recording it lets the
            # clone reproduce "no strip here" instead of guessing.
            empty += 1
            index[key] = {"file": None, "empty": True,
                          "container": entry.get("container")}
            continue

        loc = Localiser(assets_dir, BASE, served_routes, served_products)
        frozen = freeze_page(raw, BASE, loc, tally)
        tally.update(loc.tally)

        for marker in ("data-wb-stripped-globals", "data-wb-search-submit"):
            if marker in frozen:
                # Would mean freeze_page found a <head>/</body> in a fragment,
                # i.e. this is not a fragment and the assumption above is wrong.
                tally[f"unexpected_injection:{marker}"] += 1

        leftover = REMOTE.findall(frozen)
        if leftover:
            still_remote.append(f"{key}: {len(leftover)}")

        out = out_root / entry["file"]
        out.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(out, "wb") as fh:
            fh.write(frozen.encode("utf-8"))
        index[key] = {"file": entry["file"], "empty": False,
                      "container": entry.get("container"),
                      "tiles": len(re.findall(r"p_id=\d+", frozen)),
                      "bytes": len(frozen)}

    report = {
        "schema_version": "monoprice.frozen-fragments.v1",
        "out_root": str(out_root),
        "fragments_written": sum(1 for v in index.values() if v["file"]),
        "fragments_empty_at_source": empty,
        "fragments_with_remote_references_left": len(still_remote),
        "remote_examples": still_remote[:10],
        "rewrites": dict(sorted(tally.items())),
        "fragments": index,
    }
    pathlib.Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.report).write_text(json.dumps(report, indent=2) + "\n",
                                         encoding="utf-8")

    # The clone reads this, not the report in scope/. A served application that
    # reaches into the evidence tree for a file it needs at request time is an
    # application that breaks the moment it is deployed anywhere else.
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "index.json").write_text(json.dumps({
        "schema_version": "monoprice.fragment-index.v1",
        "fragments": index,
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "fragments"},
                     indent=2)[:1800])

    if still_remote:
        print(f"\n{len(still_remote)} fragments still carry references that "
              "would leave the machine. Serving these would put remote requests "
              "back into pages that currently make none.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
