#!/usr/bin/env python3
"""Freeze one captured Home Depot page into an offline, self-contained document.

Home Depot's surfaces are heavy React apps. We serve the captured POST-render
DOM (playwright page.content()) as a frozen visual snapshot, download every
first-party visual asset (thdstatic css/js/img/font + same-origin static) into
a content-addressed local store, rewrite references to /static/assets/<cid>/,
and strip telemetry / anti-bot / remote script so the document makes ZERO
runtime requests to any remote origin. Client interactivity (search submit,
add-to-cart, filters) is re-implemented locally in static/site/*.js against the
clone's own JSON API — the frozen DOM is the visual/structural baseline only.

Usage:
  python3 materials/home-depot/tools/localize_page.py --site-dir materials/home-depot \
      --checkpoint home --viewport desktop --out-name home [--capture-id ...]
"""
from __future__ import annotations

import argparse
import hashlib
import mimetypes
import pathlib
import re
import sys
import urllib.parse
import urllib.request

# Remote origins that are telemetry, analytics, anti-bot, chat or ads — never
# clone dependencies. Any <script>/<img>/<iframe> to these is removed.
TELEMETRY_HOSTS = (
    "forter.com", "sprinklr.com", "px-cloud.net", "quantummetric.com",
    "qualtrics.com", "getamigo.io", "nr-data.net", "newrelic.com",
    "doubleclick.net", "online-metrix.net", "akstat.io", "go-mpulse.net",
    "agkn.com", "google-analytics.com", "googletagmanager.com",
    "facebook.net", "facebook.com", "bing.com", "bat.bing.com",
    "adsrvr.org", "everesttech.net", "rlcdn.com", "crwdcntrl.net",
    "demdex.net", "omtrdc.net", "adnxs.com", "clarity.ms",
    "mpulse.net", "tvpixel.com", "d.agkn.com",
)
# First-party asset origins we localize.
ASSET_HOSTS = ("thdstatic.com",)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")

EXT_BY_TYPE = {
    "text/css": ".css", "text/javascript": ".js",
    "application/javascript": ".js", "image/jpeg": ".jpg",
    "image/png": ".png", "image/webp": ".webp", "image/svg+xml": ".svg",
    "image/gif": ".gif", "font/woff2": ".woff2", "font/woff": ".woff",
    "application/font-woff2": ".woff2", "image/avif": ".avif",
    "image/x-icon": ".ico", "image/vnd.microsoft.icon": ".ico",
}


def is_telemetry(url: str) -> bool:
    return any(h in url for h in TELEMETRY_HOSTS)


def css_url_ref(localized: str | None, raw: str) -> str | None:
    """Resolve a CSS url() target: localized ref if downloaded, an empty data:
    URI for any unlocalizable remote (ad/telemetry fonts/images) so no remote
    request is issued, or None to keep the original (relative/data)."""
    if localized:
        return localized
    r = raw.strip().strip("'\"")
    if r.startswith(("http://", "https://", "//")):
        return "data:,"
    return None


def is_asset_host(url: str) -> bool:
    return any(h in url for h in ASSET_HOSTS)


def fetch(url: str) -> tuple[bytes, str] | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read(), (r.headers.get("content-type") or "").split(";")[0].strip()
    except Exception as exc:  # noqa: BLE001
        print(f"  ! fetch fail {url[:70]}: {type(exc).__name__}", file=sys.stderr)
        return None


def ext_for(url: str, ctype: str) -> str:
    ext = EXT_BY_TYPE.get(ctype)
    if ext:
        return ext
    path = urllib.parse.urlparse(url).path
    guess = pathlib.Path(path).suffix
    if guess and len(guess) <= 6:
        return guess
    return mimetypes.guess_extension(ctype or "") or ".bin"


