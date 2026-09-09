"""Turn captured monoprice pages into pages the clone can serve offline.

What this does, in order, per page: rewrite every reference that points off this
machine, strip the third-party tags, and write the result under
`clone/static/frozen/<route>.html`.

Four rules here were each bought with a day somewhere else in this family:

1. **An attribute value runs to its own delimiting quote.** Writing the value
   class as `[^"']*` looks right and is not: a double-quoted attribute may
   legally contain an apostrophe, and this catalogue is full of them. The whole
   attribute then fails to match -- and an attribute that does not match is not
   counted as unresolved, it is not counted at all. The report stays silent
   while the page keeps requesting a CDN.

2. **Decide by the value, not by the attribute name.** Enumerating `src`,
   `href`, `poster`, `srcset`, `data-src`, ... never terminates, and `\\b(href)`
   quietly matches the `href` inside `data-href`. The question is only ever
   "is this value an absolute URL to somewhere else".

3. **Never repoint a reference at a file that is not on disk.** Rewriting to a
   local path that 404s converts a remote request into a local one and reports
   it as closure. Every rewrite is checked against the asset tree.

4. **A stripped tag leaves nothing behind that is still a request.** `src=""`
   makes the browser re-request the current page; an id concatenated onto an
   empty base makes it request `/GTM-XXXX`. Placeholders are chosen per element,
   not per attribute.

The belt-and-braces measure is a `Content-Security-Policy: default-src 'self'`
header served by the app. Widening a strip list is a race against the next
injection technique; the header refuses the request before it leaves.

    python3 tools/build_frozen_pages.py --capture-dir source-current \
        --assets-dir source-assets --catalogue data/catalogue.json \
        --out-root clone/static/frozen --report scope/frozen-pages.json
"""

from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import json
import pathlib
import re
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from capture_pages import read_body  # noqa: E402
from fetch_assets import WEBFLOW_HOSTS, asset_target  # noqa: E402

LOCAL_ASSET_PREFIX = "/static/assets"

# Rule 1. The value runs to the *delimiting* quote. `(?:(?!(?P=q)).)*` is the
# whole point of this pattern; do not "simplify" it to [^"']*.
URL_ATTR_SPAN = re.compile(
    r"""(?P<attr>[\w:.-]+)(?P<eq>\s*=\s*)(?P<q>["'])(?P<v>(?:(?!(?P=q)).)*)(?P=q)""",
    re.I | re.S)

CSS_URL = re.compile(r"""url\(\s*(?P<q>['"]?)(?P<v>[^)'"]+)(?P=q)\s*\)""", re.I)

ABSOLUTE = re.compile(r"^(?:https?:)?//", re.I)

# An absolute URL to a host we hold, written anywhere in the document -- in a
# script, in embedded JSON, with slashes escaped as `\/` or not. Deliberately
# narrow: only the hosts whose bytes are local, so this cannot rewrite text it
# does not understand.
BARE_ABSOLUTE = re.compile(
    r"https?:(?:\\?/){2}(?:images\.monoprice\.com|www\.monoprice\.com|"
    r"cdn\.prod\.website-files\.com)"
    # The path: an escaped slash, or any character that is not a delimiter.
    # Writing this as `(?:\\?/[^...])+` consumed a slash plus exactly one
    # character per repetition, so every match stopped one character into the
    # path -- and a pattern that matches a prefix rewrites the wrong thing.
    r"(?:\\/|[^\s\"'<>()\\])+",
    re.I)

# Hosts whose bytes we hold locally. The Webflow set is here because 3,328 pages
# of this site are a Webflow build whose entire visual layer lives there; see
# fetch_assets.WEBFLOW_HOSTS.
LOCAL_HOSTS = ({"www.monoprice.com", "monoprice.com", "images.monoprice.com"}
               | WEBFLOW_HOSTS)

# Third-party tags removed wholesale. Everything here was observed loading on a
# captured page; nothing is speculative.
THIRD_PARTY_HOST_HINTS = (
    "googletagmanager", "google-analytics", "googleadservices", "doubleclick",
    "google.com/recaptcha", "gstatic.com/recaptcha", "facebook.net",
    "facebook.com/tr", "bat.bing.com", "snap.licdn.com", "px.ads.linkedin",
    "redditstatic", "alb.reddit", "criteo", "amazon-adsystem", "hotjar",
    "listrakbi", "listrak", "lt02.net", "hs-scripts", "hs-analytics",
    "hs-banner", "hsadspixel", "usemessages", "hubapi", "hubspot",
    "cookielaw.org", "onetrust", "adobedtm", "omtrdc.net", "demdex",
    "px-cloud.net", "px-cdn.net", "perimeterx", "affirm.com", "five9.net",
    "nagich.com", "apollo.io", "aplo-evnt", "liadm.com", "cloudflareinsights",
    "wra-api.net", "sitemaphosting", "kayako", "scanalert", "trustkeeper",
    "truste.com", "unbxd", "capi-automation",
    # Named exactly, not as "cloudfront.net". That substring also matches
    # Webflow's jQuery host, and stripping it would have taken the script layer
    # off 3,328 pages while the strip report happily counted it as a third party
    # removed.
    "d21gpk1vhmjuf5.cloudfront.net", "d3m8huu8gvuyn3.cloudfront.net",
)

