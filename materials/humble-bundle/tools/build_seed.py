#!/usr/bin/env python3
"""Normalize the Humble Bundle api-harvest into the offline-clone backend seed.

Deterministic, re-runnable, stdlib-only. Reads the captured JSON payloads
under source-current/<capture>/api-harvest/ plus the frozen header-search
suggest DOM under <capture>/interactive/ and writes
clone/backend/seed_data.json. Running it twice produces byte-identical
output; nothing is read from the clock, the environment or the network.

Normalization contract (documented in scope/data-contract-notes.md):
  * currency is CAD; every money value becomes an integer number of cents
    (minor units, ROUND_HALF_UP for the few sub-cent msrp figures).
  * fields absent from the harvest are omitted, never null-padded.
  * captured order is authoritative: search/category ranks, bundle
    tier_order, tier item order, preset price order, landing mosaic
    order and the header-search suggest panel rows (``suggest_orders``,
    parsed from the frozen suggest DOM) are preserved exactly as
    harvested/captured.
  * no values are invented; every emitted value is copied or arithmetically
    derived (cents, discount_pct, callout split) from the harvest.
  * media URLs are localized: every image reference becomes
    {"local": "/static/assets/<sha256><ext>", "source_url": "<captured url>"}
    resolved through <capture>/assets/url-map.json (blobs fetched by
    tools/localize_seed_media.py). bundles_listing tile_image alone stays a
    plain string -- catalog_db stores it in a TEXT column -- and carries the
    local path (assets-provenance.json keeps its source URL).

Usage:
  python materials/humble-bundle/tools/build_seed.py [--harvest-dir DIR]
      [--out FILE] [--check-only]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from html import unescape
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

SITE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HARVEST = (
    SITE_ROOT / "source-current" / "2026-08-20.humble-bundle-r1" / "api-harvest"
)
DEFAULT_OUT = SITE_ROOT / "clone" / "backend" / "seed_data.json"

CURRENCY = "CAD"
SCHEMA = "humble-bundle.seed.v1"

# Listing files in capture order; label -> ordered page files.
LISTINGS = {
    "portal": ["search-portal-p0.json", "search-portal-p1.json"],
    "adventure-bestselling": [
        "category-adventure-p0.json",
        "category-adventure-p1.json",
    ],
}
# product-detail-5 is a suggest-panel follow-up lookup (Spellrune): a
# normal seed product that appears in NO captured listing, so it gets
# no search_orders rank (see scope/data-contract-notes.md appendix).
LOOKUP_FILES = [f"product-detail-{i}.json" for i in (1, 2, 3, 4, 5)]
# Every harvested bundle page blob; sorted glob keeps bundles[] ordered
# alphabetically by slug (filenames are bundle-<slug>.json).
BUNDLE_GLOB = "bundle-*.json"
LANDING_FILE = "bundles-landing.json"
ENDPOINTS_FILE = "observed-endpoints.json"
# Frozen header-search suggest captures: normalized typed query -> DOM
# snapshot (relative to the capture root, api-harvest's parent). The
# .site-search-results panel rows become seed suggest_orders[<query>].
SUGGEST_CAPTURES = {
    "portal": Path("interactive") / "home-search-suggest" / "dom.html",
}

# Localized-asset index: <capture>/assets/url-map.json (sibling of the
# api-harvest dir) maps every captured URL to its content-addressed blob;
# seed media is rewritten to the mirrored copies in clone/static/assets/.
ASSETS_URL_MAP_RELATIVE = Path("assets") / "url-map.json"
STATIC_ASSET_PREFIX = "/static/assets/"
EXT_BY_CONTENT_TYPE = {
    "image/avif": ".avif",
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/svg+xml": ".svg",
    "image/vnd.microsoft.icon": ".ico",
    "image/webp": ".webp",
}

# Facet enums fixed by the data contract (store UI facets). The harvested
# request itself used sort=bestselling and filter=all; see
# scope/data-contract-notes.md for provenance.
SORT_ENUM = ["discount", "alphabetical", "newest", "bestselling"]
FILTER_ENUM = ["onsale", "new"]

# Cross-check expectations from the task contract. The harvest is the
# authority: a mismatch is reported loudly but the harvest values are kept.
EXPECTED_TIERS = {
    "yes-chef-cooking-bundle": {"thresholds": [971, 1803, 2219], "item_counts": [7, 13, 16]},
    "2k-megahits-2026-bundle": {"thresholds": [2116], "item_counts": [15]},
}

CALLOUT_STEAM_RE = re.compile(
    r"^<span>(\d+)% Positive on Steam</span>(?:<br\s*/?>)*\s*(.*)$", re.S
)

# Product fields copied verbatim when present (rating block kept "as found").
PRODUCT_VERBATIM = [
    "user_rating",
    "esrb_rating",
    "pegi_rating",
    "rating_details",
    "minimum_age",
    "rating_for_current_region",
]
PRODUCT_MEDIA_FIELDS = [
    "standard_carousel_image",
    "large_capsule",
    "featured_image_recommendation",
    "icon",
    "xray_traits_thumbnail",
    "mini_carousel_image",
]


class SeedError(RuntimeError):
    """Structural problem that makes the seed untrustworthy."""


class Report:
    """Collects counts, cross-check results and data-quality flags."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.flags: list[str] = []
        self.subcent: list[str] = []
        self.mismatches: list[str] = []

    def line(self, text: str) -> None:
        self.lines.append(text)

    def flag(self, text: str) -> None:
        self.flags.append(text)