class Localizer:
    def __init__(self, store_dir: pathlib.Path, cid: str):
        self.store_dir = store_dir
        self.cid = cid
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.url_map: dict[str, str] = {}     # remote url -> /static/... path
        self.pending: dict[str, bytes] = {}   # local rel path -> bytes (for css deferrals)

    def _local_ref(self, name: str) -> str:
        return f"/static/assets/{self.cid}/{name}"

    def localize_url(self, url: str) -> str | None:
        """Download one asset, return its /static ref, or None to drop."""
        url = url.strip().replace("&amp;", "&")
        if not url or url.startswith("data:") or url.startswith("/static/"):
            return url if url.startswith(("data:", "/static/")) else None
        if url.startswith("//"):
            url = "https:" + url
        if url.startswith("/") and not url.startswith("//"):
            url = "https://www.homedepot.com" + url
        if not url.startswith("http"):
            return None
        if is_telemetry(url) or not (is_asset_host(url) or "homedepot.com" in url):
            return None
        if url in self.url_map:
            return self.url_map[url]
        got = fetch(url)
        if got is None:
            return None
        body, ctype = got
        ext = ext_for(url, ctype)
        digest = hashlib.sha256(body).hexdigest()[:16]
        name = f"{digest}{ext}"
        dest = self.store_dir / name
        if ext == ".css":
            body = self._rewrite_css(body, url)
        if not dest.exists():
            dest.write_bytes(body)
        ref = self._local_ref(name)
        self.url_map[url] = ref
        return ref

    def _rewrite_css(self, body: bytes, base_url: str) -> bytes:
        text = body.decode("utf-8", "ignore")

        def repl(m):
            raw = m.group(1).strip("'\"")
            if raw.startswith("data:"):
                return m.group(0)
            abs_url = urllib.parse.urljoin(base_url, raw)
            ref = css_url_ref(self.localize_url(abs_url), raw)
            return f"url({ref})" if ref else m.group(0)

        text = re.sub(r"url\(([^)]+)\)", repl, text)
        return text.encode("utf-8")

    def localize_srcset(self, srcset: str) -> str:
        out = []
        for part in srcset.split(","):
            part = part.strip()
            if not part:
                continue
            bits = part.split()
            ref = self.localize_url(bits[0])
            if ref:
                out.append(" ".join([ref] + bits[1:]))
        return ", ".join(out)


