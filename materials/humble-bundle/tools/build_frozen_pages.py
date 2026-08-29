#!/usr/bin/env python3
"""Build the frozen offline frontend for the humble-bundle clone.

Deterministic, re-runnable, stdlib-only (html.parser + regex). Pure file
transformation: reads already-captured evidence under
``source-current/<run>/`` and writes frozen pages, localized assets,
provenance, a pages manifest and a build report. It never launches a
browser and never touches the network.

Inputs
    static/<checkpoint>/desktop/dom.html   post-render DOM (www pages)
    static/<checkpoint>/mobile/dom.html    used for divergence reporting only
    interactive/support-*/dom.html         support pages (desktop)
    assets/blobs/<sha[:2]>/<sha>           captured response bodies
    assets/url-map.json                    {url: {sha256, content_type, bytes}}

Outputs
    clone/frontend/pages/<checkpoint>.html
    clone/frontend/pages-manifest.json
    clone/frontend/state-blobs/<checkpoint>.<id>.json   (reference data)
    clone/static/assets/<sha256><ext>                   (+ assets-provenance.json)
    clone/static/site/hb-app.js                         (placeholder, if absent)
    source-current/<run>/frozen-build-report.json

Usage
    python3 materials/humble-bundle/tools/build_frozen_pages.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

SITE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = SITE_ROOT / "source-current" / "2026-08-20.humble-bundle-r1"
CLONE_DIR = SITE_ROOT / "clone"
ASSET_DIR = CLONE_DIR / "static" / "assets"
PAGES_DIR = CLONE_DIR / "frontend" / "pages"
STATE_DIR = CLONE_DIR / "frontend" / "state-blobs"
SITE_JS = CLONE_DIR / "static" / "site" / "hb-app.js"
PROVENANCE_PATH = CLONE_DIR / "static" / "assets-provenance.json"
MANIFEST_PATH = CLONE_DIR / "frontend" / "pages-manifest.json"

MARKER = "<!-- websitebench-frozen -->"
DOCTYPE = "<!DOCTYPE html>"
INJECT_SCRIPT = '<script src="/static/site/hb-app.js" defer></script>'
CSRF_PLACEHOLDER = "websitebench-frozen-csrf"
ASSET_URL_PREFIX = "/static/assets/"
MISSING_URL_PREFIX = "/static/assets/missing/"

# checkpoint -> (route, source cell dir relative to the run dir)
PAGES: list[tuple[str, str, str]] = [
    ("home", "/", "static/home/desktop"),
    ("bundles", "/bundles", "static/bundles/desktop"),
    ("games", "/games", "static/games/desktop"),
    ("books", "/books", "static/books/desktop"),
    ("software", "/software", "static/software/desktop"),
    ("bundle-anchor", "/games/yes-chef-cooking-bundle", "static/bundle-anchor/desktop"),
    ("bundle-2k", "/games/2k-megahits-2026-bundle", "static/bundle-2k/desktop"),
    ("store", "/store", "static/store/desktop"),
    ("store-search", "/store/search", "static/store-search/desktop"),
    (
        "store-search-noresults",
        "/store/search?search=zzzz-no-match-websitebench",
        "static/store-search-noresults/desktop",
    ),
    ("store-product-satisfactory", "/store/satisfactory", "static/store-product-satisfactory/desktop"),
    ("membership", "/membership", "static/membership/desktop"),
    ("login", "/login", "static/login/desktop"),
    ("signup", "/signup", "static/signup/desktop"),
    ("about", "/about", "static/about/desktop"),
    ("charities", "/charities", "static/charities/desktop"),
    ("terms", "/terms", "static/terms/desktop"),
    ("privacy", "/privacy", "static/privacy/desktop"),
    ("legal", "/legal", "static/legal/desktop"),
    ("cookie-policy", "/cookie-policy", "static/cookie-policy/desktop"),
    ("accessibility", "/accessibility", "static/accessibility/desktop"),
    ("notfound-404", "404-handler", "static/notfound-404/desktop"),
    ("support-home", "/support", "interactive/support-home"),
    ("support-category", "/support/categories/200166394", "interactive/support-category"),
    ("support-article", "/support/articles/52764568066971", "interactive/support-article"),
]

LOCAL_ASSET_HOSTS = {
    "cdn.humblebundle.com",
    "hb.imgix.net",
    "hbproxy.imgix.net",
    "humblebundle-a.akamaihd.net",
    "www.humblebundle.com",
}
SUPPORT_HOSTS = {"support.humblebundle.com", "humblebundle.zendesk.com"}
SUPPORT_CATEGORY_PREFIX = "/hc/en-us/categories/200166394"
SUPPORT_ARTICLE_PREFIX = "/hc/en-us/articles/52764568066971"

TRACKER_KEYWORDS = (
    "googletagmanager",
    "optimizely",
    "ziffstatic",
    "zdbb",
    "clarity",
    "sift",
    "recaptcha",
    "gstatic",
    "doubleclick",
    "facebook.net",
    "onetrust",
    "cookielaw",
    "rlcdn",
    "upsellit",
    "impactcdn",
    "bing",
    "line-scdn",
    "shop.pe",
    "algolia",
)
# keywords safe to match as words inside id/class/name/data-* attribute values
_ATTR_KEYWORDS = [k for k in TRACKER_KEYWORDS if re.fullmatch(r"[a-z]+", k)]
ATTR_KEYWORD_RE = re.compile(r"\b(" + "|".join(_ATTR_KEYWORDS) + r")\b", re.I)

VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}

NAV_POSITIONS = {("a", "href"), ("area", "href"), ("form", "action"),
                 ("button", "formaction"), ("input", "formaction")}
# `data-lazy` is the carousel library's own lazy attribute and belongs here for
# the same reason `data-src` does: the browser loads whatever it names. It was
# missing while `data-lazy-src` sat in the inert list two lines down, so 33
# images across the store listing, the membership page and a bundle page were
# never downloaded and never rewritten — they stayed pointed at the source's
# image CDN, and rendered blank only because the library that would have
# promoted them had been stripped. A blank image is not a localized one.
NETWORK_ATTRS = {"src", "srcset", "poster", "background",
                 "data-src", "data-srcset", "data-poster", "data-lazy"}
LOADING_LINK_RELS = {"stylesheet", "icon", "apple-touch-icon", "mask-icon",
                     "manifest", "preload", "modulepreload", "shortcut", "image_src"}
HINT_LINK_RELS = {"preconnect", "dns-prefetch", "prefetch", "modulepreload"}
INERT_URL_ATTRS = {"content", "cite", "longdesc", "data-bg", "data-background",
                   "data-background-image", "data-image", "data-lazy-src"}
SKIP_SCHEMES = ("data:", "#", "mailto:", "tel:", "javascript:", "about:", "blob:")

EXT_BY_CONTENT_TYPE = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/avif": ".avif",
    "image/svg+xml": ".svg",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
    "text/css": ".css",
    "text/javascript": ".js",
    "application/javascript": ".js",
    "application/x-javascript": ".js",
    "application/json": ".json",
    "application/manifest+json": ".webmanifest",
    "font/woff2": ".woff2",
    "font/woff": ".woff",
    "font/ttf": ".ttf",
    "font/otf": ".otf",
    "application/font-woff": ".woff",
    "application/font-woff2": ".woff2",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "text/html": ".html",
    "text/plain": ".txt",
    "application/xml": ".xml",
    "text/xml": ".xml",
}

CSS_URL_RE = re.compile(
    r"""url\(\s*(?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)'|(?P<bare>[^)"'\s][^)]*?))\s*\)""",
    re.IGNORECASE,
)
CSS_IMPORT_RE = re.compile(r"""@import\s+(?:"(?P<dq>[^"]+)"|'(?P<sq>[^']+)')""", re.IGNORECASE)
ATTR_ITEM_RE = re.compile(
    r"""\s*(?P<name>[^\s/>=]+)"""
    r"""(?:\s*=\s*(?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)'|(?P<bare>[^\s>]*)))?""",
)
REMOTE_URL_RE = re.compile(r"^(?:https?:)?//", re.I)
ABS_HTTP_RE = re.compile(r"https?://", re.I)