# First-party paths that exist only to proxy a third party. A remote-request
# audit is structurally blind to these -- the request never leaves the origin --
# so they have to be named here.
FIRST_PARTY_TRACKER_PATHS = ("/securemetrics/", "/CommissionJunction/",
                             "/cdn-cgi/")

SCRIPT_TAG = re.compile(r"<script\b[^>]*>.*?</script>|<script\b[^>]*/?>",
                        re.I | re.S)
LINK_TAG = re.compile(r"<link\b[^>]*>", re.I)
IFRAME_TAG = re.compile(r"<iframe\b[^>]*>.*?</iframe>|<iframe\b[^>]*/?>", re.I | re.S)
NOSCRIPT_TAG = re.compile(r"<noscript\b[^>]*>.*?</noscript>", re.I | re.S)
IMG_TAG = re.compile(r"<img\b[^>]*>", re.I)

# HawkSearch ships every listing with BOTH result containers hidden and lets its
# hosted script reveal the right one:
#
#   <div style="padding-top: 15px; display: none;" id="existresult">   <- results
#   <div style="... display: none; ..." id="noresult">                 <- empty state
#
# That script is third-party and stripped, so neither was ever revealed. The
# consequence was severe and completely invisible to every gate: a category page
# carried 165 product links and showed **none** of them, and a search page 316.
# Markup present, references closed, no requests, no errors, 4,910 CSS rules in
# force -- and a blank page.
#
# The page itself carries the fact the script was deciding on: whether it has
# product tiles. So the decision is made here from that, deterministically.
RESULTS_CONTAINER = re.compile(
    r"""(<div\b[^>]*\bid\s*=\s*["'](?P<which>existresult|noresult)["'][^>]*>)""",
    re.I)
HIDDEN_DECL = re.compile(r"display\s*:\s*none\s*;?", re.I)


def reveal_results_container(html: str, tally: collections.Counter) -> str:
    """Reveal whichever container the stripped script would have revealed."""
    if "existresult" not in html:
        return html
    has_products = re.search(r"p_id=\d+", html) is not None
    wanted = "existresult" if has_products else "noresult"

    def repl(m: re.Match) -> str:
        tag = m.group(1)
        if m.group("which").lower() != wanted:
            return tag
        # Only touch the inline display declaration; leave the rest of the
        # style attribute exactly as the source wrote it.
        opened = HIDDEN_DECL.sub("display: block;", tag)
        if opened != tag:
            tally[f"results_container_revealed:{wanted}"] += 1
        return opened

    return RESULTS_CONTAINER.sub(repl, html)

# The facet sidebar toggle is NOT missing -- do not shim it.
#
# A shim was written here and it broke a working control. The page carries the
# site's own first-party inline handler, and it survives third-party stripping
# because it is the site's, not HawkSearch's:
#
#     $(document).ready(function () {
#       $(".hawk-groupHeading").on('click', function () {
#         if ($(this).hasClass("plus")) {
#           $(this).removeClass("plus").addClass("minus");
#           $(this).next().slideDown('fast', 'linear');
#         } else if ($(this).hasClass("minus")) { ... slideUp ... }
#       });
#     });
#
# jQuery binds to the element, so its handler runs before a delegated one on
# `document`. The shim then read `display` mid-slideDown, saw `block`, concluded
# the panel was open, and closed it. One click, two handlers, net effect nil --
# and the evidence for it was an inline style caught mid-animation:
#
#     overflow: hidden; height: 3.84843px; padding-top: 0.15px; display: block
#
# The rule this cost: **measure whether a control works before supplying it.**
# Everything else shimmed in this file was verified broken first -- the results
# containers were `display:none` with no script left to reveal them, the
# stripped globals threw ReferenceError by name. This one was assumed from the
# user's report that "the box on the left does not work either", which was
# really the search page showing no results at all.


# The search box does not submit without this.
#
# Measured side by side: identical markup on both, and pressing Enter navigates
# to /search/index?keyword=... on the source while the clone stays on the page.
# The source's own script swallows the keypress and hands the query to Unbxd's
# autosuggest bundle, which does the navigating -- and that bundle is a third
# party, stripped like every other. So the site's most-used control was dead,
# and no load-time gate could see it: nothing errors, nothing is requested, the
# page simply does not change.
#
# This restores the *observable behaviour*, not the mechanism: the form already
# declares GET /search/index with the right field name, so submitting it
# natively produces exactly the URL the source produces. Registered in the
# capture phase so it runs before the handler that calls preventDefault.
# Removing a third party can break first-party code that assumes its global
# exists. Stripping Google Tag Manager took `dataLayer` with it, and this site's
# own commerce code pushes to `dataLayer` inside the add-to-cart chain -- so the
# chain threw `dataLayer is not defined` before it could render, and the Add to
# Cart control did nothing.
#
# The error is not visible to a console listener: it surfaces as a pageerror
# from a rejected jQuery promise. Nothing in the network log looked wrong
# either; every request in the chain returned 200.
#
# This declares the empty array the code expects. It is a shim, not analytics:
# pushes land in an array that nothing reads and nothing transmits. It goes
# first in <head> so it is defined before any of the site's own scripts run.
STRIPPED_GLOBALS_SHIM = """<script data-wb-stripped-globals="1">
window.dataLayer = window.dataLayer || [];
window._satellite = window._satellite || {
  track: function () {}, notify: function () {},
  setVar: function () {}, getVar: function () {},
  pageBottom: function () {}, logger: {log: function () {}}
};
window.F9 = window.F9 || {Chat: {Wrapper: {init: function () {}}}};
</script>"""

