#!/usr/bin/env python
"""Anonymous static-capture matrix + public store-API harvest for humblebundle.com.

One reusable harness for the WebsiteBench offline-clone source-evidence phase.

Usage (from repo root):
  .venv/bin/python materials/humble-bundle/tools/capture_static_matrix.py
  ... --only home,login --viewports desktop --no-harvest --out /path/to/smoke
  ... --harvest-only     # redo API harvest against existing static DOMs

Hard rules enforced here (task brief + AGENTS.md):
  * read-only public GET page loads; in-page fetch() GETs to the site's own
    public store API only; robots-disallowed paths refused by assert_allowed()
  * no cookies / tokens / request/response headers persisted; values of any
    key matching /csrf/i are replaced with REDACTED-CSRF-TOKEN on save
  * max 2 attempts per failing cell; <= 4 browser contexts; polite pacing
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

BASE = "https://www.humblebundle.com"
DEFAULT_OUT = Path(
    "/Users/wentaoma/Desktop/websitebench-pipeline/materials/humble-bundle/"
    "source-current/2026-08-20.humble-bundle-r1"
)

REDACTED = "REDACTED-CSRF-TOKEN"
MAX_ASSET_BYTES = 15 * 1024 * 1024
BASE_SETTLE_MS = 3500

ASSET_HOST_ALLOWLIST = {
    "www.humblebundle.com",
    "cdn.humblebundle.com",
    "humblebundle-a.akamaihd.net",
    "hb.imgix.net",
    "hbproxy.imgix.net",
}
SKIP_HOST_TOKENS = (
    "googletagmanager", "optimizely", "ziffstatic", "zdbb", "clarity",
    "sift", "recaptcha", "gstatic", "doubleclick", "facebook",
    "cookielaw", "onetrust", "rlcdn", "algolia",
)
ASSET_CT_EXACT = {
    "text/css",
    "application/javascript",
    "text/javascript",
    "application/x-javascript",
}

DISALLOWED_PATH_RES = [
    re.compile(r"^/store/product(/|$)"),
    re.compile(r"^/widget/v2(/|$)"),
    re.compile(r"^/emailhelper"),
    re.compile(r"^/delete-key"),
    re.compile(r"^/download-lister"),
    re.compile(r"^/return"),
    re.compile(r"^/user(/|$)"),
]

VIEWPORTS = [
    {"label": "desktop", "width": 1440, "height": 900, "device_scale_factor": 1, "is_mobile": False},
    {"label": "mobile", "width": 390, "height": 844, "device_scale_factor": 2, "is_mobile": False},
]

DEFAULT_SEARCH_PARAMS = {
    "sort": "bestselling",
    "filter": "all",
    "search": "portal",
    "request": "1",
    "page_size": "20",
    "page": "0",
}

# ----- JS snippets ----------------------------------------------------------

MAIN_TEXT_500 = """((document.querySelector('main') || document.body).innerText || '').length > 500"""
GAMES_LINKS_5 = """document.querySelectorAll('a[href*="/games/"]').length >= 5"""
STORE_LINKS_20 = """document.querySelectorAll('a[href^="/store/"]').length >= 20"""
BUNDLE_READY = """/\\$/.test(document.body ? document.body.innerText : '') && document.images.length > 10"""
PRODUCT_READY = """(!!document.querySelector('h1') || !!document.querySelector('[class*=product]')) && document.images.length > 5"""
NO_RESULTS_READY = """/no result|no search result|0 results|couldn't find|could not find|didn't match|no matches|nothing (?:matched|found)|found 0|try (?:a )?different|no products/i.test(document.body ? document.body.innerText : '')"""

CHALLENGE_JS = """() => {
  const t = (document.title || '').toLowerCase();
  if (/just a moment|attention required|checking your browser|access denied/.test(t)) return true;
  const el = document.querySelector('#challenge-form, #challenge-running, #cf-challenge-running, .cf-turnstile, #turnstile-wrapper');
  if (!el) return false;
  const body = document.body ? document.body.innerText : '';
  return /verify(?:ing)? you are human|security of your connection|enable javascript and cookies/i.test(body);
}"""

SWEEP_JS = """async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const bottom = () => Math.max(
    document.body ? document.body.scrollHeight : 0,
    document.documentElement ? document.documentElement.scrollHeight : 0);
  let steps = 0;
  while (window.scrollY + window.innerHeight < bottom() - 2 && steps < 120) {
    window.scrollBy(0, 800);
    steps += 1;
    await sleep(250);
  }
  await sleep(250);
  window.scrollTo(0, 0);
  await sleep(800);
  return steps;
}"""

FETCH_JS = """async (arg) => {
  const headers = { 'Accept': 'application/json' };
  if (arg.xrw) headers['X-Requested-With'] = 'XMLHttpRequest';
  const r = await fetch(arg.u, { method: 'GET', headers: headers });
  const text = await r.text();
  return { status: r.status, text: text };
}"""

NO_RESULTS_EXTRACT_JS = """() => {
  const body = document.body ? document.body.innerText : '';
  const lines = body.split('\\n').map((s) => s.trim()).filter((s) => s.length > 0);
  const rx = /no result|no search result|0 results|couldn't find|could not find|didn't match|no matches|nothing (?:matched|found)|found 0|try (?:a )?different|no products/i;
  for (const line of lines) { if (rx.test(line)) return line; }
  return null;
}"""

HEADLINE_JS = """() => {
  const el = document.querySelector('h1, h2, [class*="error"], [class*="not-found"], [class*="404"]');
  const t = el && el.innerText ? el.innerText.trim() : '';
  if (t) return t.slice(0, 300);
  const body = document.body ? document.body.innerText : '';
  return body.split('\\n').map((s) => s.trim()).filter(Boolean).slice(0, 3).join(' | ').slice(0, 300);
}"""

DOM_JS = "() => document.documentElement.outerHTML"
SCROLL_HEIGHT_JS = "() => Math.max(document.body ? document.body.scrollHeight : 0, document.documentElement.scrollHeight)"
CONSTANTS_JS = "() => { const el = document.getElementById('storefront-constants-json-data'); return el ? el.textContent : null; }"


def build_checkpoints():
    return [
        {"id": "home", "url": BASE + "/", "readiness": "document.images.length > 10"},
        {"id": "bundles", "url": BASE + "/bundles", "readiness": GAMES_LINKS_5},
        {"id": "games", "url": BASE + "/games", "readiness": GAMES_LINKS_5},
        {"id": "books", "url": BASE + "/books",
         "readiness": """document.querySelectorAll('a[href*="/books/"]').length >= 5"""},
        {"id": "software", "url": BASE + "/software",
         "readiness": """document.querySelectorAll('a[href*="/software/"]').length >= 5"""},
        {"id": "bundle-anchor", "url": BASE + "/games/yes-chef-cooking-bundle", "readiness": BUNDLE_READY},
        {"id": "bundle-2k", "url": BASE + "/games/2k-megahits-2026-bundle", "readiness": BUNDLE_READY},
        {"id": "store", "url": BASE + "/store", "readiness": STORE_LINKS_20},
        {"id": "store-search", "url": BASE + "/store/search?search=portal", "readiness": STORE_LINKS_20},
        {"id": "store-search-noresults", "url": BASE + "/store/search?search=zzzz-no-match-websitebench",
         "readiness": NO_RESULTS_READY, "readiness_ms": 12000, "soft": True},
        {"id": "store-product-satisfactory", "url": BASE + "/store/satisfactory", "readiness": PRODUCT_READY},
        {"id": "membership", "url": BASE + "/membership", "readiness": "document.images.length > 5"},
        {"id": "login", "url": BASE + "/login", "readiness": """!!document.querySelector('input[type=password]')"""},
        {"id": "signup", "url": BASE + "/signup", "readiness": """!!document.querySelector('input[type=password]')"""},
        {"id": "about", "url": BASE + "/about", "readiness": MAIN_TEXT_500},
        {"id": "charities", "url": BASE + "/charities", "readiness": "document.images.length > 3"},
        {"id": "terms", "url": BASE + "/terms", "readiness": MAIN_TEXT_500},
        {"id": "privacy", "url": BASE + "/privacy", "readiness": MAIN_TEXT_500},
        {"id": "legal", "url": BASE + "/legal", "readiness": MAIN_TEXT_500},
        {"id": "cookie-policy", "url": BASE + "/cookie-policy", "readiness": MAIN_TEXT_500},
        {"id": "accessibility", "url": BASE + "/accessibility", "readiness": MAIN_TEXT_500},
        {"id": "notfound-404", "url": BASE + "/this-page-does-not-exist-websitebench",
         "readiness": None, "any_status": True},
        {"id": "support-home", "url": "https://support.humblebundle.com/hc/en-us",
         "readiness": """!!document.querySelector('h1') || !!document.querySelector('input[type="search"], form[role="search"], [class*="search"]')"""},
    ]


# ----- sanitization ---------------------------------------------------------

RE_GENERIC_KV = re.compile(
    r"""(["']?[A-Za-z0-9_\-]*csrf[A-Za-z0-9_\-]*["']?\s*[:=]\s*)(["'])((?:\\.|(?!\2).)+?)\2""",
    re.IGNORECASE | re.DOTALL,
)
RE_INPUT_NAME_VALUE = re.compile(
    r"""(<input\b[^>]*\bname\s*=\s*["'][^"']*csrf[^"']*["'][^>]*\bvalue\s*=\s*["'])([^"']+)(["'])""",
    re.IGNORECASE,
)
RE_INPUT_VALUE_NAME = re.compile(
    r"""(<input\b[^>]*\bvalue\s*=\s*["'])([^"']+)(["'][^>]*\bname\s*=\s*["'][^"']*csrf[^"']*["'])""",
    re.IGNORECASE,
)
RE_META_NAME_CONTENT = re.compile(
    r"""(<meta\b[^>]*\bname\s*=\s*["'][^"']*csrf[^"']*["'][^>]*\bcontent\s*=\s*["'])([^"']+)(["'])""",
    re.IGNORECASE,
)
RE_META_CONTENT_NAME = re.compile(
    r"""(<meta\b[^>]*\bcontent\s*=\s*["'])([^"']+)(["'][^>]*\bname\s*=\s*["'][^"']*csrf[^"']*["'])""",
    re.IGNORECASE,
)
RE_URL_CSRF_PARAM = re.compile(
    r"""([?&][A-Za-z0-9_\-]*csrf[A-Za-z0-9_\-]*=)([^&"'\s<]+)""",
    re.IGNORECASE,
)
CSRF_KEY_RE = re.compile("csrf", re.IGNORECASE)


def redact_text(text):
    """Redact csrf-like values in HTML/JS/JSON text. Returns (text, count)."""
    total = 0
    text, n = RE_GENERIC_KV.subn(lambda m: m.group(1) + m.group(2) + REDACTED + m.group(2), text)
    total += n
    for rx in (RE_INPUT_NAME_VALUE, RE_META_NAME_CONTENT, RE_INPUT_VALUE_NAME, RE_META_CONTENT_NAME):
        text, n = rx.subn(lambda m: m.group(1) + REDACTED + m.group(3), text)
        total += n
    text, n = RE_URL_CSRF_PARAM.subn(lambda m: m.group(1) + REDACTED, text)
    total += n
    return text, total


def redact_json_obj(obj):
    """Recursively redact values under any key matching /csrf/i. Returns (obj, count)."""
    count = 0

    def walk(o):
        nonlocal count
        if isinstance(o, dict):
            out = {}
            for k, v in o.items():
                if isinstance(k, str) and CSRF_KEY_RE.search(k) and v not in (None, "", REDACTED):
                    out[k] = REDACTED
                    count += 1
                else:
                    out[k] = walk(v)
            return out
        if isinstance(o, list):
            return [walk(v) for v in o]
        if isinstance(o, str) and "csrf" in o.lower():
            new, n = redact_text(o)
            count += n
            return new
        return o

    return walk(obj), count


def assert_allowed(url):
    """Refuse robots-disallowed humblebundle.com paths. Returns url unchanged."""
    pr = urlparse(url)
    host = (pr.hostname or "").lower()
    if host.endswith("humblebundle.com"):
        path = pr.path or "/"
        for rx in DISALLOWED_PATH_RES:
            if rx.search(path):
                raise RuntimeError(f"robots-disallowed path, refusing: {url}")
        if path == "/" and (pr.query or "").startswith("key"):
            raise RuntimeError(f"robots-disallowed query, refusing: {url}")
    return url


# ----- small helpers --------------------------------------------------------

def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(msg):
    print(f"{datetime.now(timezone.utc).strftime('%H:%M:%S')} {msg}", flush=True)


def flush_manifest(manifest, path):
    path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")


def flush_url_map(st):
    st["url_map_path"].write_text(json.dumps(st["url_map"], indent=1), encoding="utf-8")


def context_kwargs(vp):
    return dict(
        viewport={"width": vp["width"], "height": vp["height"]},
        device_scale_factor=vp["device_scale_factor"],
        is_mobile=vp["is_mobile"],
        locale="en-US",
        service_workers="block",
    )


def normalized_ct(headers):
    return (headers.get("content-type") or "").split(";")[0].strip().lower()


def asset_ct_allowed(ct):
    return (
        ct.startswith("image/")
        or ct.startswith("font/")
        or ct.startswith("application/font")
        or ct in ASSET_CT_EXACT
    )


async def save_asset_body(response, url, ct, st):
    try:
        body = await response.body()
    except Exception:
        st["asset_read_errors"] += 1
        return
    if not body:
        return
    if len(body) > MAX_ASSET_BYTES:
        st["asset_skipped_large"] += 1
        return
    digest = hashlib.sha256(body).hexdigest()
    blob = st["blob_dir"] / digest[:2] / digest
    if not blob.exists():
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.write_bytes(body)
        st["asset_unique_count"] += 1
        st["asset_unique_bytes"] += len(body)
    if url not in st["url_map"]:
        st["url_map"][url] = {"sha256": digest, "content_type": ct, "bytes": len(body)}


def make_response_handler(st, pending, flags):
    def on_response(response):
        if flags.get("closing"):
            return
        try:
            if response.request.method != "GET" or response.status != 200:
                return
            url = response.url
            host = (urlparse(url).hostname or "").lower()
            if host not in ASSET_HOST_ALLOWLIST:
                return
            if any(tok in host for tok in SKIP_HOST_TOKENS):
                return
            ct = normalized_ct(response.headers)
            if not asset_ct_allowed(ct):
                return
            pending.append(asyncio.create_task(save_asset_body(response, url, ct, st)))
        except Exception:
            pass
    return on_response


async def route_block_skiphosts(route):
    host = (urlparse(route.request.url).hostname or "").lower()
    if any(tok in host for tok in SKIP_HOST_TOKENS):
        await route.abort()
        return
    await route.continue_()


# ----- static cell capture --------------------------------------------------

async def run_attempt(browser, cp, vp, st, out_root, manifest, capture_anyway):
    cell_dir = out_root / "static" / cp["id"] / vp["label"]
    cell_dir.mkdir(parents=True, exist_ok=True)
    context = await browser.new_context(**context_kwargs(vp))
    pending = []
    flags = {"closing": False}
    notes = []
    result = {"ok": False, "reason": None, "http_status": None,
              "final_url": None, "title": None, "notes": notes}

    async def body():
        if cp["id"] != "support-home":
            await context.route("**/*", route_block_skiphosts)
            notes.append("analytics/consent/captcha hosts route-blocked")
        context.on("response", make_response_handler(st, pending, flags))
        page = await context.new_page()
        url = assert_allowed(cp["url"])
        t0 = time.monotonic()
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except (PlaywrightTimeout, PlaywrightError) as exc:
            result["reason"] = f"goto-error: {str(exc).splitlines()[0][:200]}"
            return
        status = resp.status if resp else None
        result["http_status"] = status
        await asyncio.sleep(BASE_SETTLE_MS / 1000)
        readiness_ok = True
        if cp.get("readiness"):
            try:
                await page.wait_for_function(cp["readiness"], timeout=cp.get("readiness_ms", 15000))
            except PlaywrightTimeout:
                readiness_ok = False
            except PlaywrightError as exc:
                readiness_ok = False
                notes.append(f"readiness-eval-error: {str(exc).splitlines()[0][:120]}")
        challenged = False
        try:
            challenged = bool(await page.evaluate(CHALLENGE_JS))
        except PlaywrightError:
            pass
        if challenged and not capture_anyway:
            result["reason"] = "cloudflare-challenge"
            return
        if not readiness_ok and not capture_anyway and not cp.get("soft"):
            result["reason"] = "readiness-timeout"
            return
        if not readiness_ok:
            notes.append("readiness-timeout: captured after settle anyway")

        sweep_steps = None
        for _ in range(2):
            try:
                sweep_steps = await page.evaluate(SWEEP_JS)
                break
            except PlaywrightError:
                await asyncio.sleep(1.0)
        notes.append("sweep-failed" if sweep_steps is None else f"sweep_steps={sweep_steps}")
        settle_ms = int((time.monotonic() - t0) * 1000)

        dom = None
        for _ in range(2):
            try:
                dom = await page.evaluate(DOM_JS)
                break
            except PlaywrightError:
                await asyncio.sleep(1.0)
        if dom is None:
            result["reason"] = "dom-capture-failed"
            return
        dom, n_red = redact_text(dom)
        st["redactions_html"] += n_red
        (cell_dir / "dom.html").write_text(dom, encoding="utf-8")

        try:
            result["title"] = await page.title()
        except PlaywrightError:
            pass
        result["final_url"] = page.url
        if urlparse(url).path.rstrip("/") != urlparse(page.url).path.rstrip("/"):
            notes.append(f"redirected-to: {page.url}")

        try:
            await page.screenshot(path=str(cell_dir / "screenshot.png"), timeout=60000)
        except PlaywrightError as exc:
            msg = f"viewport-screenshot-failed: {str(exc).splitlines()[0][:120]}"
            if not capture_anyway:
                result["reason"] = msg
                return
            notes.append(msg)
        try:
            await page.screenshot(path=str(cell_dir / "screenshot-full.png"),
                                  full_page=True, timeout=120000)
        except PlaywrightError as exc:
            notes.append(f"fullpage-screenshot-error: {str(exc).splitlines()[0][:120]}")
            try:
                h = await page.evaluate(SCROLL_HEIGHT_JS)
                clip_h = max(vp["height"], min(int(h), 16000))
                await page.screenshot(path=str(cell_dir / "screenshot-full.png"),
                                      clip={"x": 0, "y": 0, "width": vp["width"], "height": clip_h},
                                      timeout=120000)
                notes.append(f"fullpage-fallback-clip-height={clip_h}")
            except PlaywrightError as exc2:
                notes.append(f"fullpage-fallback-failed: {str(exc2).splitlines()[0][:120]}")

        if cp["id"] == "store-search-noresults":
            line = None
            try:
                line = await page.evaluate(NO_RESULTS_EXTRACT_JS)
            except PlaywrightError:
                pass
            if line:
                notes.append(f"no-results-copy: {line}")
                manifest.setdefault("findings", {})["no_results_copy"] = line
            else:
                notes.append("no-results-copy: no matching phrase found in body text")
        if cp["id"] == "notfound-404":
            headline = None
            try:
                headline = await page.evaluate(HEADLINE_JS)
            except PlaywrightError:
                pass
            notes.append(f"notfound-status={status} copy={headline!r}")
            manifest.setdefault("findings", {})["notfound_404"] = {
                "http_status": status, "visible_copy": headline}
        if challenged:
            notes.append("cloudflare-challenge page captured as evidence")

        meta = {
            "url": url,
            "final_url": result["final_url"],
            "title": result["title"],
            "ts_utc": now_utc(),
            "viewport": {k: vp[k] for k in ("label", "width", "height", "device_scale_factor", "is_mobile")},
            "settle_ms": settle_ms,
            "http_status": status,
            "notes": list(notes),
        }
        (cell_dir / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")

        if challenged:
            result["reason"] = "cloudflare-challenge"
            return
        if status is not None and status >= 400 and not cp.get("any_status"):
            result["reason"] = f"http-{status} (artifacts saved)"
            return
        result["ok"] = True

    try:
        await body()
        flags["closing"] = True
        tasks = [t for t in pending if not t.done()]
        if tasks:
            _, not_done = await asyncio.wait(tasks, timeout=20)
            for t in not_done:
                t.cancel()
        return result
    finally:
        flags["closing"] = True
        for t in pending:
            if not t.done():
                t.cancel()
        try:
            await context.close()
        except BaseException:
            pass


async def run_cell(browser, cp, vp, st, manifest, out_root, manifest_path):
    key = f"{cp['id']}/{vp['label']}"
    t0 = time.monotonic()
    rec = None
    attempts = 0
    for attempt in (1, 2):
        attempts = attempt
        capture_anyway = attempt == 2
        try:
            rec = await asyncio.wait_for(
                run_attempt(browser, cp, vp, st, out_root, manifest, capture_anyway),
                timeout=300,
            )
        except asyncio.TimeoutError:
            rec = {"ok": False, "reason": "attempt-timeout-300s", "http_status": None,
                   "final_url": None, "title": None, "notes": []}
        except RuntimeError as exc:
            rec = {"ok": False, "reason": str(exc), "http_status": None,
                   "final_url": None, "title": None, "notes": []}
            break
        except Exception as exc:
            rec = {"ok": False, "reason": f"unexpected: {type(exc).__name__}: {str(exc)[:200]}",
                   "http_status": None, "final_url": None, "title": None, "notes": []}
        if rec["ok"]:
            break
        if attempt == 1:
            await asyncio.sleep(2.0)
    cell = {
        "id": cp["id"],
        "viewport": vp["label"],
        "url": cp["url"],
        "status": "ok" if rec["ok"] else "failed",
        "attempts": attempts,
        "reason": rec.get("reason"),
        "http_status": rec.get("http_status"),
        "final_url": rec.get("final_url"),
        "notes": rec.get("notes", []),
        "duration_ms": int((time.monotonic() - t0) * 1000),
    }
    manifest["cells"][key] = cell
    flush_manifest(manifest, manifest_path)
    flush_url_map(st)
    extra = f" reason={cell['reason']}" if cell["reason"] else ""
    log(f"[{cell['status']}] {key} http={cell['http_status']} attempts={attempts}{extra}")


async def run_matrix(browser, cells, st, manifest, out_root, manifest_path, workers):
    q = asyncio.Queue()
    for c in cells:
        q.put_nowait(c)

    async def worker(idx):
        await asyncio.sleep(1.5 * idx)
        while True:
            try:
                cp, vp = q.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                await run_cell(browser, cp, vp, st, manifest, out_root, manifest_path)
            except Exception as exc:
                key = f"{cp['id']}/{vp['label']}"
                manifest["cells"][key] = {
                    "id": cp["id"], "viewport": vp["label"], "url": cp["url"],
                    "status": "failed", "attempts": 0,
                    "reason": f"runner-crash: {type(exc).__name__}: {str(exc)[:200]}",
                    "notes": [],
                }
                flush_manifest(manifest, manifest_path)

    n = max(1, min(int(workers), 4))
    await asyncio.gather(*(worker(i) for i in range(n)))


async def preflight(browser):
    ctx = await browser.new_context(**context_kwargs(VIEWPORTS[0]))
    try:
        page = await ctx.new_page()
        resp = await page.goto(BASE + "/", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(2.5)
        return {
            "status": resp.status if resp else None,
            "user_agent": await page.evaluate("() => navigator.userAgent"),
            "challenged": bool(await page.evaluate(CHALLENGE_JS)),
        }
    finally:
        try:
            await ctx.close()
        except Exception:
            pass


# ----- API harvest ----------------------------------------------------------

def payload_item_count(obj):
    if isinstance(obj, dict):
        for key in ("results", "result", "products", "items"):
            v = obj.get(key)
            if isinstance(v, list):
                return len(v)
        return None
    if isinstance(obj, list):
        return len(obj)
    return None


def collect_human_urls(obj):
    found = []

    def walk(o):
        if isinstance(o, dict):
            hu = o.get("human_url")
            if isinstance(hu, str) and hu:
                found.append(hu)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(obj)
    seen, out = set(), []
    for s in found:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def find_genre_enum(obj):
    best = None

    def walk(o, path):
        nonlocal best
        if best is not None:
            return
        if isinstance(o, dict):
            for k, v in o.items():
                if best is not None:
                    return
                if isinstance(k, str) and re.search(r"genre", k, re.I) and isinstance(v, list) and v:
                    vals = []
                    for item in v:
                        if isinstance(item, str):
                            vals.append(item)
                        elif isinstance(item, dict):
                            for kk in ("slug", "machine_name", "value", "key", "name"):
                                if isinstance(item.get(kk), str):
                                    vals.append(item[kk])
                                    break
                    if vals:
                        best = (f"{path}/{k}", vals)
                        return
                walk(v, f"{path}/{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{path}[{i}]")

    walk(obj, "")
    return best


def extract_script_json(html_text, want_id, fallback_tokens=()):
    m = re.search(r"<script[^>]*\bid=[\"']%s[\"'][^>]*>(.*?)</script>" % re.escape(want_id),
                  html_text, re.S | re.I)
    if m:
        return m.group(1).strip(), want_id
    for tok in fallback_tokens:
        for sm in re.finditer(r"<script[^>]*\bid=[\"']([^\"']*)[\"'][^>]*>(.*?)</script>",
                              html_text, re.S | re.I):
            sid = sm.group(1)
            if tok.lower() in sid.lower() and "data" in sid.lower():
                return sm.group(2).strip(), sid
    return None, None


def build_search_url(base_params, overrides, drop=()):
    params = {k: v for k, v in base_params.items() if k not in drop}
    params.update(overrides)
    return assert_allowed(BASE + "/store/api/search?" + urlencode(params))


def build_lookup_url(slugs):
    q = [("products[]", s) for s in slugs] + [("request", "1")]
    return assert_allowed(BASE + "/store/api/lookup?" + urlencode(q))


def save_harvest_json(api_dir, st, harvest, name, res, note=None):
    path = api_dir / name
    entry = {}
    if note:
        entry["note"] = note
    if not res or res.get("status") is None:
        entry.update({"status": "fetch-error", "error": (res or {}).get("error")})
        harvest["files"][name] = entry
        return None
    text = res.get("text") or ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        red, n = redact_text(text)
        st["redactions_json"] += n
        path.write_text(red, encoding="utf-8")
        entry.update({"status": f"http-{res['status']}", "bytes": len(red), "items": None,
                      "note": "non-json body saved raw (redacted)"})
        harvest["files"][name] = entry
        return None
    payload, n = redact_json_obj(payload)
    st["redactions_json"] += n
    out = json.dumps(payload, indent=1)
    path.write_text(out, encoding="utf-8")
    entry.update({"status": f"http-{res['status']}", "bytes": len(out),
                  "items": payload_item_count(payload)})
    harvest["files"][name] = entry
    return payload if res["status"] == 200 else None


def extract_embedded_to_file(out_root, st, harvest, cp_id, script_id, fallback_tokens, dest):
    name = dest.name
    for vp_label in ("desktop", "mobile"):
        dom_path = out_root / "static" / cp_id / vp_label / "dom.html"
        if not dom_path.exists():
            continue
        text, sid = extract_script_json(dom_path.read_text(encoding="utf-8"), script_id, fallback_tokens)
        if not text:
            continue
        entry = {"source": f"static/{cp_id}/{vp_label}/dom.html", "script_id": sid}
        try:
            payload = json.loads(text)
            payload, n = redact_json_obj(payload)
            st["redactions_json"] += n
            out = json.dumps(payload, indent=1)
            dest.write_text(out, encoding="utf-8")
            entry.update({"bytes": len(out), "items": payload_item_count(payload), "status": "extracted"})
        except json.JSONDecodeError:
            red, n = redact_text(text)
            st["redactions_json"] += n
            dest.write_text(red, encoding="utf-8")
            entry.update({"bytes": len(red), "items": None, "status": "extracted-nonjson"})
        harvest["files"][name] = entry
        return True
    harvest["files"][name] = {"status": "missing",
                              "note": f"no {script_id} script found in captured {cp_id} DOMs"}
    return False


EMBEDDED_TARGETS = [
    {"file": "bundle-yes-chef-cooking-bundle.json", "cp_id": "bundle-anchor",
     "url": BASE + "/games/yes-chef-cooking-bundle",
     "script_id": "webpack-bundle-page-data", "tokens": ("bundle",)},
    {"file": "bundle-2k-megahits-2026-bundle.json", "cp_id": "bundle-2k",
     "url": BASE + "/games/2k-megahits-2026-bundle",
     "script_id": "webpack-bundle-page-data", "tokens": ("bundle",)},
    {"file": "bundles-landing.json", "cp_id": "bundles",
     "url": BASE + "/bundles",
     "script_id": "landingPage-json-data", "tokens": ("landing",)},
]


def write_embedded_json(dest, text, st, entry):
    try:
        payload = json.loads(text)
        payload, n = redact_json_obj(payload)
        st["redactions_json"] += n
        out = json.dumps(payload, indent=1)
        dest.write_text(out, encoding="utf-8")
        entry.update({"bytes": len(out), "items": payload_item_count(payload), "status": "extracted"})
    except json.JSONDecodeError:
        red, n = redact_text(text)
        st["redactions_json"] += n
        dest.write_text(red, encoding="utf-8")
        entry.update({"bytes": len(red), "items": None, "status": "extracted-nonjson"})
    return entry


async def run_embedded_harvest(browser, out_root, st, manifest, manifest_path):
    """Extract embedded json-data scripts (bundle pages, /bundles landing,
    /store constants). Tries the captured static DOMs first; hydration removes
    these script tags from the live DOM, so fall back to one JS-disabled raw
    pre-hydration HTML load per target (read-only public GET page loads)."""
    api_dir = out_root / "api-harvest"
    api_dir.mkdir(parents=True, exist_ok=True)
    harvest = manifest.setdefault("harvest", {})
    harvest.setdefault("files", {})
    harvest.setdefault("notes", [])
    need_fetch = []
    for tgt in EMBEDDED_TARGETS:
        if not extract_embedded_to_file(out_root, st, harvest, tgt["cp_id"], tgt["script_id"],
                                        tgt["tokens"], api_dir / tgt["file"]):
            need_fetch.append(tgt)
    need_constants = not harvest.get("genre_enum")
    if not need_fetch and not need_constants:
        return
    kwargs = context_kwargs(VIEWPORTS[0])
    kwargs["java_script_enabled"] = False
    context = await browser.new_context(**kwargs)
    try:
        await context.route("**/*", route_block_skiphosts)
        page = await context.new_page()
        note = ("hydration removes embedded json-data scripts from the live DOM; "
                "extracted them from raw pre-hydration HTML instead "
                "(JS-disabled, read-only public GET page loads)")
        if need_fetch and note not in harvest["notes"]:
            harvest["notes"].append(note)

        async def raw_html(url):
            last_exc = None
            for _ in range(2):  # max 2 attempts per cell
                try:
                    await page.goto(assert_allowed(url), wait_until="domcontentloaded", timeout=60000)
                    await asyncio.sleep(1.5)
                    return await page.content()
                except (PlaywrightTimeout, PlaywrightError) as exc:
                    last_exc = exc
                    await asyncio.sleep(2.0)
            raise last_exc

        for tgt in need_fetch:
            try:
                html = await raw_html(tgt["url"])
            except (PlaywrightTimeout, PlaywrightError) as exc:
                harvest["files"][tgt["file"]] = {
                    "status": "missing",
                    "note": f"raw-html fetch failed: {str(exc).splitlines()[0][:120]}"}
                continue
            text, sid = extract_script_json(html, tgt["script_id"], tgt["tokens"])
            if not text:
                harvest["files"][tgt["file"]] = {
                    "status": "missing",
                    "note": f"{tgt['script_id']} absent even in raw pre-hydration HTML"}
                continue
            entry = {"source": f"raw pre-hydration HTML of {tgt['url']}", "script_id": sid}
            harvest["files"][tgt["file"]] = write_embedded_json(api_dir / tgt["file"], text, st, entry)
            log(f"[harvest] embedded {tgt['file']} <- raw HTML ({entry['status']})")
            await asyncio.sleep(1.0)

        if need_constants:
            try:
                html = await raw_html(BASE + "/store")
                text, sid = extract_script_json(html, "storefront-constants-json-data", ("constants",))
                if text:
                    try:
                        found = find_genre_enum(json.loads(text))
                    except json.JSONDecodeError:
                        found = None
                    if found:
                        harvest["genre_enum"] = found[1]
                        harvest["genre_enum_source"] = (
                            f"raw pre-hydration HTML of /store ({sid}) at {found[0]}")
                        log(f"[harvest] genre enum from raw /store HTML: {len(found[1])} values")
                    if "lookup" in text.lower() and \
                            "storefront constants mention 'lookup'" not in harvest["notes"]:
                        harvest["notes"].append("storefront constants mention 'lookup'")
                else:
                    harvest["notes"].append("storefront-constants-json-data absent even in raw /store HTML")
            except (PlaywrightTimeout, PlaywrightError) as exc:
                harvest["notes"].append(f"raw /store HTML fetch failed: {str(exc).splitlines()[0][:120]}")

        obs_path = api_dir / "observed-endpoints.json"
        if obs_path.exists():
            try:
                obs = json.loads(obs_path.read_text(encoding="utf-8"))
                obs["genre_enum"] = harvest.get("genre_enum")
                obs["genre_enum_source"] = harvest.get("genre_enum_source")
                obs["chosen_genre"] = harvest.get("chosen_genre")
                obs["notes"] = harvest.get("notes")
                obs, n = redact_json_obj(obs)
                st["redactions_json"] += n
                obs_path.write_text(json.dumps(obs, indent=1), encoding="utf-8")
            except json.JSONDecodeError:
                pass
        flush_manifest(manifest, manifest_path)
    finally:
        try:
            await context.close()
        except BaseException:
            pass


async def run_harvest(browser, out_root, st, manifest, manifest_path):
    api_dir = out_root / "api-harvest"
    api_dir.mkdir(parents=True, exist_ok=True)
    harvest = {
        "files": {},
        "observed_store_api_requests": [],
        "search_params_used": None,
        "page_size": None,
        "chosen_genre": None,
        "genre_enum": None,
        "genre_enum_source": None,
        "lookup_works": None,
        "product_slug_count": 0,
        "notes": [],
    }
    manifest["harvest"] = harvest
    fallback_slugs = []

    # (a) embedded JSON extraction -- static DOMs first, raw-HTML fallback
    await run_embedded_harvest(browser, out_root, st, manifest, manifest_path)
    flush_manifest(manifest, manifest_path)

    # (b) live observation + in-page fetch harvest
    context = await browser.new_context(**context_kwargs(VIEWPORTS[0]))
    flags = {"closing": False}
    pending = []
    try:
        await context.route("**/*", route_block_skiphosts)
        context.on("response", make_response_handler(st, pending, flags))
        page = await context.new_page()
        observed = []
        page.on("request", lambda r: observed.append(r.url) if "/store/api/" in r.url else None)
        await page.goto(assert_allowed(BASE + "/store/search?search=portal"),
                        wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(BASE_SETTLE_MS / 1000)
        for _ in range(24):
            if observed:
                break
            await asyncio.sleep(0.5)
        harvest["observed_store_api_requests"] = [redact_text(u)[0] for u in dict.fromkeys(observed)]
        search_obs = next((u for u in observed if "/store/api/search" in u), None)
        if search_obs:
            base_params = dict(parse_qsl(urlparse(search_obs).query))
            harvest["notes"].append("search params taken from a request the page itself issued")
        else:
            base_params = dict(DEFAULT_SEARCH_PARAMS)
            harvest["notes"].append("no /store/api/search request observed; using historical default params")
        base_params.setdefault("search", "portal")
        harvest["search_params_used"] = redact_json_obj(base_params)[0]

        async def fetch_json(u, attempts=2):
            last = None
            for i in range(attempts):
                try:
                    res = await page.evaluate(FETCH_JS, {"u": u, "xrw": i > 0})
                except PlaywrightError as exc:
                    last = {"status": None, "text": "", "error": str(exc).splitlines()[0][:200]}
                    await asyncio.sleep(2.0)
                    continue
                last = res
                if res.get("status") == 200 and res.get("text"):
                    return res
                await asyncio.sleep(2.0)
            return last

        # search subset: portal, pages 0 and 1
        search_payloads = []
        for pn in (0, 1):
            res = await fetch_json(build_search_url(base_params, {"page": str(pn), "search": "portal"}))
            search_payloads.append(save_harvest_json(api_dir, st, harvest, f"search-portal-p{pn}.json", res))
            await asyncio.sleep(1.0)
        page_size = base_params.get("page_size")
        if not page_size and isinstance(search_payloads[0], dict):
            c = payload_item_count(search_payloads[0])
            page_size = str(c) if c else None
        harvest["page_size"] = page_size

        # genre enum from storefront constants (the embedded harvest above may
        # already have populated it from raw pre-hydration /store HTML)
        genre_list = harvest.get("genre_enum") or None
        if genre_list is None:
            constants_text = None
            constants_src = None
            try:
                constants_text = await page.evaluate(CONSTANTS_JS)
                if constants_text:
                    constants_src = "live store-search page"
            except PlaywrightError:
                pass
            if not constants_text:
                for vp_label in ("desktop", "mobile"):
                    dom_path = out_root / "static" / "store" / vp_label / "dom.html"
                    if dom_path.exists():
                        text, sid = extract_script_json(dom_path.read_text(encoding="utf-8"),
                                                        "storefront-constants-json-data",
                                                        fallback_tokens=("constants",))
                        if text:
                            constants_text = text
                            constants_src = f"static/store/{vp_label}/dom.html ({sid})"
                            break
            if constants_text:
                try:
                    constants_obj = json.loads(constants_text)
                    found = find_genre_enum(constants_obj)
                    if found:
                        harvest["genre_enum_source"] = f"{constants_src} at {found[0]}"
                        genre_list = found[1]
                    if "lookup" in constants_text.lower():
                        harvest["notes"].append("storefront constants mention 'lookup'")
                except json.JSONDecodeError:
                    harvest["notes"].append("storefront constants present but not parseable JSON")
            else:
                harvest["notes"].append("storefront-constants-json-data not found (live page or static DOMs)")
        if genre_list:
            harvest["genre_enum"] = genre_list
            chosen = next((g for g in genre_list if g.lower() == "adventure"), genre_list[0])
        else:
            chosen = "adventure"
            harvest["notes"].append("genre enum unavailable; falling back to literal 'adventure'")
        harvest["chosen_genre"] = chosen

        # category subset: chosen genre, bestselling, pages 0 and 1
        g_used = chosen
        g_slug = re.sub(r"[^a-z0-9]+", "-", chosen.lower()).strip("-") or "genre"
        cat_payloads = []
        for pn in (0, 1):
            res = await fetch_json(
                build_search_url(base_params, {"genre": g_used, "sort": "bestselling", "page": str(pn)},
                                 drop=("search",)),
                attempts=1)
            items = None
            if res and res.get("status") == 200:
                try:
                    items = payload_item_count(json.loads(res["text"]))
                except Exception:
                    items = None
            if pn == 0 and not items:
                alt = chosen.capitalize() if chosen == chosen.lower() else chosen.lower()
                if alt != g_used:
                    res2 = await fetch_json(
                        build_search_url(base_params,
                                         {"genre": alt, "sort": "bestselling", "page": str(pn)},
                                         drop=("search",)),
                        attempts=1)
                    items2 = None
                    if res2 and res2.get("status") == 200:
                        try:
                            items2 = payload_item_count(json.loads(res2["text"]))
                        except Exception:
                            items2 = None
                    if items2:
                        g_used = alt
                        res = res2
                        harvest["notes"].append(f"genre value case-adjusted to {alt!r}")
            cat_payloads.append(save_harvest_json(api_dir, st, harvest, f"category-{g_slug}-p{pn}.json", res))
            await asyncio.sleep(1.0)
        harvest["chosen_genre"] = g_used

        # product detail lookup for every slug in the four harvested pages
        slugs = []
        for payload in search_payloads + cat_payloads:
            if payload is not None:
                for s in collect_human_urls(payload):
                    if s not in slugs:
                        slugs.append(s)
        harvest["product_slug_count"] = len(slugs)

        test_slugs = slugs[:1] if slugs else ["satisfactory"]
        lookup_works = False
        test = await fetch_json(build_lookup_url(test_slugs), attempts=2)
        if test and test.get("status") == 200:
            try:
                tp = json.loads(test["text"])
                lookup_works = bool(payload_item_count(tp) or (isinstance(tp, dict) and tp))
            except json.JSONDecodeError:
                lookup_works = False
        harvest["lookup_works"] = lookup_works
        if lookup_works and slugs:
            batch_no = 0
            for start in range(0, len(slugs), 20):
                batch_no += 1
                res = await fetch_json(build_lookup_url(slugs[start:start + 20]), attempts=2)
                save_harvest_json(api_dir, st, harvest, f"product-detail-{batch_no}.json", res)
                await asyncio.sleep(1.2)
        else:
            harvest["notes"].append("lookup-unavailable")
            search_slugs = []
            for payload in search_payloads:
                if payload is not None:
                    for s in collect_human_urls(payload):
                        if s not in search_slugs:
                            search_slugs.append(s)
            fallback_slugs = search_slugs[:6]

        obs_doc = {
            "observed_store_api_requests": harvest["observed_store_api_requests"],
            "search_endpoint": {
                "path": "/store/api/search",
                "params_template": harvest["search_params_used"],
                "page_param": "page",
                "page_size": harvest["page_size"],
            },
            "chosen_genre": harvest["chosen_genre"],
            "genre_enum": harvest["genre_enum"],
            "genre_enum_source": harvest["genre_enum_source"],
            "lookup_endpoint": {
                "path": "/store/api/lookup",
                "pattern": "/store/api/lookup?products[]=<slug>&products[]=<slug>...&request=1",
                "works": harvest["lookup_works"],
            },
            "notes": harvest["notes"],
            "ts_utc": now_utc(),
        }
        obs_doc, n = redact_json_obj(obs_doc)
        st["redactions_json"] += n
        (api_dir / "observed-endpoints.json").write_text(json.dumps(obs_doc, indent=1), encoding="utf-8")
        harvest["files"]["observed-endpoints.json"] = {"status": "written"}
        flush_manifest(manifest, manifest_path)
        flush_url_map(st)
        return fallback_slugs
    finally:
        flags["closing"] = True
        for t in pending:
            if not t.done():
                t.cancel()
        try:
            await context.close()
        except BaseException:
            pass


# ----- entry ----------------------------------------------------------------

async def amain(args):
    out_root = Path(args.out).resolve()
    (out_root / "static").mkdir(parents=True, exist_ok=True)
    blob_dir = out_root / "assets" / "blobs"
    blob_dir.mkdir(parents=True, exist_ok=True)
    (out_root / "api-harvest").mkdir(parents=True, exist_ok=True)
    manifest_path = out_root / "capture-manifest.json"
    url_map_path = out_root / "assets" / "url-map.json"

    manifest = {"run": {}, "cells": {}, "assets": {}, "harvest": {}, "findings": {}, "sanitization": {}}
    prev = {}
    if manifest_path.exists():
        try:
            prev = json.loads(manifest_path.read_text(encoding="utf-8"))
            for k in ("cells", "harvest", "findings"):
                if isinstance(prev.get(k), dict):
                    manifest[k] = prev[k]
        except json.JSONDecodeError:
            prev = {}

    st = {
        "blob_dir": blob_dir,
        "url_map": {},
        "url_map_path": url_map_path,
        "asset_unique_count": 0,
        "asset_unique_bytes": 0,
        "asset_read_errors": 0,
        "asset_skipped_large": 0,
        "redactions_html": 0,
        "redactions_json": 0,
    }
    if url_map_path.exists():
        try:
            st["url_map"] = json.loads(url_map_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            st["url_map"] = {}
    if args.harvest_only or args.embedded_only:
        # partial rerun: keep sanitization counters cumulative
        prev_san = prev.get("sanitization") or {}
        st["redactions_html"] += int(prev_san.get("csrf_redactions_in_html") or 0)
        st["redactions_json"] += int(prev_san.get("csrf_redactions_in_json") or 0)

    checkpoints = build_checkpoints()
    if args.only:
        wanted = [w.strip() for w in args.only.split(",") if w.strip()]
        valid = {cp["id"] for cp in checkpoints}
        unknown = [w for w in wanted if w not in valid]
        if unknown:
            raise SystemExit(f"unknown checkpoint ids {unknown}; valid: {sorted(valid)}")
        checkpoints = [cp for cp in checkpoints if cp["id"] in wanted]
    viewports = VIEWPORTS
    if args.viewports:
        wanted_vp = [w.strip() for w in args.viewports.split(",") if w.strip()]
        viewports = [vp for vp in VIEWPORTS if vp["label"] in wanted_vp]
        if not viewports:
            raise SystemExit("no viewports selected")

    started = now_utc()
    async with async_playwright() as p:
        headless = not args.headed
        browser = await p.chromium.launch(headless=headless)
        try:
            pre = await preflight(browser)
        except Exception as exc:
            pre = {"error": str(exc)[:200]}
        run_notes = []
        if pre.get("challenged") and headless:
            run_notes.append("headless preflight hit a challenge on /; relaunched headed")
            await browser.close()
            headless = False
            browser = await p.chromium.launch(headless=False)
            try:
                pre = await preflight(browser)
            except Exception as exc:
                pre = {"error": str(exc)[:200]}
        manifest["run"] = {
            "target": BASE,
            "out_root": str(out_root),
            "started_utc": started,
            "browser_version": browser.version,
            "user_agent": pre.get("user_agent"),
            "preflight": {k: pre.get(k) for k in ("status", "challenged", "error") if k in pre},
            "headless": headless,
            "mode": ("embedded-only" if args.embedded_only else
                     "harvest-only" if args.harvest_only else "full"),
            "locale": "en-US",
            "workers": args.workers,
            "viewports": [vp["label"] for vp in viewports],
            "base_settle_ms": BASE_SETTLE_MS,
            "notes": run_notes + [
                "contexts are ephemeral; cookies/session state never persisted",
                "request/response headers never saved",
                "analytics/consent/captcha hosts route-blocked on www cells (not on support-home)",
            ],
        }
        flush_manifest(manifest, manifest_path)

        if args.embedded_only:
            await run_embedded_harvest(browser, out_root, st, manifest, manifest_path)
        else:
            if not args.harvest_only:
                cells = [(cp, vp) for vp in viewports for cp in checkpoints]
                await run_matrix(browser, cells, st, manifest, out_root, manifest_path, args.workers)
            if not args.no_harvest:
                fallback_slugs = []
                try:
                    fallback_slugs = await run_harvest(browser, out_root, st, manifest, manifest_path)
                except Exception as exc:
                    manifest.setdefault("harvest", {}).setdefault("notes", []).append(
                        f"harvest-error: {type(exc).__name__}: {str(exc)[:200]}")
                    flush_manifest(manifest, manifest_path)
                if fallback_slugs:
                    fb = [{"id": f"store-product-{s}", "url": f"{BASE}/store/{s}",
                           "readiness": PRODUCT_READY} for s in fallback_slugs]
                    await run_matrix(browser, [(cp, VIEWPORTS[0]) for cp in fb],
                                     st, manifest, out_root, manifest_path, min(args.workers, 2))
        await browser.close()

    ok = sum(1 for c in manifest["cells"].values() if c.get("status") == "ok")
    failed = sum(1 for c in manifest["cells"].values() if c.get("status") != "ok")
    manifest["assets"] = {
        "url_count": len(st["url_map"]),
        "unique_blobs_added_this_run": st["asset_unique_count"],
        "unique_blob_bytes_added_this_run": st["asset_unique_bytes"],
        "blob_count_on_disk": sum(1 for _ in blob_dir.glob("*/*")),
        "blob_bytes_on_disk": sum(f.stat().st_size for f in blob_dir.glob("*/*")),
        "read_errors": st["asset_read_errors"],
        "skipped_over_15mb": st["asset_skipped_large"],
    }
    sup_cells = {k: v for k, v in manifest["cells"].items() if k.startswith("support-home/")}
    if sup_cells:
        manifest["findings"]["support_home"] = {
            k: {"status": v.get("status"), "http_status": v.get("http_status"), "reason": v.get("reason")}
            for k, v in sup_cells.items()}
    manifest["sanitization"] = {
        "csrf_redactions_in_html": st["redactions_html"],
        "csrf_redactions_in_json": st["redactions_json"],
        "policy": ("values of any key matching /csrf/i replaced with REDACTED-CSRF-TOKEN; "
                   "no cookies, tokens or request/response headers saved"),
    }
    manifest["run"]["finished_utc"] = now_utc()
    manifest["run"]["cells_ok"] = ok
    manifest["run"]["cells_failed"] = failed
    flush_manifest(manifest, manifest_path)
    flush_url_map(st)
    log(f"DONE cells ok={ok} failed={failed} asset_urls={manifest['assets']['url_count']} "
        f"blob_bytes={manifest['assets']['blob_bytes_on_disk']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--only", default=None, help="comma-separated checkpoint ids")
    ap.add_argument("--viewports", default=None, help="comma-separated labels: desktop,mobile")
    ap.add_argument("--workers", type=int, default=3, help="parallel browser contexts (hard max 4)")
    ap.add_argument("--headed", action="store_true", help="run headed instead of headless")
    ap.add_argument("--no-harvest", action="store_true", help="skip the API harvest phase")
    ap.add_argument("--harvest-only", action="store_true", help="skip the static matrix")
    ap.add_argument("--embedded-only", action="store_true",
                    help="only (re-)extract embedded json-data payloads")
    args = ap.parse_args()
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()