def localize_html(html: str, loc: Localizer) -> str:
    # 0a. Strip balanced HTML comments FIRST. The source embeds commented-out
    #     legacy markup like `<!-- Old On-Prem Version <script ...></script -->`
    #     whose closing `-->` sits right after a <script>; if the later script
    #     removal runs first it eats that `-->`, leaving an unclosed comment that
    #     swallows the whole footer. Removing balanced comments up front (they
    #     are never needed in an offline clone) avoids that entirely. `[^-]` in
    #     the closer keeps it from spanning across separate comments.
    html = re.sub(r"<!--(?:(?!-->).)*?-->", "", html, flags=re.S)

    # 0. Malformed nested speculationrules block: the source nests a telemetry
    #    <script> inside <script type="speculationrules">, so the HTML parser
    #    closes early and the rules JSON leaks as visible text. Remove the whole
    #    span up to the JSON's closing </script>.
    html = re.sub(
        r'<script\s+type=["\']speculationrules["\'][^>]*>.*?\}\s*</script>',
        "", html, flags=re.S | re.I)

    # 1. Remove telemetry + all remote scripts; keep ld+json data scripts.
    def script_repl(m):
        tag = m.group(0)
        if 'type="application/ld+json"' in tag or "type='application/ld+json'" in tag:
            return tag
        return ""  # drop every other script (remote or inline app js)

    html = re.sub(r"<script\b[^>]*>.*?</script>", script_repl, html, flags=re.S | re.I)
    html = re.sub(r"<script\b[^>]*/>", "", html, flags=re.I)
    # Remove ALL remote iframes (telemetry, reCAPTCHA, Google Pay payframe, chat,
    # ads). An offline clone embeds no third-party frame; the interactions they
    # back (captcha gate, wallet pay) are re-implemented locally. Same-origin
    # iframes, if any, are preserved.
    # Ad/telemetry markers that appear inside srcdoc ad creatives (RevJet units
    # embed a full escaped ad document that fires rmt.homedepot.com beacons when
    # the srcdoc frame renders — it carries no remote src, so the src check
    # below cannot see it).
    ad_frame = re.compile(r"rmt\.homedepot\.com|revjet|/interaction/|%%PIXEL%%", re.I)

    def iframe_repl(m):
        tag = m.group(0)
        src = re.search(r'src=["\']([^"\']+)["\']', tag)
        if src and re.match(r'https?://|//', src.group(1).strip()):
            return ""
        if ad_frame.search(tag):
            return ""
        return m.group(0)

    html = re.sub(r"<iframe\b[^>]*>.*?</iframe>", iframe_repl, html, flags=re.S | re.I)
    html = re.sub(r"<iframe\b[^>]*/?>", iframe_repl, html, flags=re.I)

    # 2. Rewrite <link href> (stylesheets, preloads, icons).
    def link_repl(m):
        tag = m.group(0)
        href = re.search(r'href=["\']([^"\']+)["\']', tag)
        if not href:
            return tag
        ref = loc.localize_url(href.group(1))
        if ref is None:
            # drop preconnect/dns-prefetch/remote we won't use
            if re.search(r'rel=["\'](?:stylesheet|icon|preload|apple-touch-icon)', tag):
                return ""
            return tag
        return tag.replace(href.group(0), f'href="{ref}"')

    html = re.sub(r"<link\b[^>]*>", link_repl, html, flags=re.I)

    # 3. Rewrite <img src/srcset> and <source srcset>.
    def img_repl(m):
        tag = m.group(0)
        src = re.search(r'src=["\']([^"\']+)["\']', tag)
        if src:
            raw = src.group(1)
            ref = loc.localize_url(raw)
            if ref:
                tag = tag.replace(src.group(0), f'src="{ref}"')
            elif raw.strip().startswith(("http", "//")):
                # unlocalizable remote (telemetry pixel / tracker) — drop it
                return ""
        ss = re.search(r'srcset=["\']([^"\']+)["\']', tag)
        if ss:
            newss = loc.localize_srcset(ss.group(1))
            tag = tag.replace(ss.group(0), f'srcset="{newss}"' if newss else "")
        return tag

    html = re.sub(r"<img\b[^>]*>", img_repl, html, flags=re.I)
    html = re.sub(r"<source\b[^>]*>", img_repl, html, flags=re.I)

    # 3b. Drop preconnect/dns-prefetch links (pure connection hints, no resource;
    #     always remote). preload/prefetch carry a real href already localized above.
    def preconnect_repl(m):
        tag = m.group(0)
        if re.search(r'rel=["\'](?:preconnect|dns-prefetch)["\']', tag, re.I):
            return ""
        return tag

    html = re.sub(r"<link\b[^>]*>", preconnect_repl, html, flags=re.I)

    # 3d. Inline style="...background-image:url(...)..." attributes.
    def inline_style_repl(m):
        val = m.group(1)
        if "url(" not in val:
            return m.group(0)
        new = re.sub(
            r"url\((&quot;|['\"]?)([^)]*?)(&quot;|['\"]?)\)",
            lambda u: (lambda ref: f"url({ref})" if ref else u.group(0))(
                css_url_ref(loc.localize_url(u.group(2).replace("&quot;", "").strip("'\"")), u.group(2))),
            val)
        return f'style="{new}"'

    html = re.sub(r'style="([^"]*)"', inline_style_repl, html, flags=re.I)

    # 3c. Rewrite <a href> first-party links to local routes; external -> boundary.
    def anchor_repl(m):
        tag = m.group(0)
        href = re.search(r'href=["\']([^"\']+)["\']', tag)
        if not href:
            return tag
        raw = href.group(1).replace("&amp;", "&")
        if raw.startswith(("http://www.homedepot.com", "https://www.homedepot.com")):
            path = urllib.parse.urlparse(raw).path or "/"
            q = urllib.parse.urlparse(raw).query
            local = path + (("?" + q) if q else "")
            return tag.replace(href.group(0), f'href="{local}"')
        if raw.startswith("http"):
            slug = urllib.parse.urlparse(raw).netloc
            return tag.replace(href.group(0), f'href="/external/{slug}"')
        return tag

    html = re.sub(r"<a\b[^>]*>", anchor_repl, html, flags=re.I)

    # 6. SEO/meta remote references (canonical, alternate hreflang, og:url) and
    # ld+json URLs are not runtime loads, but the network-closure gate scans
    # document text, so localize them to same-origin / relative to keep the
    # served files free of remote-origin references.
    def _to_local_path(url: str) -> str:
        p = urllib.parse.urlparse(url.replace("&amp;", "&"))
        return (p.path or "/") + (("?" + p.query) if p.query else "")

    # drop alternate hreflang links entirely (localized variants, incl. .ca)
    html = re.sub(r'<link\b[^>]*rel=["\']alternate["\'][^>]*>', "", html, flags=re.I)

    # canonical -> local path
    def canon_repl(m):
        tag = m.group(0)
        href = re.search(r'href=["\']([^"\']+)["\']', tag)
        if href and "homedepot." in href.group(1):
            return tag.replace(href.group(0), f'href="{_to_local_path(href.group(1))}"')
        return tag
    html = re.sub(r'<link\b[^>]*rel=["\']canonical["\'][^>]*>', canon_repl, html, flags=re.I)

    # og:url / og:image and other meta content pointing at homedepot -> local
    def meta_repl(m):
        tag = m.group(0)
        c = re.search(r'content=["\']([^"\']+)["\']', tag)
        if c and re.match(r'https?://(?:www\.)?homedepot\.(?:com|ca)', c.group(1)):
            return tag.replace(c.group(0), f'content="{_to_local_path(c.group(1))}"')
        return tag
    html = re.sub(r'<meta\b[^>]*>', meta_repl, html, flags=re.I)

    # ld+json data blocks: rewrite absolute homedepot URLs to relative
    def ldjson_repl(m):
        body = m.group(0)
        body = re.sub(r'https?://(?:www\.)?homedepot\.com', "", body)
        body = re.sub(r'https?://(?:www\.)?homedepot\.ca', "", body)
        return body
    html = re.sub(r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>.*?</script>',
                  ldjson_repl, html, flags=re.S | re.I)

    # 7. Final catch-all: neutralize any remaining remote reference that lives in
    # inert escaped data templates (ad/telemetry config blobs the page embeds as
    # text — revjet ad fonts, quantummetric, rma). These are not live loads, but
    # the network-closure gate scans document text, so blank them out.
    html = re.sub(r"url\(\s*['\"]?https?://[^)'\"]+['\"]?\s*\)", "url(data:,)", html)
    html = re.sub(r"https?://(?:cdn\.revjet\.com|rma\.homedepot\.com|"
                  r"cdn\.quantummetric\.com)[^\s'\"()<>&]*", "about:blank", html)

    # 4. Inline style="...url(...)..." and <style> blocks.
    def style_block(m):
        css = m.group(1)
        css = re.sub(r"url\(([^)]+)\)",
                     lambda u: (lambda ref: f"url({ref})" if ref else u.group(0))(
                         css_url_ref(loc.localize_url(u.group(1).strip("'\"")), u.group(1))), css)
        return f"<style{m.group('attrs')}>{css}</style>"

    html = re.sub(r"<style(?P<attrs>[^>]*)>(.*?)</style>", style_block, html, flags=re.S | re.I)

    # 5. Drop remaining absolute remote hrefs on <a> that point to telemetry.
    return html


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-dir", default="materials/home-depot")
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--viewport", default="desktop")
    ap.add_argument("--out-name", required=True)
    ap.add_argument("--capture-id", default="2026-08-18.home-depot-r1")
    ap.add_argument("--src-root", default="source-current",
                    help="source-current or source-auth-scratch/authed-source-current")
    args = ap.parse_args()

    site = pathlib.Path(args.site_dir)
    src = site / args.src_root / args.capture_id / args.checkpoint / args.viewport / "page.html"
    if not src.is_file():
        print(f"missing capture: {src}", file=sys.stderr)
        return 2
    html = src.read_text(errors="ignore")
    store = site / "clone" / "static" / "assets" / args.capture_id
    loc = Localizer(store, args.capture_id)
    out_html = localize_html(html, loc)

    pages_dir = site / "clone" / "frontend" / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    out_path = pages_dir / f"{args.out_name}.html"
    out_path.write_text(out_html, encoding="utf-8")
    # residual remote refs check
    residual = len(re.findall(r'(?:src|href)=["\']https?://', out_html))
    print(f"localized {args.checkpoint}/{args.viewport} -> {out_path}")
    print(f"  assets downloaded: {len(loc.url_map)} | residual remote refs: {residual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