# Three globals, all belonging to stripped third parties, all depended on by the
# site's *own* inline code:
#
#   dataLayer   -- Google Tag Manager
#   _satellite  -- Adobe Launch
#   F9          -- Five9 live chat; every page ends with an inline
#                  `F9.Chat.Wrapper.init({cdn: 'prod', ...})` call
#
# F9 was found by comparing thrown errors between the clone and the source
# rather than by reading the clone's console, which matters: the source throws
# `$(...).hasAttribute is not a function` and `swiper.enable is not a function`
# on its own product page, so a clone console full of errors is not evidence of
# a clone defect. Only `F9 is not defined` appeared on one side and not the
# other. Measure the source before calling an error yours.
#
# `MPI.ee.addToCart` calls `_satellite.track(...)`, and it runs *before*
# `render(results)` in the add-to-cart chain. So the ReferenceError stopped the
# chain one step short: the item was added, the cart page showed it, and the
# header badge and mini-cart never updated. Hand-running the chain step by step
# was what found it -- the network log was all 200s and the console listener saw
# nothing, because a throw inside a jQuery `.then` becomes a silent rejection.
#
# The method list is read from the site's own code (`_satellite.track` in the
# product pages, `_satellite.notify` in a bundle), not guessed. These are no-ops:
# they accept the call and discard it. Nothing is recorded and nothing is sent.

SEARCH_SUBMIT_FIX = """<script data-wb-search-submit="1">
(function () {
  function wire() {
    var form = document.querySelector('form[action="/search/index"]');
    if (!form) { return; }
    var field = form.querySelector('input[name="keyword"]');
    if (!field) { return; }
    field.addEventListener('keydown', function (event) {
      if (event.key !== 'Enter') { return; }
      event.stopImmediatePropagation();
      event.preventDefault();
      var term = (field.value || '').trim();
      if (!term) { return; }
      // URLSearchParams, not encodeURIComponent: a native form GET encodes a
      // space as "+" and encodeURIComponent gives "%20". The source produces
      // keyword=hdmi+cable, and a candidate that submits the form natively
      // would too -- so emitting %20 here would make the reference URL differ
      // from a correct rebuild's for no reason but this shim.
      var query = new URLSearchParams({keyword: term}).toString();
      window.location.href = '/search/index?' + query;
    }, true);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }
})();
</script>"""

# Rule 2 says decide by the value, not the attribute name. That is right about
# which *references* to rewrite and wrong as a licence to rewrite every
# attribute: `type="text/css"` looks exactly like a relative path, and it was
# resolved against the page URL into `type="/category/cables/hdmi-cables/text/css"`.
# A <link> whose type is not text/css is ignored by the browser, and a <script>
# whose type is not a JavaScript type does not execute -- so this one heuristic
# silently disabled a stylesheet and a script layer across every frozen page,
# while the rewrite counters happily counted each one as "localised".
#
# Two guards, because either alone is insufficient: attributes that never hold a
# fetchable URL, and values that are bare MIME types.
NON_URL_ATTRS = {
    "type", "rel", "media", "charset", "hreflang", "lang", "sizes", "as",
    "crossorigin", "integrity", "referrerpolicy", "method", "enctype", "accept",
    "accept-charset", "target", "role", "class", "id", "name", "style", "align",
    "valign", "itemtype", "itemprop", "property", "content", "value", "alt",
    "title", "placeholder", "pattern", "autocomplete", "for", "headers",
    "aria-label", "aria-labelledby", "aria-describedby", "data-command",
}
MIME_VALUE = re.compile(
    r"^(?:text|image|audio|video|application|font|model|multipart|message)/"
    r"[A-Za-z0-9.+-]+$", re.I)
# A 1x1 fully transparent GIF. Renders nothing, requests nothing.
TRANSPARENT_PIXEL = ("data:image/gif;base64,"
                     "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")

# Subresource Integrity has to go, because we deliberately break it.
#
# The Webflow pages ship their stylesheets with an SRI hash:
#
#   <link href=".../monoprice-pseo-products...opt.min.css"
#         integrity="sha384-..." crossorigin="anonymous">
#
# `patch_served_assets.py` rewrites the absolute URLs *inside* those CSS files
# so they point at local copies. That changes the bytes, so the hash no longer
# matches and the browser discards the stylesheet -- silently as far as every
# gate here is concerned: status 200, no remote request, no same-origin failure,
# no console error the audit was listening for. The visible result was a Webflow
# page holding 1,079 CSS rules where its siblings hold 4,910, which is to say a
# page with almost no styling.
#
# Keeping the attribute would only be honest if we kept the bytes. We do not, so
# the attribute is removed rather than recomputed: a recomputed hash would assert
# integrity against our own rewrite, which protects nothing offline.
SRI_ATTRS = re.compile(
    r"""\s+(?:integrity|crossorigin)\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)""", re.I)
SUBRESOURCE_TAG = re.compile(r"<(?:link|script)\b[^>]*>", re.I)


