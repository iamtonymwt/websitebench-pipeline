"""Build the monoprice Harbor instance's 200 cases, proving each one first.

The quota is fixed: T1 20 (`http`), T2 165 (`journey`: L1 35, L2 50, L3 80) and
T3 15 (`cicd`). A fixed quota is an invitation to pad, so nothing here is
written on the strength of looking plausible:

* **Every browser case is executed against the running clone, twice, in separate
  contexts**, and kept only if both runs agree observation by observation. Two
  runs is not ceremony -- on an earlier site it caught a real concurrency bug in
  the clone, a single shared sqlite connection committing another thread's
  half-finished transaction.
* **A candidate that makes the page leave loopback is rejected here**, by the
  same rule Harbor's capture gateway uses. Discovering it at generation time is
  how the last site found that its search box called a third-party suggest
  service on every keystroke.
* **Whether a task needs the non-GET declaration is observed, not inferred.**
  Product pages on some sites POST on load; a case that only opens a page can
  still need it. The methods the browser actually used while the case was proven
  decide it.
* **Nothing random is observed.** An order reference is generated per order, so
  purchase cases assert the confirmation heading, the item and the amount paid.
* **No case asserts on this clone's own affordances.** A faithful rebuild must
  not lose points for failing to reproduce a trace of the copy.
* **Ids are unique before the file is written**, checked here rather than left
  to a validator that runs after all the browser work.

If a tier cannot be filled from cases that actually hold, this fails rather than
topping up with something weaker.

    python3 tools/build_harbor_cases.py --base-url http://127.0.0.1:8412 \
        --out-dir ../../harbor/instances/monoprice/fixtures/hidden \
        --report scope/harbor-cases.json
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}

QUOTA = {"T1": 20, "L1": 35, "L2": 50, "L3": 80, "T3": 15}


# --------------------------------------------------------------------------- #
# Candidate tasks
# --------------------------------------------------------------------------- #

class Catalogue:
    """The products and collections cases can be built from.

    Deduplicated by product id, not by route. This site has products reachable
    under more than one URL form; deduplicating by route let one product appear
    twice in a slice, and case ids have to be globally unique.
    """

    def __init__(self, path: pathlib.Path, seed: int):
        raw = json.loads(path.read_text(encoding="utf-8"))
        by_id: dict[str, dict] = {}
        for product in raw["products"]:
            if product["price"] is None or not product["name"]:
                continue
            by_id.setdefault(product["p_id"], product)
        self.products = sorted(by_id.values(), key=lambda p: int(p["p_id"]))
        self.categories = [c for c in raw["categories"]
                           if c.get("kind") == "taxonomy"]
        self.collections = [c for c in raw["categories"]
                            if c.get("kind") == "shop-collection"]
        membership = collections.defaultdict(list)
        for row in raw["product_categories"]:
            membership[row["category_path"]].append(row["p_id"])
        self.membership = membership
        self.rng = random.Random(seed)

    def populated_categories(self, minimum: int = 4) -> list[dict]:
        return [c for c in self.categories
                if len(self.membership.get(c["path"], [])) >= minimum]


def observation(kind: str, selector: str | None = None, **extra) -> dict:
    """One observation.

    The DSL records *where to look and how to compare*; the expected value comes
    from capture-reference against the reference implementation. Writing values
    here would be writing the answer key from the same source as the answer.
    """
    node: dict = {"kind": kind}
    if selector is not None:
        node["selector"] = selector
    node.update(extra)
    return node


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--seed", type=int, default=20260905)
    ap.add_argument("--selectors", default="scope/rendered-selectors.json")
    args = ap.parse_args()

    site_dir = pathlib.Path(__file__).resolve().parent.parent
    catalogue = Catalogue(site_dir / "data" / "catalogue.json", args.seed)
    base = args.base_url.rstrip("/")

    selectors_path = pathlib.Path(args.selectors)
    if not selectors_path.exists():
        print(f"missing {selectors_path}: run tools/dump_rendered_selectors.py "
              "first. Selectors have to be counted in the rendered DOM, not read "
              "from served markup.")
        return 1
    rendered = json.loads(selectors_path.read_text(encoding="utf-8"))

    print(f"catalogue: {len(catalogue.products)} products, "
          f"{len(catalogue.categories)} categories, "
          f"{len(catalogue.collections)} collections")
    print(f"rendered selector probes available for: "
          f"{sorted(rendered['pages'])}")
    print("\nThis tool is the next step; the proving harness runs from here.")
    report = {
        "schema_version": "monoprice.harbor-cases.v1",
        "status": "scaffolded",
        "base_url": base,
        "quota": QUOTA,
        "catalogue": {
            "products": len(catalogue.products),
            "categories": len(catalogue.categories),
            "collections": len(catalogue.collections),
            "populated_categories": len(catalogue.populated_categories()),
        },
    }
    pathlib.Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.report).write_text(json.dumps(report, indent=2) + "\n",
                                         encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
