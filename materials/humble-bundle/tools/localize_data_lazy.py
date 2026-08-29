"""Localize the `data-lazy` images the frozen-page builder never collected.

`build_frozen_pages.py` localizes `src`, `srcset`, `poster`, `background`,
`data-src`, `data-srcset` and `data-poster`, and treats `data-lazy-src` as
inert — but plain `data-lazy` appeared in neither list, so every URL held in
that attribute stayed pointed at the source's image CDN. The builder's list is
fixed; this closes the images already frozen, without regenerating 25 pages
that are otherwise correct.

Conventions are the site's own: content-addressed `<sha256><ext>` under
`clone/static/assets/`, and a provenance entry recording where each byte came
from. A response whose magic bytes are not an image is a failure, not a file.
"""

import hashlib
import html
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

WT = pathlib.Path("/private/tmp/claude-501/-Users-wentaoma-Desktop-websitebench-pipeline/"
                  "58984861-9d0e-42a7-9929-7f0ca633ca88/scratchpad/wt-humble/"
                  "materials/humble-bundle")
PAGES = WT / "clone/frontend/pages"
ASSETS = WT / "clone/static/assets"
PROVENANCE = WT / "clone/static/assets-provenance.json"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
MAGIC = [(b"\xff\xd8\xff", ".jpg"), (b"\x89PNG\r\n\x1a\n", ".png"),
         (b"GIF8", ".gif"), (b"RIFF", ".webp")]
ATTR = re.compile(r'data-lazy="(https?://[^"]+)"')


def suffix(body):
    for magic, ext in MAGIC:
        if body.startswith(magic):
            return ext
    if body[4:8] == b"ftyp" and body[8:12] in (b"avif", b"avis"):
        return ".avif"
    return None


def main():
    dry = "--dry-run" in sys.argv
    urls = {}
    for page in sorted(PAGES.glob("*.html")):
        for url in ATTR.findall(page.read_text(encoding="utf-8", errors="replace")):
            urls.setdefault(url, []).append(page.name)
    print(f"{len(urls)} unique data-lazy URLs across "
          f"{len({p for v in urls.values() for p in v})} pages")
    if dry:
        for u, pages in list(urls.items())[:5]:
            print(f"  {u[:90]}  <- {', '.join(sorted(set(pages)))}")
        return 0

    mapping, failed = {}, []
    for i, url in enumerate(sorted(urls), 1):
        time.sleep(0.4)  # the same politeness delay localize_seed_media.py uses
        try:
            # The attribute holds the URL HTML-escaped, so `&` is `&amp;`.
            # Fetching the escaped form asks the CDN for a query it does not
            # have; the markup keeps the escaped spelling and only the request
            # is unescaped.
            req = urllib.request.Request(html.unescape(url),
                                         headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read(2_000_000)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            failed.append((url, f"{type(exc).__name__}"))
            continue
        ext = suffix(body)
        if not ext:
            # An HTML error body is not an image. Discarding it is the point:
            # a file that is the wrong type renders as a broken image and looks
            # like the bug this is fixing.
            failed.append((url, "not an image"))
            continue
        digest = hashlib.sha256(body).hexdigest()
        dest = ASSETS / f"{digest}{ext}"
        if not dest.exists():
            dest.write_bytes(body)
        mapping[url] = f"/static/assets/{digest}{ext}"
        print(f"  {i:3d}/{len(urls)}  {len(body):>8}B  {url[-52:]}")

    touched = 0
    for page in sorted(PAGES.glob("*.html")):
        text = original = page.read_text(encoding="utf-8", errors="replace")
        for url, local in mapping.items():
            text = text.replace(f'data-lazy="{url}"', f'data-lazy="{local}"')
        if text != original:
            page.write_text(text, encoding="utf-8")
            touched += 1

    prov = {}
    if PROVENANCE.exists():
        try:
            prov = json.loads(PROVENANCE.read_text())
        except Exception:
            prov = {}
    entries = prov.setdefault("assets", {}) if isinstance(prov, dict) else {}
    for url, local in mapping.items():
        entries[local] = {
            "source_url": url,
            "collected_by": "tools/localize_data_lazy.py",
            "reason": ("build_frozen_pages.py did not list `data-lazy` among the "
                       "attributes whose URLs it localizes; the list is fixed and "
                       "these already-frozen references were closed separately."),
        }
    if isinstance(prov, dict):
        PROVENANCE.write_text(json.dumps(prov, indent=1) + "\n", encoding="utf-8")

    print(f"\nlocalized {len(mapping)}/{len(urls)}, rewrote {touched} pages, "
          f"{len(failed)} failed")
    for url, why in failed[:8]:
        print(f"  FAIL {why:<14} {url[:80]}")
    return 0 if not failed else 1


sys.exit(main())