def strip_subresource_integrity(html: str, tally: collections.Counter) -> str:
    """Drop SRI attributes from link/script tags whose bytes we rewrite."""
    if "integrity" not in html.lower():
        return html

    def repl(m: re.Match) -> str:
        tag = m.group(0)
        stripped = SRI_ATTRS.sub("", tag)
        if stripped != tag:
            tally["sri_stripped"] += 1
        return stripped

    return SUBRESOURCE_TAG.sub(repl, html)


def is_third_party(value: str) -> bool:
    low = value.lower()
    if any(h in low for h in THIRD_PARTY_HOST_HINTS):
        return True
    return any(p.lower() in low for p in FIRST_PARTY_TRACKER_PATHS)


def url_is_third_party(value: str) -> bool:
    """Third party decided by the URL's HOST, not by text anywhere in it.

    `is_third_party` is a substring test, and the hint list holds bare vendor
    names -- "unbxd", "onetrust", "hotjar". Applied to a whole URL it strips
    first-party files whose *filename* mentions the vendor:

        https://www.monoprice.com/assets/css/mp_unbxd_search.css   541 rules
        https://www.monoprice.com/assets/js/hawksearchproxy.js

    That stylesheet is monoprice's own, it styles the search results, and losing
    it is why the category and search pages held 4,357 CSS rules against the
    source's 5,863. The vendor's name in a filename says who the file is *for*,
    not who serves it.

    Some hints legitimately carry a path (`facebook.com/tr`,
    `google.com/recaptcha`), so the test runs against host+path -- but only once
    the host is known not to be ours.
    """
    raw = value.strip()
    if not raw:
        return False
    try:
        parsed = urllib.parse.urlsplit(
            raw if "//" in raw[:8] else urllib.parse.urljoin("https://x.invalid/", raw))
    except ValueError:
        # `urlsplit` raises "Invalid IPv6 URL" on a token with an unbalanced
        # bracket, and inline scripts are full of things that look like URLs and
        # are not -- `//[object Object]`, template fragments, commented-out code.
        # An unparseable token cannot be a working request, so it is kept rather
        # than treated as a third party and deleted along with its whole tag.
        return False
    host = (parsed.netloc or "").lower().split("@")[-1].split(":")[0]
    path = (parsed.path or "").lower()

    # A first-party path that proxies a third party is still a third party, and
    # this is the only case where the path alone decides.
    if any(p.lower() in path for p in FIRST_PARTY_TRACKER_PATHS):
        return True
    if not host or host == "x.invalid" or host in LOCAL_HOSTS:
        return False
    return any(h in f"{host}{path}" for h in THIRD_PARTY_HOST_HINTS)


class Localiser:
    """Rewrites one page's references and keeps a per-reason tally."""

    def __init__(self, assets_dir: pathlib.Path, base_url: str,
                 served_routes: set[str], served_products: set[str]):
        self.assets_dir = assets_dir
        self.base_url = base_url
        self.served_routes = served_routes
        self.served_products = served_products
        self.tally: collections.Counter = collections.Counter()
        self.unresolved: list[str] = []

    # -- assets ---------------------------------------------------------- #
    def local_asset(self, absolute: str) -> str | None:
        target = asset_target(absolute)
        if target is None:
            return None
        host, local = target
        # Rule 3: only repoint at bytes that are actually here.
        if not (self.assets_dir / host / local).exists():
            self.tally["asset_missing_on_disk"] += 1
            self.unresolved.append(absolute)
            return None
        return f"{LOCAL_ASSET_PREFIX}/{host}/{urllib.parse.quote(local)}"

    # -- routes ---------------------------------------------------------- #
    def local_route(self, absolute: str) -> str | None:
        u = urllib.parse.urlsplit(absolute)
        if u.netloc and u.netloc.lower() not in LOCAL_HOSTS:
            return None
        path = u.path.lower() or "/"
        query = u.query
        if path.startswith("/product"):
            pid = dict(urllib.parse.parse_qsl(query)).get("p_id")
            if pid is None:
                return None
            if pid not in self.served_products:
                # A tile advertising a product the clone cannot serve is worse
                # than an absent tile: the link resolves and the page 404s.
                self.tally["route_product_not_served"] += 1
                return ""
            return f"/product?p_id={pid}"
        keep = [(k, v) for k, v in urllib.parse.parse_qsl(query)
                if k.lower() not in {"page", "page_type", "location_type",
                                     "start_date", "promo_type"}]
        rebuilt = urllib.parse.urlencode(keep)
        return f"{path}?{rebuilt}" if rebuilt else path

    def rewrite_value(self, value: str) -> str | None:
        """None means 'leave alone'; '' means 'this reference must go'."""
        raw = value.strip()
        if not raw or raw.startswith(("data:", "javascript:", "mailto:", "tel:",
                                      "#", "{{", "${")):
            return None
        if url_is_third_party(raw):
            self.tally["third_party_reference_removed"] += 1
            return ""
        absolute = urllib.parse.urljoin(self.base_url, raw.replace("&amp;", "&"))
        u = urllib.parse.urlsplit(absolute)
        if u.scheme not in ("http", "https"):
            return None
        if u.netloc.lower() not in LOCAL_HOSTS:
            self.tally["offsite_reference_removed"] += 1
            return ""
        local = self.local_asset(absolute)
        if local is not None:
            self.tally["asset_localised"] += 1
            return local
        route = self.local_route(absolute)
        if route is not None:
            if route:
                self.tally["route_localised"] += 1
            return route
        if ABSOLUTE.match(raw) or raw.startswith("http"):
            self.tally["same_host_absolute_made_relative"] += 1
            return u.path + (f"?{u.query}" if u.query else "")
        return None