def html_unescape(value: str) -> str:
    import html

    return html.unescape(value)


def html_escape_attr(value: str, quote: str) -> str:
    out = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if quote == '"':
        out = out.replace('"', "&quot;")
    elif quote == "'":
        out = out.replace("'", "&#x27;")
    return out


class Node:
    __slots__ = ("tag", "attrs", "start", "tag_end", "end_start", "end",
                 "raw", "parent", "removed", "in_removed")

    def __init__(self, tag, attrs, start, tag_end, raw, parent):
        self.tag = tag
        self.attrs = attrs
        self.start = start
        self.tag_end = tag_end
        self.end_start = tag_end
        self.end = tag_end
        self.raw = raw
        self.parent = parent
        self.removed = False
        self.in_removed = False


class OffsetHTMLParser(HTMLParser):
    """Records start/end tag events with absolute character offsets."""

    def __init__(self, text: str):
        super().__init__(convert_charrefs=False)
        self.text = text
        self._line_starts = [0]
        idx = text.find("\n")
        while idx != -1:
            self._line_starts.append(idx + 1)
            idx = text.find("\n", idx + 1)
        self.events: list[tuple] = []

    def _offset(self) -> int:
        line, col = self.getpos()
        return self._line_starts[line - 1] + col

    def handle_starttag(self, tag, attrs):
        raw = self.get_starttag_text() or ""
        start = self._offset()
        self.events.append(("start", tag, start, start + len(raw), attrs, raw))

    def handle_startendtag(self, tag, attrs):
        raw = self.get_starttag_text() or ""
        start = self._offset()
        self.events.append(("startend", tag, start, start + len(raw), attrs, raw))

    def handle_endtag(self, tag):
        start = self._offset()
        gt = self.text.find(">", start)
        end = gt + 1 if gt != -1 else start
        self.events.append(("end", tag, start, end, None, None))

    def handle_data(self, data):
        self.events.append(("data", None, self._offset(), self._offset() + len(data), None, None))

    def handle_comment(self, data):
        start = self._offset()
        self.events.append(("comment", None, start, start + len(data) + 7, None, None))


def parse_nodes(text: str) -> list[Node]:
    parser = OffsetHTMLParser(text)
    parser.feed(text)
    parser.close()
    nodes: list[Node] = []
    stack: list[Node] = []
    for kind, tag, start, end, attrs, raw in parser.events:
        if kind in ("start", "startend"):
            attr_dict = {}
            for name, value in attrs or []:
                attr_dict.setdefault(name.lower(), value)
            node = Node(tag, attr_dict, start, end, raw, stack[-1] if stack else None)
            nodes.append(node)
            if kind == "start" and tag not in VOID_ELEMENTS:
                stack.append(node)
        elif kind == "end":
            match_idx = None
            for i in range(len(stack) - 1, -1, -1):
                if stack[i].tag == tag:
                    match_idx = i
                    break
            if match_idx is None:
                continue
            while len(stack) > match_idx + 1:
                dangling = stack.pop()
                dangling.end_start = start
                dangling.end = start
            matched = stack.pop()
            matched.end_start = start
            matched.end = end
    while stack:
        dangling = stack.pop()
        dangling.end_start = len(text)
        dangling.end = len(text)
    return nodes


