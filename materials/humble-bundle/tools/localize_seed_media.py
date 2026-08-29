#!/usr/bin/env python3
"""Localize every media URL referenced by the offline-clone backend seed.

Stdlib-only companion to build_seed.py. Collects the media/image URLs the
seed references (product ``media`` entries, bundle tier item media,
``bundles_listing`` tile images -- the seed carries no bundle-level
hero/logo image fields -- and ``suggest_orders`` row images) and makes
each one servable offline:

  * a content-addressed blob under
    source-current/<capture>/assets/blobs/<sha256[:2]>/<sha256>
  * an entry in source-current/<capture>/assets/url-map.json
    ({url: {sha256, content_type, bytes}})
  * a copy at clone/static/assets/<sha256><ext>
  * an entry in clone/static/assets-provenance.json

URLs already present in url-map.json reuse the captured blob. Missing ones
are fetched with serial /usr/bin/curl GETs (desktop Chrome UA, 30s timeout,
at most 2 tries, 0.4s politeness delay before every request, 2MB cap).
A response whose magic bytes are not a real image -- an HTML body, for
example -- is a failure: the payload is discarded and the URL reported.
Videos are never fetched; only already-captured blobs are reused.

Media values may be raw URL strings (pre-localization seed) or the
localized ``{"local", "source_url"}`` entries build_seed.py emits, so the
tool is idempotent. Run it, then re-run build_seed.py so the seed points
at the localized copies.

Usage:
  python materials/humble-bundle/tools/localize_seed_media.py [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
from build_seed import (  # noqa: E402
    EXT_BY_CONTENT_TYPE,
    PRODUCT_MEDIA_FIELDS,
    SITE_ROOT,
    STATIC_ASSET_PREFIX,
)

CAPTURE_DIR = SITE_ROOT / "source-current" / "2026-08-20.humble-bundle-r1"
ASSETS_DIR = CAPTURE_DIR / "assets"
BLOBS_DIR = ASSETS_DIR / "blobs"
URL_MAP_PATH = ASSETS_DIR / "url-map.json"
SEED_PATH = SITE_ROOT / "clone" / "backend" / "seed_data.json"
STATIC_ASSETS_DIR = SITE_ROOT / "clone" / "static" / "assets"
PROVENANCE_PATH = SITE_ROOT / "clone" / "static" / "assets-provenance.json"

CURL = "/usr/bin/curl"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    " (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
TIMEOUT_S = 30
MAX_TRIES = 2
POLITENESS_DELAY_S = 0.4
MAX_IMAGE_BYTES = 2 * 1024 * 1024
VIDEO_MARKERS = (".mp4", ".webm", "fm=mp4")
FLUSH_EVERY = 25  # persist url-map progress every N successful fetches


# ------------------------------------------------------------- collection


def _source_url(value) -> str | None:
    """Media value (raw URL string or localized entry) -> source URL."""
    if isinstance(value, str) and value.startswith("http"):
        return value
    if isinstance(value, dict):
        url = value.get("source_url")
        if isinstance(url, str) and url.startswith("http"):
            return url
    return None


def collect_media_urls(seed: dict) -> tuple[list[str], dict[str, int]]:
    """Every media URL in the seed, unique+sorted, with per-section counts."""
    urls: set[str] = set()
    counts: dict[str, int] = {
        "product-media": 0,
        "bundle-tier-item-media": 0,
        "bundle-level-media": 0,
        "bundles-listing-tiles": 0,
        "suggest-rows": 0,
    }

    def take(section: str, value) -> None:
        url = _source_url(value)
        if url is not None:
            counts[section] += 1
            urls.add(url)

    for product in seed.get("products", []):
        media = product.get("media") or {}
        for field in PRODUCT_MEDIA_FIELDS:
            if field in media:
                take("product-media", media[field])
        for listed in ("screenshots", "thumbnails"):
            for value in media.get(listed) or []:
                take("product-media", value)
    for bundle in seed.get("bundles", []):
        # The seed schema has no bundle-level hero/logo/marketing image
        # fields (norm_bundle emits none); tier items carry the media.
        for tier in bundle.get("tiers", []):
            for item in tier.get("items", []):
                media = item.get("media") or {}
                if "featured_image" in media:
                    take("bundle-tier-item-media", media["featured_image"])
    for tiles in seed.get("bundles_listing", {}).values():
        for tile in tiles:
            take("bundles-listing-tiles", tile.get("tile_image"))
    for rows in seed.get("suggest_orders", {}).values():
        for row in rows:
            take("suggest-rows", row.get("img"))
    return sorted(urls), counts


# ---------------------------------------------------------------- fetching


def sniff_image(data: bytes) -> tuple[str, str] | None:
    """Magic-byte sniff -> (content_type, ext); None when not a real image."""
    if len(data) < 12:
        return None
    if data[:3] == b"\xff\xd8\xff":
        return ("image/jpeg", ".jpg")
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ("image/png", ".png")
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ("image/gif", ".gif")
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ("image/webp", ".webp")
    if data[4:8] == b"ftyp" and data[8:12] in (b"avif", b"avis"):
        return ("image/avif", ".avif")
    if data[:4] == b"\x00\x00\x01\x00":
        return ("image/vnd.microsoft.icon", ".ico")
    head = data[:1024].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if head.startswith((b"<?xml", b"<!doctype svg", b"<svg", b"<!--")):
        if b"<svg" in data[:4096].lower():
            return ("image/svg+xml", ".svg")
    return None


def curl_fetch(url: str, dest: Path) -> tuple[bool, str]:
    """Serial curl GET; <=2 tries, politeness delay before every request."""
    detail = "unknown"
    for _attempt in range(MAX_TRIES):
        time.sleep(POLITENESS_DELAY_S)
        proc = subprocess.run(
            [
                CURL,
                "-sS",
                "--location",
                "--max-redirs",
                "2",
                "-A",
                USER_AGENT,
                "--max-time",
                str(TIMEOUT_S),
                "--max-filesize",
                str(MAX_IMAGE_BYTES),
                "-o",
                str(dest),
                "-w",
                "%{http_code}",
                url,
            ],
            capture_output=True,
            text=True,
        )
        code = proc.stdout.strip()
        if proc.returncode == 0 and code == "200":
            return True, code
        detail = f"http={code} curl_rc={proc.returncode} {proc.stderr.strip()[:120]}"
    return False, detail


def blob_path(sha256: str) -> Path:
    return BLOBS_DIR / sha256[:2] / sha256


def write_json(path: Path, obj, *, indent: int, sort_keys: bool, trailing_nl: bool) -> None:
    text = json.dumps(obj, indent=indent, sort_keys=sort_keys, ensure_ascii=False)
    path.write_text(text + ("\n" if trailing_nl else ""), encoding="utf-8")


# -------------------------------------------------------------------- main


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="collect and report without fetching or writing anything",
    )
    args = parser.parse_args(argv)

    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    urls, counts = collect_media_urls(seed)
    url_map = json.loads(URL_MAP_PATH.read_text(encoding="utf-8"))

    def mapped_with_blob(url: str) -> bool:
        meta = url_map.get(url)
        return bool(meta) and blob_path(meta["sha256"]).exists()

    reused = [u for u in urls if mapped_with_blob(u)]
    to_fetch = [u for u in urls if not mapped_with_blob(u)]
    videoish = [u for u in to_fetch if any(m in u.lower() for m in VIDEO_MARKERS)]
    to_fetch = [u for u in to_fetch if u not in set(videoish)]

    print(f"seed media urls: {len(urls)} unique")
    for section, n in counts.items():
        print(f"  {section}: {n} refs")
    print(f"already localized (url-map blob reuse): {len(reused)}")
    print(f"to fetch: {len(to_fetch)}   video-like skipped: {len(videoish)}")
    if args.dry_run:
        return 0

    tmp = ASSETS_DIR / ".download.tmp"
    fetched: list[str] = []
    failed: list[tuple[str, str]] = []
    new_blob_bytes = 0
    since_flush = 0
    for url in to_fetch:
        ok, detail = curl_fetch(url, tmp)
        if not ok:
            tmp.unlink(missing_ok=True)
            failed.append((url, detail))
            continue
        data = tmp.read_bytes()
        if len(data) > MAX_IMAGE_BYTES:
            tmp.unlink(missing_ok=True)
            failed.append((url, f"payload {len(data)} bytes > 2MB cap"))
            continue
        kind = sniff_image(data)
        if kind is None:
            tmp.unlink(missing_ok=True)
            failed.append((url, "body is not a real image (magic bytes)"))
            continue
        content_type, _ext = kind
        sha256 = hashlib.sha256(data).hexdigest()
        blob = blob_path(sha256)
        if not blob.exists():
            blob.parent.mkdir(parents=True, exist_ok=True)
            tmp.replace(blob)
            new_blob_bytes += len(data)
        else:
            tmp.unlink(missing_ok=True)
        url_map[url] = {
            "sha256": sha256,
            "content_type": content_type,
            "bytes": len(data),
        }
        fetched.append(url)
        since_flush += 1
        if since_flush >= FLUSH_EVERY:
            write_json(URL_MAP_PATH, url_map, indent=1, sort_keys=False, trailing_nl=False)
            since_flush = 0
    if since_flush:
        write_json(URL_MAP_PATH, url_map, indent=1, sort_keys=False, trailing_nl=False)

    # Mirror every localized seed-media blob into clone/static/assets and
    # record provenance (first source URL for a blob wins; existing entries
    # are never rewritten).
    provenance = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
    copied = 0
    copied_bytes = 0
    unlocalizable: list[tuple[str, str]] = []
    for url in urls:
        meta = url_map.get(url)
        if meta is None:
            continue  # fetch failed above; already reported
        ext = EXT_BY_CONTENT_TYPE.get(meta["content_type"])
        if ext is None:
            unlocalizable.append((url, f"no extension for {meta['content_type']}"))
            continue
        name = f"{meta['sha256']}{ext}"
        dest = STATIC_ASSETS_DIR / name
        if not dest.exists():
            shutil.copyfile(blob_path(meta["sha256"]), dest)
            copied += 1
            copied_bytes += meta["bytes"]
        key = f"{STATIC_ASSET_PREFIX}{name}"
        if key not in provenance:
            provenance[key] = {
                "bytes": meta["bytes"],
                "content_type": meta["content_type"],
                "sha256": meta["sha256"],
                "source_url": url,
            }
    write_json(PROVENANCE_PATH, provenance, indent=2, sort_keys=True, trailing_nl=True)

    print("== localize_seed_media report ==")
    print(f"  fetched: {len(fetched)}  reused: {len(reused)}  failed: {len(failed)}")
    print(f"  new blob bytes: {new_blob_bytes}")
    print(f"  static assets copied: {copied} ({copied_bytes} bytes)")
    print(f"  static assets total: {len(list(STATIC_ASSETS_DIR.iterdir()))}")
    print(f"  provenance entries: {len(provenance)}")
    for url, why in unlocalizable:
        print(f"  UNLOCALIZABLE {url} :: {why}")
    for url, why in failed:
        print(f"  FAILED {url} :: {why}")
    if failed or unlocalizable:
        print("  (re-run build_seed.py only after failures are resolved or accepted)")
    return 1 if failed or unlocalizable else 0


if __name__ == "__main__":
    sys.exit(main())