REPORT = Report()


def load(path: Path):
    """Load JSON with exact decimal amounts (floats become Decimal)."""
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh, parse_float=Decimal)


def money_minor(value, *, where: str) -> int:
    """{'currency': 'CAD', 'amount': X} -> integer cents (ROUND_HALF_UP)."""
    if not isinstance(value, dict) or set(value) != {"currency", "amount"}:
        raise SeedError(f"{where}: not a money object: {value!r}")
    if value["currency"] != CURRENCY:
        raise SeedError(f"{where}: expected {CURRENCY}, got {value['currency']!r}")
    amount = value["amount"]
    if isinstance(amount, int):
        amount = Decimal(amount)
    if not isinstance(amount, Decimal):
        raise SeedError(f"{where}: non-numeric amount {amount!r}")
    cents = amount * 100
    if cents != cents.to_integral_value():
        rounded = int(cents.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        note = f"{where}: {amount} -> {rounded}"
        if note not in REPORT.subcent:  # cumulative tiers repeat items
            REPORT.subcent.append(note)
    return int(cents.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def discount_pct(current_minor: int, full_minor: int) -> int:
    """Whole-percent discount, ROUND_HALF_UP, from minor units."""
    if full_minor <= 0 or current_minor >= full_minor:
        return 0
    frac = Decimal(full_minor - current_minor) * 100 / Decimal(full_minor)
    return int(frac.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def plain(value):
    """Convert surviving Decimals into JSON-safe numbers, recursively.

    Integral decimals become int, everything else float; used only for
    pass-through structures whose numbers are fractions/percentages,
    never for money (money always goes through money_minor)."""
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    return value


def strip_type_suffixes(value):
    """Drop Humble's '|decimal'/'|money'/'|datetime' key-name suffixes."""
    if isinstance(value, dict):
        return {k.split("|", 1)[0]: strip_type_suffixes(v) for k, v in value.items()}
    if isinstance(value, list):
        return [strip_type_suffixes(v) for v in value]
    return value


class AssetIndex:
    """url -> localized media entry, backed by the capture's url-map."""

    def __init__(self, harvest: Path) -> None:
        self.index: dict[str, str] = {}
        self.hits = 0
        self.misses: list[str] = []
        path = harvest.parent / ASSETS_URL_MAP_RELATIVE
        if path.exists():
            with path.open("r", encoding="utf-8") as fh:
                url_map = json.load(fh)
            for url, meta in url_map.items():
                ext = EXT_BY_CONTENT_TYPE.get(meta.get("content_type", ""))
                if ext:
                    self.index[url] = f"{STATIC_ASSET_PREFIX}{meta['sha256']}{ext}"
        else:
            REPORT.flag(f"asset url-map missing ({path}); seed media stays remote")

    def entry(self, url: str) -> dict:
        """One media URL -> {"local": "/static/assets/..", "source_url": url}."""
        local = self.index.get(url)
        if local is None:
            if url not in self.misses:
                self.misses.append(url)
            return {"source_url": url}
        self.hits += 1
        return {"local": local, "source_url": url}

    def local_or_url(self, url: str) -> str:
        """Plain-string variant for scalar columns (listing tile_image)."""
        local = self.index.get(url)
        if local is None:
            if url not in self.misses:
                self.misses.append(url)
            return url
        self.hits += 1
        return local


# ---------------------------------------------------------------- products


def collect_ranks(harvest: Path) -> dict[str, dict[str, int]]:
    """slug -> {listing-label: 1-based rank in captured order}."""
    ranks: dict[str, dict[str, int]] = {}
    for label, files in LISTINGS.items():
        rank = 0
        seen: set[str] = set()
        for page_number, name in enumerate(files):
            page = load(harvest / name)
            if page.get("page_index") != page_number:
                raise SeedError(f"{name}: page_index {page.get('page_index')} != {page_number}")
            for result in page["results"]:
                slug = result["human_url"]
                if slug in seen:
                    raise SeedError(f"{name}: duplicate slug {slug} in listing {label}")
                seen.add(slug)
                rank += 1
                ranks.setdefault(slug, {})[label] = rank
        REPORT.line(f"listing '{label}': {rank} captured ranks")
    return ranks


def norm_people(entries, kind: str) -> list[dict]:
    """[{'developer-name': .., 'developer-url': ..}] -> [{'name', 'url'?}]."""
    out = []
    for person in entries:
        name = person.get(f"{kind}-name")
        if name is None:
            raise SeedError(f"{kind} entry without name: {person!r}")
        item = {"name": name}
        url = person.get(f"{kind}-url")
        if url:
            item["url"] = url
        out.append(item)
    return out


def product_media(entry, assets: AssetIndex) -> dict:
    media: dict = {}
    for field in PRODUCT_MEDIA_FIELDS:
        value = entry.get(field)
        if value:
            media[field] = assets.entry(value)
    carousel = entry.get("carousel_content") or {}
    if carousel.get("screenshot"):
        media["screenshots"] = [assets.entry(url) for url in carousel["screenshot"]]
    if carousel.get("thumbnails"):
        media["thumbnails"] = [assets.entry(url) for url in carousel["thumbnails"]]
    if carousel.get("youtube-link"):
        media["youtube"] = list(carousel["youtube-link"])
    return media


def norm_product(entry, ranks, assets: AssetIndex) -> dict:
    slug = entry["human_url"]
    current_minor = money_minor(entry["current_price"], where=f"product {slug} current_price")
    full_minor = money_minor(entry["full_price"], where=f"product {slug} full_price")
    product = {
        "slug": slug,
        "machine_name": entry["machine_name"],
        "human_name": entry["human_name"],
        "current_price_minor": current_minor,
        "full_price_minor": full_minor,
        "discount_pct": discount_pct(current_minor, full_minor),
        "platforms": list(entry["platforms"]),
        # Humble's store DRM facet is keyed by delivery method; icon_dict
        # holds the same keys with per-platform availability. Verified
        # identical sets across the harvest (see data-contract-notes).
        "drm": list(entry["icon_dict"].keys()),
        "delivery_methods": list(entry["delivery_methods"]),
        "genres": list(entry["genre_identifiers"]),
    }
    # cta_badge grounds the "new" search filter and store tile badges;
    # the lookup payload null-pads it (62/69 null) so only real badges
    # ("new" | "preorder" | "earlyaccess") are seeded.
    if entry.get("cta_badge") is not None:
        product["cta_badge"] = entry["cta_badge"]
    if "developers" in entry:
        product["developers"] = norm_people(entry["developers"], "developer")
    if "publishers" in entry:
        product["publishers"] = norm_people(entry["publishers"], "publisher")
    for field in PRODUCT_VERBATIM:
        if field in entry:
            product[field] = plain(entry[field])
    product["description"] = entry["description"]
    product["system_requirements"] = entry["system_requirements"]
    product["media"] = product_media(entry, assets)
    product["search_orders"] = ranks.get(slug, {})
    return product


def build_products(harvest: Path, assets: AssetIndex):
    ranks = collect_ranks(harvest)
    entries = []
    for name in LOOKUP_FILES:
        entries.extend(load(harvest / name)["result"])
    by_slug: dict[str, dict] = {}
    duplicates: list[str] = []
    for entry in entries:
        slug = entry["human_url"]
        if slug in by_slug:
            # A later lookup capture may re-present an already-harvested
            # product (product-detail-5 re-looked-up Spellrune during the
            # suggest-panel session; detail-1 already carried it). Equal
            # payloads (Decimal-aware ==, so 0.0 == 0) dedupe to the
            # first-seen entry; a disagreeing duplicate stays fatal.
            if entry != by_slug[slug]:
                raise SeedError(f"conflicting duplicate lookup slug {slug}")
            duplicates.append(slug)
            continue
        by_slug[slug] = entry
    if duplicates:
        REPORT.line(
            "lookup duplicates verified equal, deduped (first-seen kept): "
            + ", ".join(sorted(duplicates))
        )
    missing = sorted(set(ranks) - set(by_slug))
    if missing:
        raise SeedError(f"listing slugs missing from lookup: {missing}")
    extra = sorted(set(by_slug) - set(ranks))
    if extra:
        REPORT.flag(f"lookup slugs not present in any captured listing: {extra}")
    products = [
        norm_product(by_slug[slug], ranks, assets) for slug in sorted(by_slug)
    ]
    platforms = sorted({p for prod in products for p in prod["platforms"]})
    drm = sorted({d for prod in products for d in prod["delivery_methods"]})
    return products, platforms, drm


# ----------------------------------------------------------------- bundles


def norm_tier_item(item, *, bundle_slug: str, assets: AssetIndex) -> dict:
    machine_name = item["machine_name"]
    where = f"bundle {bundle_slug} item {machine_name}"
    out = {"machine_name": machine_name, "human_name": item["human_name"]}
    if item.get("msrp_price|money") is not None:
        out["msrp_minor"] = money_minor(item["msrp_price|money"], where=f"{where} msrp_price")
    callout = item.get("callout")
    if callout:
        match = CALLOUT_STEAM_RE.match(callout)
        if match:
            out["steam_positive_pct"] = int(match.group(1))
            if match.group(2):
                out["one_liner"] = match.group(2)
        else:
            out["one_liner"] = callout
    media: dict = {}
    resolved = (item.get("resolved_paths") or {}).get("featured_image")
    if resolved:
        media["featured_image"] = assets.entry(resolved)
    if item.get("featured_image"):
        media["featured_image_path"] = item["featured_image"]
    if item.get("youtube_link"):
        media["youtube"] = item["youtube_link"]
    if media:
        out["media"] = media
    return out


def norm_charity(bundle_data, *, bundle_slug: str) -> dict:
    charity_items = bundle_data["charity_data"]["charity_items"]
    if len(charity_items) != 1:
        raise SeedError(f"bundle {bundle_slug}: expected exactly one charity, got {sorted(charity_items)}")
    machine_name, entry = next(iter(charity_items.items()))
    info = entry["ppgf_info"]
    charity = {
        "machine_name": machine_name,
        "name": info["human_name"],
        "id": info["charity_id"],
    }
    if info.get("description"):
        charity["blurb"] = info["description"]
    return charity


def norm_bundle(payload, assets: AssetIndex) -> dict:
    bundle_data = payload["bundleData"]
    basic = bundle_data["basic_data"]
    slug = bundle_data["page_url"].rstrip("/").split("/")[-1]
    if basic["currency"] != CURRENCY:
        raise SeedError(f"bundle {slug}: basic_data.currency {basic['currency']!r}")

    tiers = []
    initial_minor = None
    for tier_id in bundle_data["tier_order"]:
        display = bundle_data["tier_display_data"][tier_id]
        pricing = bundle_data["tier_pricing_data"][tier_id]
        names = list(display["tier_item_machine_names"])
        threshold_minor = money_minor(
            pricing["price|money"], where=f"bundle {slug} tier {tier_id} price"
        )
        if pricing.get("is_initial_tier"):
            initial_minor = threshold_minor
        items = [
            norm_tier_item(
                bundle_data["tier_item_data"][name],
                bundle_slug=slug,
                assets=assets,
            )
            for name in names
        ]
        tier = {
            "tier_id": tier_id,
            "threshold_minor": threshold_minor,
            "item_count": len(names),
        }
        if display.get("header"):
            tier["header"] = display["header"]
        tier["items"] = items
        tiers.append(tier)
    if initial_minor is None:
        raise SeedError(f"bundle {slug}: no is_initial_tier tier found")

    preset_minor = []
    suggested_minor = None
    for index, preset in enumerate(bundle_data["preset_prices"]):
        minor = money_minor(preset["price|money"], where=f"bundle {slug} preset_prices[{index}]")
        preset_minor.append(minor)
        if preset.get("suggested"):
            if suggested_minor is not None:
                REPORT.flag(f"bundle {slug}: multiple suggested preset prices")
            suggested_minor = minor

    tpkd = basic.get("tpkd_cutoff_price|money")
    if tpkd is not None:
        tpkd_minor = money_minor(tpkd, where=f"bundle {slug} tpkd_cutoff_price")
        if tpkd_minor != initial_minor:
            REPORT.flag(
                f"bundle {slug}: tpkd_cutoff {tpkd_minor} != initial tier {initial_minor}"
            )

    stats = bundle_data["statistics_data"]
    purchases = stats["num_purchases|decimal"]
    if purchases != purchases.to_integral_value():
        REPORT.flag(f"bundle {slug}: non-integral num_purchases {purchases}")
    bundle = {
        "slug": slug,
        "machine_name": bundle_data["machine_name"],
        "name": basic["human_name"],
        "type": basic["media_type"],
        "end_at": basic["end_time|datetime"],
        "msrp_minor": money_minor(basic["msrp|money"], where=f"bundle {slug} msrp"),
        "floor_minor": initial_minor,
        "preset_prices_minor": preset_minor,
    }
    if suggested_minor is not None:
        bundle["suggested_price_minor"] = suggested_minor
    bundle["tier_order"] = list(bundle_data["tier_order"])
    bundle["tiers"] = tiers
    bundle["charity"] = norm_charity(bundle_data, bundle_slug=slug)
    bundle["splits"] = plain(strip_type_suffixes(bundle_data["splits"]))
    bundle["sold_count"] = int(purchases)
    bundle["charity_raised_minor"] = money_minor(
        stats["total_charity_raised|money"], where=f"bundle {slug} total_charity_raised"
    )
    bundle["harvested_at"] = bundle_data["at_time|datetime"]
    return bundle


def cross_check_bundle(bundle: dict) -> None:
    expected = EXPECTED_TIERS.get(bundle["slug"])
    if expected is None:
        return
    # Expectations are expressed ascending; tier_order is captured
    # display order (highest tier first on multi-tier bundles).
    got = sorted(
        (tier["threshold_minor"], tier["item_count"]) for tier in bundle["tiers"]
    )
    got_thresholds = [pair[0] for pair in got]
    got_counts = [pair[1] for pair in got]
    if got_thresholds == expected["thresholds"] and got_counts == expected["item_counts"]:
        REPORT.line(
            f"cross-check {bundle['slug']}: PASS thresholds={got_thresholds} item_counts={got_counts}"
        )
    else:
        REPORT.mismatches.append(
            f"cross-check {bundle['slug']}: HARVEST DISAGREES with expectation — "
            f"harvest thresholds={got_thresholds} item_counts={got_counts}, "
            f"expected thresholds={expected['thresholds']} item_counts={expected['item_counts']} "
            "(harvest kept as authority)"
        )


# ---------------------------------------------------------- bundles listing


def build_bundles_listing(harvest: Path, assets: AssetIndex) -> dict:
    landing = load(harvest / LANDING_FILE)["data"]
    listing: dict[str, list] = {}
    for category, section in landing.items():  # captured key order
        mosaics = section["mosaic"]
        if len(mosaics) != 1:
            raise SeedError(f"landing {category}: expected one mosaic, got {len(mosaics)}")
        rows = []
        for product in mosaics[0]["products"]:
            rows.append(
                {
                    "slug": product["product_url"].rstrip("/").split("/")[-1],
                    "machine_name": product["machine_name"],
                    "name": product["tile_name"],
                    "type": product["tile_stamp"],
                    "end_at": product["end_date|datetime"],
                    "highlights": list(product["highlights"]),
                    # tile_image stays a plain string: catalog_db binds it
                    # into a TEXT column (hb_bundles_listing.tile_image), so
                    # the localized form is the bare /static/assets/ path
                    # (assets-provenance.json keeps the source URL).
                    "tile_image": assets.local_or_url(product["tile_image"]),
                }
            )
        listing[category] = rows
        stamps = sorted({row["type"] for row in rows})
        if stamps != [category]:
            REPORT.flag(f"landing {category}: tile_stamp values {stamps} (kept as found)")
    return listing



# ------------------------------------------------------------ suggest panel

SUGGEST_PANEL_RE = re.compile(r'<div class="site-search-results js-results[^"]*">')
SUGGEST_ROW_SPLIT = '<div class="product-search-result">'
SUGGEST_DIV_RE = re.compile(r"<div\b|</div>")
SUGGEST_ANCHOR_RE = re.compile(r'<a href="([^"]+)" class="product-details')
SUGGEST_IMG_RE = re.compile(r'<img class="product-image([^"]*)" src="([^"]+)"')
SUGGEST_TITLE_RE = re.compile(r'<span class="product-title">(.*?)</span>', re.S)
SUGGEST_DESC_RE = re.compile(r'<div class="product-description">(.*?)</div>', re.S)
SUGGEST_PLATFORMS_RE = re.compile(
    r'<div class="product-platform-delivery">(.*?)</div>', re.S
)
SUGGEST_ICON_RE = re.compile(r'<i class="hb hb-([a-z0-9-]+)"')
SUGGEST_CTA_RE = re.compile(r'<span class="cta-text ([a-z-]+)">')
SUGGEST_DISCOUNT_RE = re.compile(r'<span class="product-discount-amount">-(\d+)%')
SUGGEST_ACTION_RE = re.compile(
    r'<span class="product-action-text[^"]*">\s*(.*?)\s*</span>', re.S
)


def extract_suggest_panel(html: str, *, where: str) -> str:
    """First balanced ``.site-search-results.js-results`` div in the DOM."""
    match = SUGGEST_PANEL_RE.search(html)
    if match is None:
        raise SeedError(f"{where}: no .site-search-results panel found")
    depth = 0
    for tag in SUGGEST_DIV_RE.finditer(html, match.start()):
        depth += 1 if tag.group(0) == "<div" else -1
        if depth == 0:
            return html[match.start() : tag.end()]
    raise SeedError(f"{where}: unbalanced .site-search-results panel")


def parse_suggest_row(chunk: str, *, where: str, assets: AssetIndex) -> dict:
    """One captured ``.product-search-result`` block -> pinned suggest row.

    Fixed keys: kind ("bundle" when the image carries the bundle-product
    class, else "product"), href (captured link path with any ?query — e.g.
    ?hmb_source=search_bar — stripped), name, platform_icons (hb-<token>
    icon classes in captured order, delivery first), delivery_separator,
    discount_pct (int | None), exactly one of price_display ("CA$x.xx") /
    action_text ("View"), and img (localized media entry). Optional keys
    copied only when captured: description, cta_badge.
    """
    anchor = SUGGEST_ANCHOR_RE.search(chunk)
    image = SUGGEST_IMG_RE.search(chunk)
    title = SUGGEST_TITLE_RE.search(chunk)
    action = SUGGEST_ACTION_RE.search(chunk)
    if anchor is None or image is None or title is None or action is None:
        raise SeedError(f"{where}: row missing anchor/image/title/action")
    row: dict = {
        "kind": "bundle" if "bundle-product" in image.group(1) else "product",
        "href": unescape(anchor.group(1)).split("?", 1)[0],
        "name": unescape(title.group(1)).strip(),
    }
    description = SUGGEST_DESC_RE.search(chunk)
    if description:
        row["description"] = unescape(description.group(1)).strip()
    icons: list[str] = []
    separator = False
    platforms = SUGGEST_PLATFORMS_RE.search(chunk)
    if platforms:
        block = platforms.group(1)
        icons = SUGGEST_ICON_RE.findall(block)
        separator = 'class="separator"' in block
        cta = SUGGEST_CTA_RE.search(block)
        if cta:
            row["cta_badge"] = cta.group(1)
    row["platform_icons"] = icons
    row["delivery_separator"] = separator
    discount = SUGGEST_DISCOUNT_RE.search(chunk)
    row["discount_pct"] = int(discount.group(1)) if discount else None
    text = unescape(action.group(1)).strip()
    if text.startswith("CA$"):
        row["price_display"] = text
    else:
        row["action_text"] = text
    row["img"] = assets.entry(unescape(image.group(2)))
    return row


def build_suggest_orders(harvest: Path, assets: AssetIndex) -> dict:
    """{normalized query: pinned panel rows} from the frozen suggest DOMs."""
    orders: dict[str, list[dict]] = {}
    for query, relative in SUGGEST_CAPTURES.items():
        dom_path = harvest.parent / relative
        panel = extract_suggest_panel(
            dom_path.read_text(encoding="utf-8"), where=f"suggest '{query}'"
        )
        chunks = panel.split(SUGGEST_ROW_SPLIT)[1:]
        if not chunks:
            raise SeedError(f"suggest '{query}': no .product-search-result rows")
        rows = [
            parse_suggest_row(
                chunk, where=f"suggest '{query}' row {index}", assets=assets
            )
            for index, chunk in enumerate(chunks, start=1)
        ]
        orders[query] = rows
        REPORT.line(
            f"suggest '{query}': {len(rows)} pinned rows "
            f"({', '.join(row['kind'] for row in rows)})"
        )
    return orders


# -------------------------------------------------------------- search meta


def build_search_meta(harvest: Path, platforms, drm) -> dict:
    observed = load(harvest / ENDPOINTS_FILE)
    page_size = int(observed["search_endpoint"]["page_size"])
    return {
        "page_size": page_size,
        "genres": list(observed["genre_enum"]),
        "sorts": list(SORT_ENUM),
        "filters": list(FILTER_ENUM),
        "platforms": platforms,
        "drm": drm,
        "endpoints": {
            "search": observed["search_endpoint"]["path"],
            "lookup": observed["lookup_endpoint"]["path"],
        },
    }


# ---------------------------------------------------------------- validate


def assert_integer_money(node, path="$") -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}"
            if key.endswith("_minor"):
                scalars = value if isinstance(value, list) else [value]
                for scalar in scalars:
                    if not isinstance(scalar, int) or isinstance(scalar, bool):
                        raise SeedError(f"{child}: money field is not an integer: {value!r}")
            assert_integer_money(value, child)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            assert_integer_money(value, f"{path}[{index}]")
    elif isinstance(node, Decimal):
        raise SeedError(f"{path}: Decimal leaked into output")


def serialize(doc) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=1) + "\n"


# -------------------------------------------------------------------- main


def build(harvest: Path) -> dict:
    assets = AssetIndex(harvest)
    products, platforms, drm = build_products(harvest, assets)
    observed = load(harvest / ENDPOINTS_FILE)
    bundles = []
    bundle_files = sorted(path.name for path in harvest.glob(BUNDLE_GLOB))
    if not bundle_files:
        raise SeedError(f"no {BUNDLE_GLOB} files found in {harvest}")
    for name in bundle_files:
        bundle = norm_bundle(load(harvest / name), assets)
        cross_check_bundle(bundle)
        bundles.append(bundle)
    listing = build_bundles_listing(harvest, assets)
    doc = {
        "schema": SCHEMA,
        "currency": CURRENCY,
        "source": {
            "harvest": str(harvest.relative_to(SITE_ROOT))
            if harvest.is_relative_to(SITE_ROOT)
            else str(harvest),
            "harvest_ts_utc": observed["ts_utc"],
        },
        "search_meta": build_search_meta(harvest, platforms, drm),
        "suggest_orders": build_suggest_orders(harvest, assets),
        "products": products,
        "bundles": bundles,
        "bundles_listing": listing,
    }
    listing_total = sum(len(rows) for rows in listing.values())
    REPORT.line(
        f"entities: products={len(products)} bundles={len(bundles)} "
        f"bundles_listing={listing_total} "
        f"({', '.join(f'{cat}={len(rows)}' for cat, rows in listing.items())})"
    )
    REPORT.line(
        f"media: {assets.hits} refs localized to {STATIC_ASSET_PREFIX}*, "
        f"{len(assets.misses)} distinct urls not localized"
    )
    if assets.misses:
        REPORT.flag(
            "media urls without a localized blob (kept remote/source-only): "
            + ", ".join(assets.misses[:5])
            + (" ..." if len(assets.misses) > 5 else "")
        )
    assert_integer_money(doc)
    return doc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--harvest-dir", type=Path, default=DEFAULT_HARVEST)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="build and validate without writing the seed file",
    )
    args = parser.parse_args(argv)

    doc = build(args.harvest_dir)
    text = serialize(doc)
    if serialize(json.loads(text)) != text:
        raise SeedError("serialization does not round-trip deterministically")

    if not args.check_only:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        REPORT.line(f"wrote {args.out} ({len(text.encode('utf-8'))} bytes)")
    else:
        REPORT.line(f"check-only: seed valid ({len(text.encode('utf-8'))} bytes)")

    print("== build_seed report ==")
    for line in REPORT.lines:
        print(" ", line)
    if REPORT.subcent:
        print("  sub-cent money rounded HALF_UP:")
        for line in REPORT.subcent:
            print("   -", line)
    if REPORT.flags:
        print("  data-quality flags:")
        for line in REPORT.flags:
            print("   -", line)
    if REPORT.mismatches:
        print("  !! CROSS-CHECK MISMATCHES !!")
        for line in REPORT.mismatches:
            print("   -", line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
