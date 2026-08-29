#!/usr/bin/env python3
"""Build the mobile fixup manifest for the humble-bundle clone.

The frozen pages are derived from the desktop (1440x900) DOM captures. The
source site's JS swaps in a few mobile-specific pieces at <=767px that the
desktop DOM never materialized (lazy images that only load at mobile widths,
slick carousels re-laid-out with mobile inline styles). This tool derives
byte-frozen replacement fragments from the already-captured *mobile* DOM
evidence and emits ``clone/static/site/mobile-fixups.json``, which the
``hb-app.js`` mobile-fixup module applies at narrow viewports only.

Reuses the exact rewriting/stripping machinery of ``build_frozen_pages.py``
(asset localization to /static/assets/<sha><ext>, script/iframe/tracker
stripping, csrf neutralization) by importing it. Assets already localized by
the main build are reused; any newly needed blob is copied with the same
sha-name scheme and appended to ``clone/static/assets-provenance.json``.
Mobile-only asset URLs absent from the capture url-map are recorded as
missing (never fetched).

Deterministic and re-runnable; no network, no browser.

Usage
    python3 materials/humble-bundle/tools/build_mobile_fixups.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_frozen_pages as bfp  # noqa: E402

SITE_ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = bfp.DEFAULT_RUN
OUT_PATH = SITE_ROOT / "clone" / "static" / "site" / "mobile-fixups.json"

# The capture-run Sofia Pro regular face renders a 22px line box at 16px
# (ascent 17px + descent 5px) while the audit-grade headless render computes
# 21px (descent 4px) from the same woff2. Re-declaring the face with explicit
# metric overrides pins the captured metrics so every `line-height: normal`
# text block matches the mobile capture. Src list mirrors the shipped
# stylesheet's face byte-for-byte; only the override descriptors are added.
SOFIA_METRICS_FIX = (
    "@font-face{font-family:'Sofia Pro';"
    'src:url("/static/assets/82828761122ff2e0c162bbc213aaf6ff9c26c056505209984a67d1354d63c4f9.woff2") format("woff2"),'
    'url("/static/assets/f855294d672d6d751f4f6c27d47a32ef883c07a76dd1a2e0043f4ba7a9eb8f4b.woff") format("woff"),'
    'url("/static/assets/6162a3a31aed0177dc9079bc4aeddf7f520186d96dc7ab7768c0b1bf3e92f8eb.ttf") format("truetype"),'
    'url("/static/assets/47ff94ca77428ec10a4bc9e447d4b4c2b0eaf44712d262fc83b8fc132f65ed6d.ttf") format("opentype");'
    "font-weight:normal;font-style:normal;"
    "ascent-override:106.25%;descent-override:31.25%;line-gap-override:0%}"
)
SOFIA_FIX_WHY = (
    "capture-render Sofia Pro regular metrics (22px normal line box @16px) vs "
    "17px+4px in the frozen render; override realigns every normal-line-height "
    "text block at mobile"
)

# Fragment specs. ``needle``/``after`` locate the element inside the mobile
# dom.html: the element whose start tag contains ``needle`` at the first
# occurrence after index of ``after`` (0 when omitted).
FRAGMENTS = [
    {
        "route": "/",
        "cell": "static/home/mobile",
        "tag": "img",
        "needle": 'class="spn-mobile-foreground js-lazyload lazy-loaded"',
        "after": "signup?goto=%2Fmembership%2Fcheckout",
        "anchor_selector": 'a.spn-bordered-box[href*="membership"] img.spn-mobile-foreground',
        "position": "replace",
        "why": "mobile-only Humble Choice game-art collage: lazy image only loads at <=767px, so the desktop DOM carries data-src without src",
    },
    {
        "route": "/",
        "cell": "static/home/mobile",
        "tag": "img",
        "needle": 'class="spn-mobile-foreground js-lazyload lazy-loaded"',
        "after": "2k-megahits-2026-bundle?hmb_source=humble_home&amp;hmb_medium=takeover",
        "anchor_selector": 'a.spn-bordered-box[href*="2k-megahits"] img.spn-mobile-foreground',
        "position": "replace",
        "why": "mobile-only 2K takeover collage image: same mobile-width lazy-load gap as the Humble Choice takeover",
    },
    {
        "route": "/store",
        "cell": "static/store/mobile",
        "tag": "div",
        "needle": (
            'class="entities-list js-entities-list no-style-list full js-full '
            'slick-initialized slick-slider"'
        ),
        "after": "01featured_carousel_anchor",
        "anchor_selector": "li.entity-list.carousel-large .entities-list.slick-slider",
        "position": "replace",
        "why": "featured hero carousel: desktop slick inline state (468px slides, desktop offsets, dot controls) renders broken at 390px; mobile capture carries the mobile slick layout",
    },
    {
        "route": "/store",
        "cell": "static/store/mobile",
        "tag": "div",
        "needle": (
            'class="entities-list js-entities-list no-style-list full js-full '
            'slick-initialized slick-slider"'
        ),
        "after": "carousel-mini",
        "anchor_selector": "li.entity-list.carousel-mini .entities-list.slick-slider",
        "position": "replace",
        "why": "second store carousel: desktop slick inline state offsets the visible slide ~20px down at 390px; mobile capture carries the mobile slick layout",
    },
]

# Style entries appended per route. The Sofia metrics fix goes on the routes
# whose visible text relies on `line-height: normal`; the two bundle pages set
# explicit line-heights on their copy (the override would only jitter their
# strut baselines), so they get the theia fix below instead.
SOFIA_FIX_ROUTES = [
    "/",
    "/store",
    "/books",
    "/software",
    "/login",
    "/games",
    "/bundles",
]
ROUTES = SOFIA_FIX_ROUTES + [
    "/games/yes-chef-cooking-bundle",
    "/games/2k-megahits-2026-bundle",
]

# The desktop-only theia-sticky-sidebar script stamps
# `style="padding-top: 1px; padding-bottom: 1px; ..."` onto .theiaStickySidebar
# in the desktop DOM; the mobile capture carries the bare element. That 1px
# shifts the whole bundle column down at mobile.
THEIA_PADDING_FIX = {
    "action": "style",
    "css": ".theiaStickySidebar{padding-top:0!important;padding-bottom:0!important}",
    "why": "desktop-only theia-sticky-sidebar JS bakes 1px paddings into the desktop DOM; the mobile capture has none, so the frozen padding shifts the bundle column down 1px at mobile",
}
EXTRA_STYLE_ENTRIES: dict[str, list[dict]] = {
    "/games/yes-chef-cooking-bundle": [THEIA_PADDING_FIX],
    "/games/2k-megahits-2026-bundle": [THEIA_PADDING_FIX],
}

# Desktop-only elements that must not show at mobile widths.
HIDE_ENTRIES: dict[str, list[dict]] = {
    "/store": [
        {
            "action": "hide",
            "selector": "li.entity-list ul.slick-dots",
            "why": "desktop-only slick dot bars under the store carousels; the mobile capture renders no dots and their height shifts the next carousel down",
        },
    ],
}


class FragmentBuilder(bfp.PageBuilder):
    """PageBuilder variant that freezes a fragment instead of a full page.

    JSON state scripts inside fragments are stripped like plain inline
    scripts (no state-blob extraction side effects).
    """

    def decide_removal(self, node, text):
        if node.tag == "script":
            if self.tracker_keyword(node):
                return "script_tracker"
            return "script_src" if "src" in node.attrs else "script_inline"
        return super().decide_removal(node, text)

    def build_fragment(self, fragment_text: str) -> str:
        nodes = bfp.parse_nodes(fragment_text)
        edits: list[tuple[int, int, str]] = []
        for node in nodes:
            if node.parent is not None and (node.parent.removed or node.parent.in_removed):
                node.in_removed = True
                continue
            category = self.decide_removal(node, fragment_text)
            if category:
                node.removed = True
                self.removals[category] += 1
                edits.append((node.start, node.end, ""))
        for node in nodes:
            if node.removed or node.in_removed:
                continue
            new_raw = self.rewrite_start_tag(node)
            if new_raw is not None:
                edits.append((node.start, node.tag_end, new_raw))
            if node.tag == "style" and node.end_start > node.tag_end:
                css_text = fragment_text[node.tag_end:node.end_start]
                new_css, n = self.rewrite_inline_css(
                    css_text, f"{self.checkpoint}:style-element")
                if n:
                    edits.append((node.tag_end, node.end_start, new_css))
        edits.sort(key=lambda e: (e[0], e[1]))
        for (s1, e1, _), (s2, _e2, _r) in zip(edits, edits[1:]):
            if e1 > s2:
                raise AssertionError(
                    f"overlapping edits in {self.checkpoint}: ({s1},{e1}) vs ({s2},..)")
        out = fragment_text
        for start, end, replacement in sorted(edits, key=lambda e: e[0], reverse=True):
            out = out[:start] + replacement + out[end:]
        return out


def extract_element(text: str, needle: str, tag: str, after: str) -> str:
    base = 0
    if after:
        base = text.find(after)
        if base == -1:
            raise SystemExit(f"marker not found: {after!r}")
    idx = text.find(needle, base)
    if idx == -1:
        raise SystemExit(f"needle not found: {needle!r}")
    nodes = bfp.parse_nodes(text)
    best = None
    for node in nodes:
        if node.tag == tag and node.start <= idx < node.tag_end:
            if best is None or node.start > best.start:
                best = node
    if best is None:
        raise SystemExit(f"no <{tag}> start tag containing needle at {idx}")
    return text[best.start:best.end]


def validate_fragment(html: str, label: str) -> None:
    forbidden, _nav, _inert, _text = bfp.validate_page(html, label)
    # validate_page flags every script element; fragments must carry none at all
    if forbidden:
        raise SystemExit(f"fragment {label} kept forbidden refs: {forbidden[:4]}")


def main() -> int:
    url_map = json.loads((RUN_DIR / "assets" / "url-map.json").read_text(encoding="utf-8"))
    ctx = bfp.BuildContext(RUN_DIR, url_map)
    existing_assets = {
        p.name for p in bfp.ASSET_DIR.iterdir() if p.is_file()
    } if bfp.ASSET_DIR.exists() else set()

    fixups: dict[str, list[dict]] = {route: [] for route in ROUTES}
    fragment_report = []

    for spec in FRAGMENTS:
        cell_dir = RUN_DIR / spec["cell"]
        text = (cell_dir / "dom.html").read_bytes().decode("utf-8", "surrogateescape")
        raw = extract_element(text, spec["needle"], spec["tag"], spec.get("after", ""))
        checkpoint = f"mobile-fixup:{spec['route']}"
        builder = FragmentBuilder(ctx, checkpoint, spec["route"], spec["cell"])
        frozen = builder.build_fragment(raw)
        validate_fragment(frozen, checkpoint)
        fixups[spec["route"]].append({
            "anchor_selector": spec["anchor_selector"],
            "position": spec["position"],
            "html": frozen,
            "why": spec["why"],
        })
        fragment_report.append(
            (spec["route"], spec["anchor_selector"], len(raw), len(frozen),
             dict(builder.removals)))

    for route in ROUTES:
        if route in SOFIA_FIX_ROUTES:
            fixups[route].append({
                "action": "style",
                "css": SOFIA_METRICS_FIX,
                "why": SOFIA_FIX_WHY,
            })
        for entry in EXTRA_STYLE_ENTRIES.get(route, []):
            fixups[route].append(entry)
        for entry in HIDE_ENTRIES.get(route, []):
            fixups[route].append(entry)

    OUT_PATH.write_text(
        json.dumps(fixups, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")

    # merge any newly localized assets into the shipped provenance manifest
    prov_path = bfp.PROVENANCE_PATH
    provenance = json.loads(prov_path.read_text(encoding="utf-8"))
    new_assets = []
    for local, info in sorted(ctx.provenance.items()):
        name = local[len(bfp.ASSET_URL_PREFIX):]
        if local not in provenance:
            provenance[local] = info
        if name not in existing_assets:
            new_assets.append(local)
    prov_path.write_text(
        json.dumps(provenance, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")

    print(f"routes: {len(fixups)}  fragments: {len(fragment_report)}")
    for route, sel, raw_len, frozen_len, removals in fragment_report:
        print(f"  {route} :: {sel} raw={raw_len} frozen={frozen_len} removals={removals}")
    print(f"assets referenced this run: {len(ctx.provenance)} "
          f"(newly copied from blobs: {len(new_assets)})")
    for a in new_assets:
        print(f"  new: {a}")
    if ctx.missing:
        print(f"missing from blobs ({len(ctx.missing)}):")
        for url, rec in sorted(ctx.missing.items()):
            print(f"  {url} -> {rec['path']}")
    else:
        print("missing from blobs: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