def scan_raw_attrs(raw: str):
    """Yield (name_lower, value_raw|None, value_span|None, quote) from a raw start tag.

    Spans index into ``raw`` and exclude the surrounding quotes. Boolean
    attributes yield value None. Sequential scanning ensures we never match
    attribute-like text inside another attribute's value.
    """
    head = re.match(r"<\s*[a-zA-Z][^\s/>]*", raw)
    if not head:
        return
    pos = head.end()
    while pos < len(raw):
        item = ATTR_ITEM_RE.match(raw, pos)
        if not item or not item.group("name") or item.end() == pos:
            break
        if item.group("dq") is not None:
            value, span, quote = item.group("dq"), item.span("dq"), '"'
        elif item.group("sq") is not None:
            value, span, quote = item.group("sq"), item.span("sq"), "'"
        elif item.group("bare") is not None:
            value, span, quote = item.group("bare"), item.span("bare"), ""
        else:
            value, span, quote = None, None, None
        yield item.group("name").lower(), value, span, quote
        pos = item.end()


def guess_ext_from_url(url: str) -> str:
    path = urlsplit(url).path
    seg = path.rsplit("/", 1)[-1]
    if "." in seg:
        cand = seg.rsplit(".", 1)[-1].lower()
        if re.fullmatch(r"[a-z0-9]{1,8}", cand):
            return "." + cand
    return ".bin"


def ext_for_content_type(content_type: str, url: str) -> str:
    ct = content_type.split(";", 1)[0].strip().lower()
    if ct in EXT_BY_CONTENT_TYPE:
        return EXT_BY_CONTENT_TYPE[ct]
    guessed = guess_ext_from_url(url)
    return guessed if guessed != ".bin" else ".bin"


class BuildContext:
    def __init__(self, run_dir: Path, url_map: dict):
        self.external_links: dict[str, dict] = {}
        self.run_dir = run_dir
        self.url_map = url_map
        self.provenance: dict[str, dict] = {}
        self.copied: dict[str, str] = {}       # source url -> local runtime path
        self.css_memo: dict[str, str] = {}     # css source url -> local runtime path
        self.css_in_progress: set[str] = set()
        self.missing: dict[str, dict] = {}     # abs url -> {path, wheres:set}
        self.dropped_missing: dict[str, set] = {}  # abs url -> {where, ...}
        self.css_url_rewrites = 0
        self.css_transformed = 0

    # -- url-map helpers -------------------------------------------------
    def map_lookup(self, abs_url: str):
        entry = self.url_map.get(abs_url)
        if entry is None and abs_url.startswith("http://"):
            entry = self.url_map.get("https://" + abs_url[len("http://"):])
            if entry is not None:
                abs_url = "https://" + abs_url[len("http://"):]
        if entry is None and "#" in abs_url:
            bare = abs_url.split("#", 1)[0]
            entry = self.url_map.get(bare)
            if entry is not None:
                abs_url = bare
        return (abs_url, entry) if entry is not None else (abs_url, None)

    def blob_path(self, sha256: str) -> Path:
        return self.run_dir / "assets" / "blobs" / sha256[:2] / sha256

    # -- asset localization ----------------------------------------------
    def localize_asset(self, abs_url: str, entry: dict) -> str:
        if abs_url in self.copied:
            return self.copied[abs_url]
        content_type = entry["content_type"].split(";", 1)[0].strip().lower()
        if content_type == "text/css":
            return self.localize_css(abs_url, entry)
        ext = ext_for_content_type(entry["content_type"], abs_url)
        name = entry["sha256"] + ext
        local = ASSET_URL_PREFIX + name
        target = ASSET_DIR / name
        if not target.exists():
            target.write_bytes(self.blob_path(entry["sha256"]).read_bytes())
        self.provenance.setdefault(local, {
            "source_url": abs_url,
            "sha256": entry["sha256"],
            "bytes": entry["bytes"],
            "content_type": entry["content_type"],
        })
        self.copied[abs_url] = local
        return local

    def localize_css(self, abs_url: str, entry: dict) -> str:
        if abs_url in self.css_memo:
            return self.css_memo[abs_url]
        if abs_url in self.css_in_progress:  # @import cycle guard
            return self.missing_path(abs_url, f"css-cycle:{abs_url}")
        self.css_in_progress.add(abs_url)
        raw = self.blob_path(entry["sha256"]).read_bytes()
        text = raw.decode("utf-8", "surrogateescape")
        new_text, changed = self.rewrite_css_text(text, abs_url, f"css:{abs_url}")
        if changed:
            data = new_text.encode("utf-8", "surrogateescape")
            sha = hashlib.sha256(data).hexdigest()
            name = sha + ".css"
            local = ASSET_URL_PREFIX + name
            target = ASSET_DIR / name
            if not target.exists():
                target.write_bytes(data)
            self.provenance.setdefault(local, {
                "source_url": abs_url,
                "sha256": sha,
                "source_sha256": entry["sha256"],
                "bytes": len(data),
                "content_type": entry["content_type"],
                "transform": "css-url-rewrite",
            })
            self.css_transformed += 1
        else:
            name = entry["sha256"] + ".css"
            local = ASSET_URL_PREFIX + name
            target = ASSET_DIR / name
            if not target.exists():
                target.write_bytes(raw)
            self.provenance.setdefault(local, {
                "source_url": abs_url,
                "sha256": entry["sha256"],
                "bytes": entry["bytes"],
                "content_type": entry["content_type"],
            })
        self.css_in_progress.discard(abs_url)
        self.css_memo[abs_url] = local
        self.copied[abs_url] = local
        return local

    def rewrite_css_text(self, text: str, base_url: str, where: str) -> tuple[str, bool]:
        edits: list[tuple[int, int, str]] = []

        def handle(url_value: str, span: tuple[int, int]):
            candidate = url_value.strip()
            if not candidate or candidate.startswith(SKIP_SCHEMES):
                return
            abs_url = urljoin(base_url, candidate)
            if not abs_url.startswith(("http://", "https://")):
                return
            abs_url, entry = self.map_lookup(abs_url)
            if entry is not None:
                local = self.localize_asset(abs_url, entry)
            else:
                local = self.missing_path(abs_url, where)
            if local != candidate:
                edits.append((span[0], span[1], local))
                self.css_url_rewrites += 1

        for m in CSS_URL_RE.finditer(text):
            for group in ("dq", "sq", "bare"):
                if m.group(group) is not None:
                    handle(m.group(group), m.span(group))
                    break
        for m in CSS_IMPORT_RE.finditer(text):
            for group in ("dq", "sq"):
                if m.group(group) is not None:
                    handle(m.group(group), m.span(group))
                    break
        if not edits:
            return text, False
        edits.sort(key=lambda e: e[0], reverse=True)
        for start, end, replacement in edits:
            text = text[:start] + replacement + text[end:]
        return text, True

    def record_dropped_missing(self, abs_url: str, where: str) -> None:
        self.dropped_missing.setdefault(abs_url, set()).add(where)

    def missing_path(self, abs_url: str, where: str) -> str:
        rec = self.missing.get(abs_url)
        if rec is None:
            sha1 = hashlib.sha1(abs_url.encode("utf-8", "surrogateescape")).hexdigest()
            rec = {"path": MISSING_URL_PREFIX + sha1 + guess_ext_from_url(abs_url),
                   "wheres": set()}
            self.missing[abs_url] = rec
        rec["wheres"].add(where)
        return rec["path"]


