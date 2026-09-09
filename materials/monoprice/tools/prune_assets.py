"""Delete asset files that nothing the clone serves refers to.

The asset tree is 2.7 GB and was fetched from a plan built during capture. A
plan is a superset by construction: it lists what the *source* referenced,
including pages that were never frozen, products that are not in the catalogue,
and image sizes the served markup never asks for.

This finds what is actually reachable from what the clone serves -- every frozen
page, every localised fragment, the three derived templates, and the served CSS
and JS, which carry their own `url(...)` references after
`patch_served_assets.py` has rewritten them. Anything not reachable is dead
weight.

Two rules keep this from being destructive:

  * It is a dry run unless `--apply` is given.
  * It refuses to run at all if the reachable set looks implausibly small, which
    is what a broken reference scan looks like. Deleting 2.7 GB because a regex
    stopped matching is exactly the kind of silent, total failure this site has
    produced twice already.

    python3 tools/prune_assets.py --assets-dir source-assets \\
        --report scope/asset-prune.json            # dry run
    python3 tools/prune_assets.py ... --apply

RESULT ON THIS SITE, and the reason to treat `--apply` with suspicion:

  * The first dry run called 20,519 files unreachable, 16,066 of them product
    photographs. They are referenced only from the `product_images` table, which
    the app reads at request time -- no file on disk points at them. Deleting
    them would have emptied every product page while link closure, the
    remote-request audit and the test suite all stayed green.
  * With the catalogue added as a root, the unreachable set fell to 4,453 files
    and **32 MB of 2.7 GB** -- 1.2%.
  * Applying even that broke the search page: `productmediumimages/24051.jpg`
    and others began answering 404. They were restored from git.

So the honest summary is that this asset tree has almost no dead weight, and a
reachability scan cannot see every root a running application uses. The tool is
kept for its report. Do not `--apply` without loading the clone afterwards and
checking a page from every family for broken images.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import json
import pathlib
import re
import urllib.parse

PREFIX = "/static/assets/"
# Matches a localised asset reference wherever it appears: an attribute, a CSS
# url(), embedded JSON with escaped slashes.
REFERENCE = re.compile(
    r"/static(?:\\?/)assets(?:\\?/)([A-Za-z0-9.-]+)((?:\\?/)[^\s\"'<>()\\,;]+)")


def read(path: pathlib.Path) -> str:
    if path.suffix == ".gz":
        with gzip.open(path, "rb") as fh:
            return fh.read().decode("utf-8", "replace")
    return path.read_text(encoding="utf-8", errors="replace")


def referenced_in(text: str) -> set[tuple[str, str]]:
    out = set()
    for m in REFERENCE.finditer(text):
        host = m.group(1).lower()
        rel = m.group(2).replace("\\/", "/").lstrip("/")
        rel = urllib.parse.unquote(rel.split("?")[0].split("#")[0])
        if rel:
            out.add((host, rel))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets-dir", default="source-assets")
    ap.add_argument("--clone-dir", default="clone")
    ap.add_argument("--catalogue", default="data/catalogue.json")
    ap.add_argument("--report", default="scope/asset-prune.json")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    assets = pathlib.Path(args.assets_dir)
    clone = pathlib.Path(args.clone_dir)

    sources: list[pathlib.Path] = []
    sources += sorted((clone / "static" / "frozen").rglob("*.html.gz"))
    sources += sorted((clone / "static" / "fragments").rglob("*.html.gz"))
    for name in ("page-shell.html", "detail-template.html",
                 "search-template.json", "variant-map.json"):
        p = clone / "static" / name
        if p.exists():
            sources.append(p)
    # Served CSS and JS carry their own references, rewritten in place.
    sources += [p for p in assets.rglob("*") if p.suffix.lower() in
                (".css", ".js") and p.is_file()]

    reachable: set[tuple[str, str]] = set()

    # The catalogue's images are referenced by NOTHING on disk.
    #
    # `render_product` and the search tiles build their image URLs at request
    # time from the `product_images` table, so a scan of served files finds no
    # reference to them at all. Without this the dry run reported 16,066
    # unreachable `productlargeimages` -- every product photo the clone serves
    # from a template-rendered page -- and deleting them would have emptied the
    # product pages while every gate stayed green, because no *file* pointed at
    # them either.
    #
    # A reachability scan is only as good as its list of roots, and a root that
    # lives in a database is the one that gets forgotten.
    catalogue_path = pathlib.Path(args.catalogue)
    from_catalogue = 0
    if catalogue_path.exists():
        catalogue = json.loads(catalogue_path.read_text(encoding="utf-8"))
        for product in catalogue["products"]:
            for url in product.get("images") or []:
                split = urllib.parse.urlsplit(url)
                if not split.netloc:
                    continue
                rel = urllib.parse.unquote(split.path.lstrip("/"))
                reachable.add((split.netloc.lower(), rel))
                from_catalogue += 1
    else:
        print(f"REFUSING: no catalogue at {catalogue_path}; every product image "
              f"would look unreachable")
        return 1

    for path in sources:
        try:
            reachable |= referenced_in(read(path))
        except Exception as exc:  # noqa: BLE001
            print(f"  unreadable, skipped: {path} ({type(exc).__name__}: {exc})")

    on_disk: dict[tuple[str, str], pathlib.Path] = {}
    for path in assets.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(assets)
        host = rel.parts[0].lower()
        on_disk[(host, "/".join(rel.parts[1:]))] = path

    keep = {k for k in on_disk if k in reachable}
    drop = [p for k, p in on_disk.items() if k not in reachable]
    drop_bytes = sum(p.stat().st_size for p in drop)
    keep_bytes = sum(on_disk[k].stat().st_size for k in keep)

    by_dir: collections.Counter = collections.Counter()
    for p in drop:
        by_dir["/".join(p.relative_to(assets).parts[:2])] += 1

    report = {
        "schema_version": "monoprice.asset-prune.v1",
        "sources_scanned": len(sources),
        "references_found": len(reachable),
        "references_from_catalogue": from_catalogue,
        "files_on_disk": len(on_disk),
        "files_reachable": len(keep),
        "files_unreachable": len(drop),
        "bytes_reachable": keep_bytes,
        "bytes_unreachable": drop_bytes,
        "unreachable_by_directory": dict(by_dir.most_common(20)),
        "applied": False,
    }

    # The refusal. If the scan broke, everything looks unreachable.
    share = len(keep) / max(len(on_disk), 1)
    if share < 0.20:
        report["error"] = (f"only {share:.1%} of assets look reachable; that is "
                           f"a broken reference scan, not a tidy tree")
        pathlib.Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({k: v for k, v in report.items()
                          if k != "unreachable_by_directory"}, indent=2))
        print("\nREFUSING: the reachable set is implausibly small.")
        return 1

    if args.apply:
        for p in drop:
            p.unlink()
        # Leave no empty directories behind.
        for d in sorted((p for p in assets.rglob("*") if p.is_dir()),
                        key=lambda p: -len(p.parts)):
            if not any(d.iterdir()):
                d.rmdir()
        report["applied"] = True

    pathlib.Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.report).write_text(json.dumps(report, indent=2) + "\n",
                                         encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items()
                      if k != "unreachable_by_directory"}, indent=2))
    print(f"\n  reachable {len(keep):,} files / {keep_bytes/2**30:.2f} GB")
    print(f"  unreachable {len(drop):,} files / {drop_bytes/2**30:.2f} GB"
          f"{' -- DELETED' if args.apply else ' (dry run)'}")
    for d, n in by_dir.most_common(8):
        print(f"    {n:>6}  {d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