# A host hint has to match a URL, not prose.
#
# `is_third_party` tests for substrings like "unbxd" and "onetrust", and
# `strip_third_party_tags` was applying it to the **entire text of an inline
# script**. The site's own product page carries:
#
#     <script> var unbxdVersionValue = 2; </script>
#     <script>
#       $(document).ready(function () {
#         productPageStuff.initialize({"p_id":"10149","cust_review":0,
#                                      "unbxdVersion":2});
#       });
#     </script>
#
# Both contain the substring `unbxd`, so both were deleted as third party. That
# call is the only thing that starts the product page's content fills, so every
# product page lost its recommendation carousels AND its tab panels -- the specs
# and description that are most of the page's text. Measured against the source:
# 920 characters rendered against 7,134, and 1 product tile against 35.
#
# This is the third time on this site that a substring test has eaten
# first-party code. `cloudfront.net` took Webflow's jQuery off 3,328 pages until
# the hints were narrowed to exact hostnames; a fast path that checked for
# `monoprice.com/` skipped every Webflow file before its own pattern could run.
# The rule that keeps being relearned: **match the thing, not text that happens
# to contain the thing's name.**
#
# So a tag is third party when a *URL inside it* points at a third party, or an
# attribute points at a first-party tracker proxy. An inline script that merely
# mentions a vendor is the site's own code calling into that vendor -- which is
# exactly what the stripped-globals shim exists to keep working.
URL_IN_TAG = re.compile(r"""(?:https?:)?//[^\s"'<>()\\]{4,}""", re.I)


# A hostname written in code, with a real TLD.
#
# Inline loaders assemble their URL at run time, so no complete URL literal
# exists for the URL test to find. Google Optimize's is the one that got through:
#
#   d.write('<sc' + 'ript src="' + 'http'
#           + (l.protocol == 'https:' ? 's://ssl' : '://www')
#           + '.google-analytics.com/ga_exp.js?' + 'utmxkey=' + k
#           + '&utmxtime=' + new Date().valueOf() + ...);
#
# Keeping it put 114 remote requests back into a clone that had none. The old
# substring test caught this by accident, and narrowing to hosts lost it -- so
# the text is searched for hostname *tokens*, which is what a substring test
# should have been doing all along.
#
# Requiring a real TLD is what keeps this from eating first-party code again:
# `unbxdVersion` has no dot, and `mp_unbxd_search.css` ends in `.css`, so
# neither is a hostname and neither matches.
HOSTNAME_IN_TEXT = re.compile(
    r"\b[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*"
    r"\.(?:com|net|org|io|co|tv|cloud|app|ai|uk|de)\b", re.I)


def tag_is_third_party(tag_text: str) -> bool:
    for m in URL_IN_TAG.finditer(tag_text):
        if url_is_third_party(m.group(0)):
            return True
    for m in HOSTNAME_IN_TEXT.finditer(tag_text):
        host = m.group(0).lower()
        if host in LOCAL_HOSTS:
            continue
        if any(h in host for h in THIRD_PARTY_HOST_HINTS):
            return True
    for m in URL_ATTR_SPAN.finditer(tag_text):
        value = m.group("v")
        if any(p.lower() in value.lower() for p in FIRST_PARTY_TRACKER_PATHS):
            return True
        if url_is_third_party(value):
            return True
    return False


def strip_third_party_tags(html: str, tally: collections.Counter) -> str:
    def drop_if_third_party(pattern: re.Pattern, label: str, text: str) -> str:
        def repl(m: re.Match) -> str:
            if tag_is_third_party(m.group(0)):
                tally[label] += 1
                return ""
            return m.group(0)
        return pattern.sub(repl, text)

    html = drop_if_third_party(SCRIPT_TAG, "script_removed", html)
    html = drop_if_third_party(LINK_TAG, "link_removed", html)
    html = drop_if_third_party(IFRAME_TAG, "iframe_removed", html)
    # A <noscript> body is inert markup until scripting is off, and its contents
    # are pixels. grep says these pages "load GTM"; the browser says they do not.
    # Removing them keeps a static scan from reporting a leak that is not one.
    html = drop_if_third_party(NOSCRIPT_TAG, "noscript_removed", html)
    return html


def family_of(url: str) -> str:
    """Which page family a URL belongs to, matching discover_runtime_assets."""
    split = urllib.parse.urlsplit(url)
    path = split.path.lower()
    query = dict(urllib.parse.parse_qsl(split.query))
    if path in ("/", ""):
        return "home"
    if path.startswith("/p/shop"):
        return "shop-collection"
    if path.startswith("/p/resources"):
        return "resource-article"
    if path.startswith("/product"):
        return "product" if query.get("p_id") else "product"
    if path.startswith("/category/pages"):
        return "category-hub"
    if path.startswith(("/category/", "/p/cat")):
        return "category-l3"
    if path.startswith("/search"):
        return "search"
    if path.startswith("/home/newsroom"):
        return "newsroom"
    if path.startswith("/about"):
        return "about"
    return "static-page"