def external_slug(host: str, path: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (host + (path if path not in ("", "/") else "")).lower()).strip("-")
    return base[:80] or "link"


def host_scope(url: str) -> str:
    """Classify a missing-asset URL for the follow-up capture pass."""
    host = urlsplit(url).netloc.lower()
    if host in LOCAL_ASSET_HOSTS:
        return "primary-origin"
    if host in SUPPORT_HOSTS:
        return "support-origin"
    return "external"


def support_route_for(path: str) -> str:
    if path.startswith(SUPPORT_CATEGORY_PREFIX):
        return "/support/categories/200166394"
    if path.startswith(SUPPORT_ARTICLE_PREFIX):
        return "/support/articles/52764568066971"
    return "/support"


def position_kind(tag: str, attr: str, attrs: dict) -> str:
    """Classify a (tag, attribute) URL position: nav / network / inert."""
    if (tag, attr) in NAV_POSITIONS:
        return "nav"
    if tag == "link" and attr == "href":
        rels = set((attrs.get("rel") or "").lower().split())
        return "network" if rels & LOADING_LINK_RELS else "inert"
    if attr in NETWORK_ATTRS:
        return "network"
    if tag in ("use", "image") and attr in ("href", "xlink:href"):
        return "network"
    if tag == "object" and attr == "data":
        return "network"
    if tag in ("embed", "track", "input") and attr == "src":
        return "network"
    return "inert"


class PageBuilder:
    def __init__(self, ctx: BuildContext, checkpoint: str, route: str, cell: str):
        self.ctx = ctx
        self.checkpoint = checkpoint
        self.route = route
        self.cell = cell
        cell_dir = ctx.run_dir / cell
        self.source_path = cell_dir / "dom.html"
        meta = json.loads((cell_dir / "meta.json").read_text(encoding="utf-8"))
        self.page_url = meta.get("final_url") or meta["url"]
        self.removals: Counter = Counter()
        self.assets_rewritten = 0
        self.missing_rewritten = 0
        self.page_links_rewritten = 0
        self.csrf_neutralized = 0
        self.state_blobs: list[str] = []
        self.title = ""

    # -- URL policy --------------------------------------------------------

    def rewrite_url(self, value: str, kind: str, where: str):
        candidate = value.strip()
        if not candidate or candidate.startswith(SKIP_SCHEMES):
            return None
        if kind == "inert" and not REMOTE_URL_RE.match(candidate):
            # inert positions (meta content, data-*, …) are only rewritten when
            # they hold an absolute remote URL; never resolve bare tokens like
            # "width=device-width" against the page URL
            return None
        abs_url = urljoin(self.page_url, candidate)
        if not abs_url.startswith(("http://", "https://")):
            return None
        abs_url, entry = self.ctx.map_lookup(abs_url)
        if entry is not None:
            self.assets_rewritten += 1
            return self.ctx.localize_asset(abs_url, entry)
        host = urlsplit(abs_url).netloc.lower()
        if kind == "network":
            self.missing_rewritten += 1
            return self.ctx.missing_path(abs_url, where)
        if host in SUPPORT_HOSTS:
            new = support_route_for(urlsplit(abs_url).path)
            if new != candidate:
                self.page_links_rewritten += 1
                return new
            return None
        if host == "www.humblebundle.com":
            parts = urlsplit(abs_url)
            new = parts.path or "/"
            if parts.query:
                new += "?" + parts.query
            if parts.fragment:
                new += "#" + parts.fragment
            if new != candidate:
                self.page_links_rewritten += 1
                return new
            return None
        if kind == "nav":
            # external navigation goes through the local interstitial so no
            # remote reference remains (established /external/<slug> pattern)
            parts = urlsplit(abs_url)
            slug = external_slug(parts.netloc.lower(), parts.path)
            self.ctx.external_links[slug] = {"host": parts.netloc, "path": parts.path or "/"}
            self.page_links_rewritten += 1
            return "/external/" + slug
        return None  # inert reference stays as-is

    # -- removal policy ----------------------------------------------------
    def tracker_keyword(self, node: Node):
        for attr_name, attr_value in node.attrs.items():
            if not attr_value:
                continue
            value = html_unescape(attr_value)
            if REMOTE_URL_RE.match(value.strip()) or value.strip().startswith("/"):
                abs_url = urljoin(self.page_url, value.strip())
                host = urlsplit(abs_url).netloc.lower()
                for kw in TRACKER_KEYWORDS:
                    if kw in host:
                        return kw
            if attr_name in ("id", "class", "name") or attr_name.startswith("data-"):
                m = ATTR_KEYWORD_RE.search(value)
                if m:
                    return m.group(1).lower()
        return None

    def missing_only_reference(self, node: Node) -> bool:
        """True when this node exists solely to fetch an asset we never localized.

        ``<source>`` and ``<link>`` carry no content of their own, so keeping
        them with a placeholder path only produces a runtime 404 and a console
        error the source never emits. The URL is still disclosed in the build
        report as a dropped reference.
        """
        if node.tag not in ("source", "link"):
            return False
        for attr in ("src", "srcset", "href"):
            value_raw = node.attrs.get(attr)
            if not value_raw:
                continue
            value = html_unescape(value_raw).strip()
            if not value or value.startswith(SKIP_SCHEMES):
                continue
            if position_kind(node.tag, attr, node.attrs) != "network":
                continue
            first = value.split(",")[0].strip().split(" ")[0] if attr == "srcset" else value
            abs_url = urljoin(self.page_url, first)
            if not abs_url.startswith(("http://", "https://")):
                continue
            abs_url, entry = self.ctx.map_lookup(abs_url)
            if entry is None:
                self.ctx.record_dropped_missing(
                    abs_url, f"{self.checkpoint}:{node.tag}@{attr}")
                return True
        return False

    def decide_removal(self, node: Node, text: str):
        tag = node.tag
        if self.missing_only_reference(node):
            return "missing-asset-reference"
        if tag == "link":
            rels = set((node.attrs.get("rel") or "").lower().split())
            href = html_unescape(node.attrs.get("href") or "")
            if rels & {"alternate", "search"} and REMOTE_URL_RE.match(href.strip()):
                return "remote-head-link"

        if tag in ("html", "head", "body"):
            return None
        if tag == "script":
            script_type = (node.attrs.get("type") or "").strip().lower()
            script_id = node.attrs.get("id")
            if script_type == "application/json" and script_id:
                content = text[node.tag_end:node.end_start]
                safe_id = re.sub(r"[^A-Za-z0-9._-]", "_", script_id)
                out = STATE_DIR / f"{self.checkpoint}.{safe_id}.json"
                out.write_text(content, encoding="utf-8", errors="surrogateescape")
                self.state_blobs.append(out.name)
                return "script_json_extracted"
            if self.tracker_keyword(node):
                return "script_tracker"
            return "script_src" if "src" in node.attrs else "script_inline"
        if tag == "noscript":
            return "noscript"
        if tag == "base":
            return "base_element"
        if tag == "link":
            rels = set((node.attrs.get("rel") or "").lower().split())
            href = html_unescape(node.attrs.get("href") or "")
            if rels & HINT_LINK_RELS:
                return "resource_hint_link"
            if "preload" in rels:
                as_value = (node.attrs.get("as") or "").lower()
                if as_value in ("script", "worker", "fetch", "track", "document",
                                "embed", "object", "audioworklet", "paintworklet",
                                "serviceworker", "sharedworker"):
                    return "resource_hint_link"
                abs_url = urljoin(self.page_url, href.strip()) if href.strip() else ""
                _, entry = self.ctx.map_lookup(abs_url)
                if entry is None:
                    return "resource_hint_link"
        if tag == "iframe":
            src = html_unescape(node.attrs.get("src") or "").strip()
            if REMOTE_URL_RE.match(src):
                return "external_iframe"
        kw = self.tracker_keyword(node)
        if kw:
            if tag == "img":
                return "tracking_pixel_img"
            return "tracker_element"
        return None

    # -- attribute rewriting -------------------------------------------------
    def rewrite_start_tag(self, node: Node) -> str | None:
        raw = node.raw
        edits: list[tuple[int, int, str]] = []
        strip_integrity = False
        meta_name = (node.attrs.get("name") or "").lower() if node.tag == "meta" else ""
        input_name = (node.attrs.get("name") or "").lower() if node.tag == "input" else ""

        for attr, value_raw, span, quote in scan_raw_attrs(raw):
            if value_raw is None or span is None:
                continue
            new_value = None
            value = html_unescape(value_raw)
            where = f"{self.checkpoint}:{node.tag}@{attr}"
            if attr == "ping":
                # tracking ping attribute: neutralize
                new_value = ""
                self.removals["tracking_ping_attr"] += 1
            elif node.tag == "meta" and attr == "content" and meta_name == "csrf-token":
                if value != CSRF_PLACEHOLDER:
                    new_value = CSRF_PLACEHOLDER
                    self.csrf_neutralized += 1
            elif node.tag == "input" and attr == "value" and input_name == "authenticity_token":
                if value != CSRF_PLACEHOLDER:
                    new_value = CSRF_PLACEHOLDER
                    self.csrf_neutralized += 1
            elif attr == "style":
                new_value, n = self.rewrite_inline_css(value, where)
                if n == 0:
                    new_value = None
            elif attr in ("srcset", "data-srcset"):
                new_value = self.rewrite_srcset(value, where)
            elif attr in ("src", "href", "poster", "action", "formaction", "data",
                          "background", "xlink:href") or attr in INERT_URL_ATTRS or (
                          attr.startswith("data-") and REMOTE_URL_RE.match(value.strip())):
                kind = position_kind(node.tag, attr, node.attrs)
                new_value = self.rewrite_url(value, kind, where)
                if new_value is not None and node.tag == "link" and attr == "href":
                    strip_integrity = True
            if new_value is not None and new_value != value:
                edits.append((span[0], span[1], html_escape_attr(new_value, quote)))

        if strip_integrity:
            for attr, value_raw, span, quote in scan_raw_attrs(raw):
                if attr in ("integrity", "crossorigin") and span is not None:
                    edits.append((span[0], span[1], ""))
        if not edits:
            return None
        edits.sort(key=lambda e: e[0], reverse=True)
        new_raw = raw
        for start, end, replacement in edits:
            new_raw = new_raw[:start] + replacement + new_raw[end:]
        return new_raw

    def rewrite_inline_css(self, css_text: str, where: str) -> tuple[str, int]:
        count = 0
        edits: list[tuple[int, int, str]] = []

        def handle(group_value: str, span: tuple[int, int]):
            nonlocal count
            candidate = group_value.strip()
            if not candidate or candidate.startswith(SKIP_SCHEMES):
                return
            abs_url = urljoin(self.page_url, candidate)
            if not abs_url.startswith(("http://", "https://")):
                return
            abs_url, entry = self.ctx.map_lookup(abs_url)
            if entry is not None:
                local = self.ctx.localize_asset(abs_url, entry)
                self.assets_rewritten += 1
            else:
                local = self.ctx.missing_path(abs_url, where)
                self.missing_rewritten += 1
            edits.append((span[0], span[1], local))
            count += 1

        for m in CSS_URL_RE.finditer(css_text):
            for group in ("dq", "sq", "bare"):
                if m.group(group) is not None:
                    handle(m.group(group), m.span(group))
                    break
        for m in CSS_IMPORT_RE.finditer(css_text):
            for group in ("dq", "sq"):
                if m.group(group) is not None:
                    handle(m.group(group), m.span(group))
                    break
        if not edits:
            return css_text, 0
        edits.sort(key=lambda e: e[0], reverse=True)
        out = css_text
        for start, end, replacement in edits:
            out = out[:start] + replacement + out[end:]
        return out, count

    def rewrite_srcset(self, value: str, where: str) -> str | None:
        candidates = []
        changed = False
        pos, n = 0, len(value)
        while pos < n:
            while pos < n and value[pos] in ", \t\n\r\f":
                pos += 1
            if pos >= n:
                break
            url_start = pos
            while pos < n and not value[pos].isspace():
                pos += 1
            url_token = value[url_start:pos]
            if url_token.endswith(","):
                # comma-terminated URL ends the candidate; no descriptor follows
                url = url_token.rstrip(",")
                descriptor = ""
            else:
                url = url_token
                desc_start = pos
                while pos < n and value[pos] != ",":
                    pos += 1
                descriptor = value[desc_start:pos].strip()
                pos += 1
            if not url:
                continue
            new_url = self.rewrite_url(url, "network", where)
            if new_url is not None:
                changed = True
                url = new_url
            candidates.append(url + ((" " + descriptor) if descriptor else ""))
        if not changed:
            return None
        return ", ".join(candidates)

    # -- main build -----------------------------------------------------------
    def build(self) -> str:
        text = self.source_path.read_bytes().decode("utf-8", "surrogateescape")
        nodes = parse_nodes(text)
        edits: list[tuple[int, int, str]] = []

        for node in nodes:
            if node.parent is not None and (node.parent.removed or node.parent.in_removed):
                node.in_removed = True
                continue
            category = self.decide_removal(node, text)
            if category:
                node.removed = True
                self.removals[category] += 1
                edits.append((node.start, node.end, ""))

        for node in nodes:
            if node.removed or node.in_removed:
                continue
            if node.tag == "title" and not self.title:
                self.title = html_unescape(text[node.tag_end:node.end_start]).strip()
            new_raw = self.rewrite_start_tag(node)
            if new_raw is not None:
                edits.append((node.start, node.tag_end, new_raw))
            if node.tag == "style" and node.end_start > node.tag_end:
                css_text = text[node.tag_end:node.end_start]
                new_css, n = self.rewrite_inline_css(
                    css_text, f"{self.checkpoint}:style-element")
                if n:
                    edits.append((node.tag_end, node.end_start, new_css))

        edits.sort(key=lambda e: (e[0], e[1]))
        for (s1, e1, _), (s2, _e2, _r) in zip(edits, edits[1:]):
            if e1 > s2:
                raise AssertionError(
                    f"overlapping edits in {self.checkpoint}: ({s1},{e1}) vs ({s2},..)")
        out = text
        for start, end, replacement in sorted(edits, key=lambda e: e[0], reverse=True):
            out = out[:start] + replacement + out[end:]

        idx = out.lower().rfind("</body>")
        if idx != -1:
            out = out[:idx] + INJECT_SCRIPT + out[idx:]
        else:
            out += INJECT_SCRIPT
        return MARKER + "\n" + DOCTYPE + "\n" + out