def load_runtime_stylesheets(path: pathlib.Path | None) -> dict[str, list[str]]:
    """Per family, the stylesheets the browser was observed loading.

    17 of the 40 stylesheets the source loads on a category page are injected at
    run time and appear in no page's markup. Without them the clone renders with
    2,501 CSS rules against the source's 5,865 -- and the visible consequence was
    the entire megamenu, 9,516 pixels of it, laid out in the page instead of
    collapsed.
    """
    if path is None or not path.exists():
        return {}
    report = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {}
    for family, urls in (report.get("by_family") or {}).items():
        sheets = []
        for url in urls:
            if not isinstance(url, str):
                continue
            split = urllib.parse.urlsplit(url)
            if split.path.lower().endswith(".css"):
                sheets.append(url)
        out[family] = sheets
    return out


def route_for(url: str) -> str:
    """Frozen-file path for a URL, keeping the source's directory structure.

    Flattening the path to one name loses information and collides:
    `/category/cables/hdmi-cables` and `/category/cables-hdmi/cables` both
    become `category-cables-hdmi-cables`, and the second write silently wins.
    Segments are kept as directories, and a query becomes one extra segment.
    """
    u = urllib.parse.urlsplit(url)
    trailing = u.path.endswith("/") and u.path != "/"
    segments = [s for s in u.path.lower().split("/") if s] or ["index"]
    # Percent-encode rather than substitute. Replacing every unsafe run with "-"
    # collapsed genuinely different pages together: this site serves both
    # `/category/adapters,-switches,-&-splitters/...` and
    # `/category/adapters, switches, & splitters/...`, and they are not the same
    # page -- one pair differed by 70 KB. Encoding keeps them distinct and still
    # readable.
    safe = [urllib.parse.quote(s, safe="._,+&=-")[:100] for s in segments]
    if trailing:
        # `/terms-of-use/` and `/terms-of-use` are two URLs the source answers
        # separately. Keep them apart rather than letting one overwrite the other.
        safe.append("index")
    if u.query:
        keep = sorted(urllib.parse.parse_qsl(u.query))
        if keep:
            encoded = urllib.parse.urlencode(keep)
            # Truncating a long query collided two different filtered listings
            # into one file. A digest of the *whole* query keeps the readable
            # prefix and still separates them.
            digest = hashlib.sha256(encoded.encode()).hexdigest()[:8]
            safe.append("q__" + re.sub(r"[^A-Za-z0-9._,%+&=-]+", "-",
                                       encoded)[:100] + "." + digest)
    return "/".join(safe)


def inject_runtime_stylesheets(html: str, base_url: str, loc: Localiser,
                               sheets_by_family: dict[str, list[str]],
                               tally: collections.Counter) -> str:
    """Add the stylesheets the browser loaded but the markup never declared."""
    sheets = sheets_by_family.get(family_of(base_url)) or []
    if not sheets:
        return html
    additions = []
    for url in sheets:
        local = loc.local_asset(url)
        if local is None:
            continue
        if local in html:
            continue
        additions.append(f'<link rel="stylesheet" href="{local}" '
                         f'data-wb-runtime-injected="1">')
    if not additions:
        return html
    tally["runtime_stylesheets_injected"] += len(additions)
    block = "".join(additions)
    lowered = html.lower()
    head_close = lowered.find("</head>")
    if head_close == -1:
        return block + html
    return html[:head_close] + block + html[head_close:]