# --------------------------------------------------------------------------
# divergence + validation
# --------------------------------------------------------------------------

def tag_profile(text: str):
    tags = Counter()
    ids: set[str] = set()
    classes: set[str] = set()
    parser = OffsetHTMLParser(text)
    parser.feed(text)
    parser.close()
    for kind, tag, _s, _e, attrs, _raw in parser.events:
        if kind not in ("start", "startend"):
            continue
        tags[tag] += 1
        for name, value in attrs or []:
            if not value:
                continue
            if name == "id":
                ids.add(value)
            elif name == "class":
                classes.update(value.split())
    return tags, ids, classes


NOTABLE_CLASS_RE = re.compile(
    r"(mobile|desktop|nav|menu|drawer|hamburger|carousel|footer|header|sidebar|banner)", re.I)


def divergence_signal(desktop_path: Path, mobile_path: Path):
    d_text = desktop_path.read_bytes().decode("utf-8", "surrogateescape")
    m_text = mobile_path.read_bytes().decode("utf-8", "surrogateescape")
    d_tags, d_ids, d_classes = tag_profile(d_text)
    m_tags, m_ids, m_classes = tag_profile(m_text)
    deltas = {}
    for tag in set(d_tags) | set(m_tags):
        diff = d_tags[tag] - m_tags[tag]
        if diff:
            deltas[tag] = diff
    top = dict(sorted(deltas.items(), key=lambda kv: (-abs(kv[1]), kv[0]))[:8])
    only_d = sorted(d_ids - m_ids)[:6]
    only_m = sorted(m_ids - d_ids)[:6]
    class_d = sorted(c for c in (d_classes - m_classes) if NOTABLE_CLASS_RE.search(c))[:6]
    class_m = sorted(c for c in (m_classes - d_classes) if NOTABLE_CLASS_RE.search(c))[:6]
    return {
        "desktop_tag_total": sum(d_tags.values()),
        "mobile_tag_total": sum(m_tags.values()),
        "tag_count_delta": sum(d_tags.values()) - sum(m_tags.values()),
        "top_tag_deltas": top,
        "ids_only_in_desktop": only_d,
        "ids_only_in_mobile": only_m,
        "notable_classes_only_in_desktop": class_d,
        "notable_classes_only_in_mobile": class_m,
    }


def validate_page(text: str, checkpoint: str):
    """Scan a built page for leftover remote refs and classify them."""
    forbidden: list[dict] = []
    allowed_nav = 0
    inert: list[dict] = []
    text_refs = 0
    parser = OffsetHTMLParser(text)
    parser.feed(text)
    parser.close()
    for kind, tag, s, e, attrs, raw in parser.events:
        if kind in ("data", "comment"):
            text_refs += len(ABS_HTTP_RE.findall(text[s:e]))
            continue
        if kind not in ("start", "startend"):
            continue
        attr_dict = {}
        for name, value in attrs or []:
            attr_dict.setdefault(name.lower(), value)
        if tag == "script":
            src = attr_dict.get("src") or ""
            if src != "/static/site/hb-app.js":
                forbidden.append({"tag": "script", "attr": "element",
                                  "url": src or "(inline script survived)"})
            continue
        for name, value in attrs or []:
            if not value:
                continue
            name = name.lower()
            value_unescaped = html_unescape(value)
            stripped = value_unescaped.strip()
            if name == "style":
                for m in CSS_URL_RE.finditer(value_unescaped):
                    inner = (m.group("dq") or m.group("sq") or m.group("bare") or "").strip()
                    if REMOTE_URL_RE.match(inner):
                        forbidden.append({"tag": tag, "attr": name, "url": inner})
                continue
            if not REMOTE_URL_RE.match(stripped):
                if ABS_HTTP_RE.search(value_unescaped):
                    bucket = "event_handler" if name.startswith("on") else "embedded"
                    inert.append({"tag": tag, "attr": name, "kind": bucket,
                                  "url": value_unescaped[:120]})
                continue
            if tag == "meta" and name == "content" and \
                    (attr_dict.get("http-equiv") or "").lower() == "refresh":
                forbidden.append({"tag": tag, "attr": name, "url": stripped})
                continue
            kind_pos = position_kind(tag, name, attr_dict)
            if kind_pos == "network":
                forbidden.append({"tag": tag, "attr": name, "url": stripped[:200]})
            elif kind_pos == "nav":
                allowed_nav += 1
            else:
                inert.append({"tag": tag, "attr": name, "kind": "inert", "url": stripped[:120]})

    # <style> element contents
    nodes = parse_nodes(text)
    for node in nodes:
        if node.tag == "style" and node.end_start > node.tag_end:
            css_text = text[node.tag_end:node.end_start]
            for m in CSS_URL_RE.finditer(css_text):
                inner = (m.group("dq") or m.group("sq") or m.group("bare") or "").strip()
                if REMOTE_URL_RE.match(inner):
                    forbidden.append({"tag": "style", "attr": "css-url", "url": inner[:200]})
            for m in CSS_IMPORT_RE.finditer(css_text):
                inner = (m.group("dq") or m.group("sq") or "").strip()
                if REMOTE_URL_RE.match(inner):
                    forbidden.append({"tag": "style", "attr": "css-import", "url": inner[:200]})
        if node.tag == "noscript":
            forbidden.append({"tag": "noscript", "attr": "element", "url": "(survived)"})
    return forbidden, allowed_nav, inert, text_refs


# --------------------------------------------------------------------------
# orchestration
# --------------------------------------------------------------------------

def prune_outputs(expected_pages: set[str]):
    if PAGES_DIR.exists():
        for f in PAGES_DIR.glob("*.html"):
            if f.stem not in expected_pages:
                f.unlink()
    if STATE_DIR.exists():
        for f in STATE_DIR.glob("*.json"):
            f.unlink()