def freeze_page(html: str, base_url: str, loc: Localiser,
                tally: collections.Counter,
                sheets_by_family: dict[str, list[str]] | None = None) -> str:
    html = strip_third_party_tags(html, tally)

    def attr_repl(m: re.Match) -> str:
        attr, eq, q, value = m.group("attr"), m.group("eq"), m.group("q"), m.group("v")
        # Rule 2: decide by the value. An attribute whose value is not a
        # reference is left exactly as it was.
        if not value.strip():
            return m.group(0)
        if attr.lower() in NON_URL_ATTRS:
            tally["attribute_skipped_not_a_url_attribute"] += 1
            return m.group(0)
        if MIME_VALUE.match(value.strip()):
            tally["value_skipped_looks_like_a_mime_type"] += 1
            return m.group(0)
        looks_like_ref = (ABSOLUTE.match(value) or value.startswith("/")
                          or re.match(r"^\.{1,2}/", value)
                          or re.match(r"^[\w.-]+/[\w./?=&%-]+$", value))
        if not looks_like_ref:
            return m.group(0)
        if "," in value and re.search(r"\s\d+[wx]", value):     # a srcset
            parts = []
            for chunk in value.split(","):
                chunk = chunk.strip()
                if not chunk:
                    continue
                bits = chunk.split(None, 1)
                new = loc.rewrite_value(bits[0])
                if new == "":
                    continue
                parts.append(" ".join([new if new is not None else bits[0], *bits[1:]]))
            if not parts:
                # Rule 4: an emptied srcset is not inert. Remove the attribute.
                tally["srcset_attribute_removed"] += 1
                return ""
            return f"{attr}{eq}{q}{', '.join(parts)}{q}"
        new = loc.rewrite_value(value)
        if new is None:
            return m.group(0)
        if new == "":
            # Rule 4 again: src="" re-requests the current document. Drop the
            # attribute rather than blanking it.
            tally["attribute_removed_rather_than_blanked"] += 1
            return ""
        return f"{attr}{eq}{q}{new}{q}"

    html = URL_ATTR_SPAN.sub(attr_repl, html)

    def css_repl(m: re.Match) -> str:
        new = loc.rewrite_value(m.group("v"))
        if new is None:
            return m.group(0)
        if new == "":
            tally["css_url_removed"] += 1
            return "url(about:blank)"
        return f'url("{new}")'

    html = CSS_URL.sub(css_repl, html)

    # Third pass: absolute URLs that are neither an attribute value nor a CSS
    # url(). This site embeds product data as JSON inside the page, and the image
    # URLs in it are written `https:\/\/images.monoprice.com\/...` -- escaped
    # slashes, inside a string, invisible to both passes above.
    #
    # The runtime audit is what found them: a *frozen* product page was still
    # asking images.monoprice.com for its gallery, with initiator type "parser",
    # meaning the URL was in the markup all along. Every closure number was green
    # because a reference the rewriter does not match is not counted as
    # unresolved -- it is not counted at all.
    def bare_repl(m: re.Match) -> str:
        raw = m.group(0)
        escaped = "\\/" in raw
        candidate = raw.replace("\\/", "/")
        if is_third_party(candidate):
            tally["third_party_reference_removed_in_text"] += 1
            return raw
        local = loc.local_asset(candidate)
        if local is None:
            return raw
        tally["asset_localised_in_text"] += 1
        return local.replace("/", "\\/") if escaped else local

    html = BARE_ABSOLUTE.sub(bare_repl, html)

    # Rule 4, second half. Removing a src attribute stops the empty-string
    # re-request, but an <img> with no src still paints a broken-image box. Side
    # by side with the source, the clone showed 14 visible broken images on a
    # category page where the source showed none.
    #
    # A transparent 1x1 GIF as a data: URI makes no request, renders nothing, and
    # leaves the element in place for any script that expects it. `data:` is
    # allowed by the img-src directive precisely for this.
    def blank_img(m: re.Match) -> str:
        tag = m.group(0)
        # `\bsrc\s*=` is wrong here and the test caught it: `-` is a non-word
        # character, so `\b` matches inside `data-src`, and an <img> carrying
        # only a data-src would have been left with no src at all -- the exact
        # broken-image box this pass exists to remove. The lookbehind is the
        # same fix an earlier site needed when `\b(href)` matched `data-href`.
        if re.search(r"(?<![-\w])src\s*=", tag, re.I):
            return tag
        tally["img_without_src_given_transparent_pixel"] += 1
        return tag[:4] + f' src="{TRANSPARENT_PIXEL}"' + tag[4:]

    html = IMG_TAG.sub(blank_img, html)

    if sheets_by_family:
        html = inject_runtime_stylesheets(html, base_url, loc, sheets_by_family,
                                          tally)

    html = reveal_results_container(html, tally)
    html = strip_subresource_integrity(html, tally)

    if "data-wb-stripped-globals" not in html:
        lowered = html.lower()
        head_open = lowered.find("<head")
        if head_open != -1:
            insert_at = lowered.find(">", head_open) + 1
            tally["stripped_globals_shim_injected"] += 1
            html = html[:insert_at] + STRIPPED_GLOBALS_SHIM + html[insert_at:]

    if 'action="/search/index"' in html and "data-wb-search-submit" not in html:
        lowered = html.lower()
        close_body = lowered.rfind("</body>")
        if close_body != -1:
            tally["search_submit_fix_injected"] += 1
            html = html[:close_body] + SEARCH_SUBMIT_FIX + html[close_body:]
    return html


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture-dir", required=True)
    ap.add_argument("--assets-dir", required=True)
    ap.add_argument("--catalogue", required=True)
    ap.add_argument("--out-root", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--runtime-assets", default=None,
                    help="scope/runtime-assets.json: the stylesheets the "
                         "browser was observed loading per page family")
    args = ap.parse_args()

    catalogue = json.loads(pathlib.Path(args.catalogue).read_text(encoding="utf-8"))
    served_products = {p["p_id"] for p in catalogue["products"]}
    served_routes = {c["path"] for c in catalogue["categories"]}
    assets_dir = pathlib.Path(args.assets_dir)
    sheets_by_family = load_runtime_stylesheets(
        pathlib.Path(args.runtime_assets) if args.runtime_assets else None)
    out_root = pathlib.Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    tally: collections.Counter = collections.Counter()
    unresolved: list[str] = []
    written = 0
    by_kind: collections.Counter = collections.Counter()
    route_map: dict[str, str] = {}
    reserved: dict[str, str] = {}
    collisions: list[tuple[str, str]] = []
    total_raw_bytes = [0]
    total_stored_bytes = [0]

    page_dirs = sorted(d for d in pathlib.Path(args.capture_dir).glob("*/*")
                       if d.is_dir())
    if args.limit:
        page_dirs = page_dirs[:args.limit]

    for page_dir in page_dirs:
        meta_path = page_dir / "fetch.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        kind = meta.get("classification")
        # A stylesheet that got swept into the page capture is not a page. It
        # classifies as `content` -- it has no <title>, so no rule rejects it --
        # and freezing it would serve CSS as an HTML route.
        if re.match(r"^/(assets|Scripts|Content|cf-fonts|CommissionJunction)/",
                    urllib.parse.urlsplit(meta["url"]).path, re.I):
            by_kind["skipped:asset-not-a-page"] += 1
            continue
        # An error page captured from the source is not a content page. Serving
        # one with status 200 is a false success, and this site's absent-product
        # page looks entirely ordinary.
        # An error page captured from the source must never be served as content
        # at status 200 -- that is a false success, and this site's absent-product
        # page looks entirely ordinary. But the clone still needs *one* of each,
        # because the source answers those situations with these exact pages: a
        # real 404 at /this-route-does-not-exist, and a 200 "Products no longer
        # Available" for 1,906 discontinued ids. They are frozen once, into a
        # reserved directory the route map does not point at, and the app serves
        # them deliberately with the right status.
        if kind in ("not-found", "absent-product"):
            slot = "_error/not-found" if kind == "not-found" else "_error/absent-product"
            if slot in reserved:
                by_kind[f"skipped:{kind}"] += 1
                continue
            html_body = read_body(page_dir)
            if html_body is None:
                by_kind[f"skipped:{kind}-no-body"] += 1
                continue
            # Not every 404 the site emits is the *site's* 404. A request under
            # an asset path returns IIS's own "Detailed Error - 404.0" page --
            # a server page, not a Monoprice page -- and taking the first one
            # encountered picked exactly that. The site's own error page is
            # titled HttpError404.
            if kind == "not-found":
                title = re.search(r"<title[^>]*>(.*?)</title>", html_body,
                                  re.I | re.S)
                text = (title.group(1) if title else "").strip().lower()
                if "httperror404" not in text.replace(" ", ""):
                    by_kind["skipped:not-found-server-page"] += 1
                    continue
            loc = Localiser(assets_dir, meta["url"], served_routes, served_products)
            frozen_error = freeze_page(html_body, meta["url"], loc, tally,
                                       sheets_by_family)
            dest = out_root / f"{slot}.html"
            dest.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(f"{dest}.gz", "wb", compresslevel=6) as fh:
                fh.write(frozen_error.encode("utf-8", "replace"))
            reserved[slot] = meta["url"]
            by_kind[f"written:error-page:{kind}"] += 1
            continue
        if kind not in ("content", "empty-listing"):
            by_kind[f"skipped:{kind}"] += 1
            continue
        html = read_body(page_dir)
        if html is None:
            by_kind["skipped:body-not-retained"] += 1
            continue
        loc = Localiser(assets_dir, meta["url"], served_routes, served_products)
        frozen = freeze_page(html, meta["url"], loc, tally, sheets_by_family)
        tally.update(loc.tally)
        unresolved.extend(loc.unresolved[:5])
        route = route_for(meta["url"])
        dest = out_root / f"{route}.html"
        if route in route_map:
            # Two source URLs that would occupy one file. Report it rather than
            # letting the second write win in silence.
            collisions.append((route_map[route], meta["url"]))
            by_kind["skipped:route-collision"] += 1
            continue
        route_map[route] = meta["url"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Stored gzipped. These pages are 285 KB each and there are ~6,000 of
        # them: 1.7 GB verbatim, ~180 MB compressed. The app serves the bytes
        # untouched with `Content-Encoding: gzip`, which every browser decodes,
        # so this costs nothing at request time -- it is not a cache, it is the
        # representation.
        raw = frozen.encode("utf-8", "replace")
        with gzip.open(f"{dest}.gz", "wb", compresslevel=6) as fh:
            fh.write(raw)
        total_raw_bytes[0] += len(raw)
        total_stored_bytes[0] += pathlib.Path(f"{dest}.gz").stat().st_size
        by_kind[f"written:{kind}"] += 1
        written += 1

    # The route map is what the app serves from. Writing it here rather than
    # having the app re-derive the naming rule keeps one definition of the
    # mapping instead of two that can drift apart.
    (out_root / "route-map.json").write_text(
        json.dumps({"schema_version": "monoprice.frozen-route-map.v1",
                    "routes": {url: route for route, url in
                               sorted(route_map.items(), key=lambda kv: kv[1])}},
                   indent=1) + "\n", encoding="utf-8")

    report = {
        "schema_version": "monoprice.frozen-pages.v1",
        "pages_written": written,
        "stored_bytes": total_stored_bytes[0],
        "uncompressed_bytes": total_raw_bytes[0],
        "error_pages": dict(sorted(reserved.items())),
        "route_collisions": len(collisions),
        "route_collision_examples": collisions[:10],
        "runtime_stylesheet_families": {k: len(v) for k, v in
                                        sorted(sheets_by_family.items())},
        "by_kind": dict(sorted(by_kind.items())),
        "rewrites": dict(sorted(tally.items())),
        "unresolved_examples": sorted(set(unresolved))[:40],
        "unresolved_total": tally.get("asset_missing_on_disk", 0),
        "note": ("`asset_missing_on_disk` is the number of references left "
                 "pointing at bytes that are not in the asset tree. They are "
                 "counted, not silently skipped: an unmatched reference that is "
                 "not counted is how a page keeps calling a CDN while the "
                 "closure report reads clean."),
    }
    pathlib.Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.report).write_text(json.dumps(report, indent=2) + "\n",
                                         encoding="utf-8")
    print(json.dumps(report, indent=2)[:2500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