def runtime_asset_names() -> set[str]:
    """Asset filenames referenced at runtime rather than by a frozen page.

    The seed's product and bundle media, and the mobile fixup fragments, are
    fetched by the interaction layer from JSON. They appear in no frozen page,
    so pruning on page references alone deletes every product gallery on disk.
    """

    names: set[str] = set()

    def collect(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "local" and isinstance(value, str):
                    if value.startswith(ASSET_URL_PREFIX):
                        names.add(value[len(ASSET_URL_PREFIX):])
                else:
                    collect(value)
        elif isinstance(node, list):
            for value in node:
                collect(value)
        elif isinstance(node, str) and node.startswith(ASSET_URL_PREFIX):
            names.add(node[len(ASSET_URL_PREFIX):])

    for candidate in (CLONE_DIR / "backend" / "seed_data.json",
                      CLONE_DIR / "static" / "site" / "mobile-fixups.json"):
        if candidate.is_file():
            try:
                collect(json.loads(candidate.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
    return {n for n in names if "/" not in n}


def prune_assets(produced: set[str]):
    keep = produced | runtime_asset_names()
    for f in ASSET_DIR.iterdir():
        if f.is_file() and re.fullmatch(r"[0-9a-f]{64}(\.[a-z0-9]+)?", f.name) \
                and f.name not in keep:
            f.unlink()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-dir", type=Path, default=DEFAULT_RUN,
                    help="capture run directory (default: %(default)s)")
    args = ap.parse_args(argv)
    run_dir: Path = args.run_dir

    url_map = json.loads((run_dir / "assets" / "url-map.json").read_text(encoding="utf-8"))
    ctx = BuildContext(run_dir, url_map)

    for d in (ASSET_DIR, PAGES_DIR, STATE_DIR, SITE_JS.parent):
        d.mkdir(parents=True, exist_ok=True)
    prune_outputs({cp for cp, _r, _c in PAGES})

    if not SITE_JS.exists():
        SITE_JS.write_text(
            "/*\n"
            " * websitebench humble-bundle frozen frontend runtime placeholder.\n"
            " * Every frozen page loads this file as /static/site/hb-app.js.\n"
            " * Intentionally empty at freeze time; page interactions are wired\n"
            " * up in a later phase of the clone pipeline.\n"
            " */\n",
            encoding="utf-8",
        )

    report_pages: dict[str, dict] = {}
    manifest: dict[str, dict] = {}
    totals_removals: Counter = Counter()
    total_forbidden = 0

    for checkpoint, route, cell in PAGES:
        builder = PageBuilder(ctx, checkpoint, route, cell)
        out_text = builder.build()
        out_path = PAGES_DIR / f"{checkpoint}.html"
        out_path.write_text(out_text, encoding="utf-8", errors="surrogateescape")

        forbidden, allowed_nav, inert, text_refs = validate_page(out_text, checkpoint)
        total_forbidden += len(forbidden)
        totals_removals.update(builder.removals)

        page_missing = sorted(
            (url, sorted(w for w in rec["wheres"] if w.startswith(f"{checkpoint}:")))
            for url, rec in ctx.missing.items()
            if any(w.startswith(f"{checkpoint}:") for w in rec["wheres"])
        )

        static_cell = run_dir / "static" / checkpoint
        divergence = None
        d_dom = static_cell / "desktop" / "dom.html"
        m_dom = static_cell / "mobile" / "dom.html"
        if d_dom.exists() and m_dom.exists():
            divergence = divergence_signal(d_dom, m_dom)

        report_pages[checkpoint] = {
            "route": route,
            "file": f"clone/frontend/pages/{checkpoint}.html",
            "source_cell": f"{cell}/dom.html",
            "source_url": builder.page_url,
            "assets_rewritten": builder.assets_rewritten,
            "missing_asset_refs_rewritten": builder.missing_rewritten,
            "page_links_rewritten": builder.page_links_rewritten,
            "csrf_values_neutralized": builder.csrf_neutralized,
            "removals": dict(sorted(builder.removals.items())),
            "state_blobs_extracted": sorted(builder.state_blobs),
            "missing_assets": [{"url": u, "where": w} for u, w in page_missing],
            "forbidden_remote_refs": forbidden,
            "allowed_remote_refs": {
                "navigation_links": allowed_nav,
                "inert_attribute_refs": len(inert),
                "text_or_comment_refs": text_refs,
            },
            "inert_remote_ref_samples": inert[:10],
            "desktop_vs_mobile_divergence": divergence,
        }
        manifest[checkpoint] = {
            "route": route,
            "file": f"pages/{checkpoint}.html",
            "title": builder.title,
            "source_cell": f"{cell}/dom.html",
        }

    produced_assets = {p[len(ASSET_URL_PREFIX):] for p in ctx.provenance}
    prune_assets(produced_assets)

    # final sweep: no remote url() left inside any shipped css asset
    css_leftovers = []
    for local, info in sorted(ctx.provenance.items()):
        if not local.endswith(".css"):
            continue
        css_text = (CLONE_DIR / "static" / "assets" / local[len(ASSET_URL_PREFIX):]) \
            .read_bytes().decode("utf-8", "surrogateescape")
        for m in CSS_URL_RE.finditer(css_text):
            inner = (m.group("dq") or m.group("sq") or m.group("bare") or "").strip()
            if REMOTE_URL_RE.match(inner):
                css_leftovers.append({"asset": local, "url": inner[:200]})

    provenance_sorted = {k: ctx.provenance[k] for k in sorted(ctx.provenance)}
    PROVENANCE_PATH.write_text(
        json.dumps(provenance_sorted, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")
    (CLONE_DIR / "frontend" / "external-links.json").write_text(
        json.dumps({k: ctx.external_links[k] for k in sorted(ctx.external_links)},
                   indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")

    localized_bytes = sum(v["bytes"] for v in ctx.provenance.values())
    report = {
        "builder": "materials/humble-bundle/tools/build_frozen_pages.py",
        "run": run_dir.name,
        "notes": [
            "deterministic re-runnable build; no network, no browser",
            "serialized DOM captures carry no doctype; '<!DOCTYPE html>' is injected "
            "after the websitebench-frozen marker to preserve standards-mode rendering",
            "csrf-token meta values and authenticity_token inputs are neutralized to a "
            "fixed placeholder",
            "missing assets are rewritten to /static/assets/missing/<sha1-of-url><ext> "
            "and listed here for a follow-up capture pass (never fetched by this tool)",
        ],
        "pages": report_pages,
        "dropped_missing_references": [
            {"url": u, "where": sorted(w)}
            for u, w in sorted(ctx.dropped_missing.items())
        ],
        "missing_assets_all": [
            {
                "url": url,
                "local_path": rec["path"],
                "host_scope": host_scope(url),
                "wheres": sorted(rec["wheres"]),
            }
            for url, rec in sorted(ctx.missing.items())
        ],
        "totals": {
            "pages_built": len(report_pages),
            "assets_localized": len(ctx.provenance),
            "assets_localized_bytes": localized_bytes,
            "css_assets_transformed": ctx.css_transformed,
            "css_url_rewrites": ctx.css_url_rewrites,
            "missing_assets_unique_urls": len(ctx.missing),
            "state_blobs_extracted": int(totals_removals.get("script_json_extracted", 0)),
            "forbidden_remote_refs_total": total_forbidden,
            "css_remote_url_leftovers": css_leftovers,
            "removals_by_category": dict(sorted(totals_removals.items())),
        },
    }
    (run_dir / "frozen-build-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")

    print(f"pages built: {len(report_pages)}")
    print(f"assets localized: {len(ctx.provenance)} ({localized_bytes} bytes)")
    print(f"css transformed: {ctx.css_transformed} (url rewrites: {ctx.css_url_rewrites})")
    print(f"missing asset urls: {len(ctx.missing)}")
    print(f"forbidden remote refs: {total_forbidden}")
    if total_forbidden or css_leftovers:
        print("VALIDATION FAILED", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
