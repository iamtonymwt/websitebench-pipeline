"""Fetch the assets the captured pages declare.

This site splits into two halves and they need different transports:

* `images.monoprice.com` -- open. Plain HTTP works, in parallel, no browser.
  This is the bulk: every product photo.
* `www.monoprice.com/assets/`, `/Scripts/`, `/cf-fonts/` -- behind the same
  Cloudflare challenge as the HTML. A plain client is answered 403 with a
  challenge shell, which is *not* an error the retry logic would notice: it is a
  well-formed 5.7 KB response. These have to come through the browser, and the
  challenge shell must be detected by content or we will save 5.7 KB of
  "Just a moment..." under the name of every stylesheet on the site.

Two rules carried over from earlier sites, both learned by breaking them:

* Decode %XX when naming the file on disk. Starlette decodes the request path
  before looking at the filesystem, so a file stored with the escape still in its
  name exists, is referenced correctly, and 404s anyway.
* Size limits apply to media only. Never to CSS or fonts. A limit that drops a
  stylesheet takes the site's entire visual layer with it, and every closure gate
  stays green because a page with no stylesheet makes no requests.

    python3 tools/fetch_assets.py plan --capture-dir source-current --out scope/asset-plan.json
    python3 tools/fetch_assets.py fetch --plan scope/asset-plan.json --assets-dir source-assets
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from browser_session import attach  # noqa: E402
from capture_pages import decode_image_field, read_body  # noqa: E402

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# `/p/shop/` and `/p/resources/` -- 3,328 pages of this site -- are a Webflow
# build. Their stylesheets, their scripts and 5,019 of their product photographs
# are served from Webflow's CDN, and nothing of theirs is on monoprice.com at
# all. Treating those hosts as third parties would have frozen every one of
# those pages as unstyled HTML with no images, and no closure gate would have
# said a word: a page with no stylesheet makes no request.
#
# These are approved external *resource* origins -- origins the page itself
# requests for static assets. They are not trackers and nothing is sent to them.
WEBFLOW_HOSTS = {
    "cdn.prod.website-files.com",     # Webflow assets: css, js, images
    "d3e54v103j8qbb.cloudfront.net",  # Webflow's jQuery build
    "cdnjs.cloudflare.com",           # font-awesome, linked by those pages
}
OPEN_HOSTS = {"images.monoprice.com"} | WEBFLOW_HOSTS
CHALLENGED_HOSTS = {"www.monoprice.com", "monoprice.com"}

# Media only. Stylesheets, scripts and fonts are never capped -- see the module
# docstring.
MEDIA_BYTE_LIMIT = 8 * 1024 * 1024
MEDIA_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".mp4",
                  ".webm", ".mov", ".avif", ".ico", ".bmp"}
NEVER_CAPPED = {".css", ".js", ".woff", ".woff2", ".ttf", ".otf", ".eot", ".json"}

# Reference forms that appear in this site's markup and CSS.
REF_PATTERNS = (
    re.compile(r"""\b(?:src|href|poster|data-src|data-original)\s*=\s*(["'])(.*?)\1""", re.I | re.S),
    re.compile(r"""\b(?:srcset|imagesrcset|data-srcset)\s*=\s*(["'])(.*?)\1""", re.I | re.S),
    re.compile(r"""url\(\s*(['"]?)([^)'"]+)\1\s*\)""", re.I),
)


def iter_refs(html: str):
    for pat in REF_PATTERNS:
        for m in pat.finditer(html):
            value = m.group(2)
            if "srcset" in (m.re.pattern or "") and "," in value:
                for part in value.split(","):
                    cand = part.strip().split()[0] if part.strip() else ""
                    if cand:
                        yield cand
            else:
                yield value


def asset_target(url: str) -> tuple[str, str] | None:
    """(host, local relative path) for a URL we should fetch, else None."""
    try:
        u = urllib.parse.urlsplit(url)
    except ValueError:
        return None
    if u.scheme not in ("http", "https"):
        return None
    host = u.netloc.lower()
    if host not in OPEN_HOSTS | CHALLENGED_HOSTS:
        return None
    path = u.path
    if host in CHALLENGED_HOSTS:
        # Only real asset trees. HTML routes are captured by capture_pages.py.
        # `/CommissionJunction/` is deliberately absent: it is a first-party path
        # that exists only to carry a third-party affiliate tag, and fetching it
        # would put a tracker in the asset tree under a first-party name.
        if not re.match(r"^/(assets|Scripts|src|Content|cf-fonts)/", path, re.I):
            return None
    if not path or path.endswith("/"):
        return None
    # Decode now, at naming time, so the byte on disk carries the name the HTTP
    # layer will look for. The URL in the rewritten markup keeps its escapes;
    # the browser re-encodes on its own.
    local = urllib.parse.unquote(path.lstrip("/"))
    if u.query:
        # Cache-buster queries name the same byte. Keep one file. `bust` was
        # missing from this list and RequireJS appends it to every module it
        # loads, so the runtime pass planned a second copy of a dozen scripts
        # already on disk -- same bytes, different filename, and the frozen
        # pages would then reference whichever one the rewrite happened to pick.
        keep = [(k, v) for k, v in urllib.parse.parse_qsl(u.query)
                if k.lower() not in {"v", "ver", "version", "_", "cb", "t",
                                     "bust", "rev", "cachebust"}]
        if keep:
            # The suffix goes *before* the extension. Appending it after gave
            # `jquery-3.5.1.min.js__site=6807...`, whose suffix is no longer
            # `.js` -- so the app would serve it as octet-stream and the browser
            # would refuse to execute it. Webflow's jQuery, on 3,328 pages,
            # would simply not run, and nothing would report a failure.
            stem, dot, extension = local.rpartition(".")
            marker = "__" + re.sub(r"[^A-Za-z0-9._=-]+", "-",
                                   urllib.parse.urlencode(keep))[:60]
            local = f"{stem}{marker}{dot}{extension}" if dot else local + marker
    local = re.sub(r"[<>:\"|?*]", "_", local)
    return host, local


def build_plan(capture_dir: pathlib.Path, out: pathlib.Path) -> int:
    refs: dict[str, dict] = {}
    pages = 0
    extracts = 0
    unparsable = 0
    for page_dir in sorted(capture_dir.glob("*/*")):
        if not page_dir.is_dir():
            continue
        meta_path = page_dir / "fetch.json"
        base = json.loads(meta_path.read_text())["url"] if meta_path.exists() else None

        # Product pages past the body sample keep only a structured extract, and
        # their image URLs live in it. Reading bodies alone would have planned
        # 5,291 images for a catalogue of 5,600 products -- the clone would then
        # serve product pages referencing pictures nobody fetched. What the plan
        # must cover is what the clone will *reference*, not what happens to
        # still have a body on disk.
        extract_path = page_dir / "extract.json"
        if extract_path.exists():
            extracts += 1
            record = json.loads(extract_path.read_text(encoding="utf-8"))
            for image_url in decode_image_field(
                    (record.get("product") or {}).get("image")):
                target = asset_target(image_url)
                if target is None:
                    continue
                host, local = target
                rec = refs.setdefault(f"{host}/{local}",
                                      {"url": image_url, "host": host,
                                       "local": local, "referrers": 0})
                rec["referrers"] += 1

        html = read_body(page_dir)
        if html is None:
            continue
        pages += 1
        for raw in iter_refs(html):
            raw = raw.strip()
            if not raw or raw.startswith(("data:", "javascript:", "mailto:", "tel:", "#")):
                continue
            try:
                absolute = urllib.parse.urljoin(base or "https://www.monoprice.com/",
                                                raw.replace("&amp;", "&"))
            except ValueError:
                unparsable += 1
                continue
            target = asset_target(absolute)
            if target is None:
                continue
            host, local = target
            key = f"{host}/{local}"
            rec = refs.setdefault(key, {"url": absolute, "host": host,
                                        "local": local, "referrers": 0})
            rec["referrers"] += 1

    by_host = collections.Counter(r["host"] for r in refs.values())
    plan = {
        "schema_version": "monoprice.asset-plan.v1",
        "capture_dir": str(capture_dir),
        "pages_read": pages,
        "unparsable_references": unparsable,
        "assets": len(refs),
        "by_host": dict(by_host),
        "transport": {h: ("plain-http" if h in OPEN_HOSTS else "browser")
                      for h in by_host},
        "entries": sorted(refs.values(), key=lambda r: -r["referrers"]),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in plan.items() if k != "entries"}, indent=2))
    return 0


def _capped(local: str) -> int | None:
    suffix = pathlib.PurePosixPath(local).suffix.lower()
    if suffix in NEVER_CAPPED:
        return None
    if suffix in MEDIA_SUFFIXES:
        return MEDIA_BYTE_LIMIT
    return None


def _fetch_plain(entry: dict, assets_dir: pathlib.Path, timeout: float) -> dict:
    dest = assets_dir / entry["host"] / entry["local"]
    if dest.exists() and dest.stat().st_size > 0:
        return {"key": f"{entry['host']}/{entry['local']}", "status": "cached",
                "bytes": dest.stat().st_size}
    # The source publishes image URLs with literal spaces and other unescaped
    # characters ("cms_images/US Coast Guard.png"). urllib raises on those in
    # putrequest -- and that is not a network error, so the retry and backoff
    # logic never sees it; it propagates and kills the worker. Encode the path
    # before asking, while the file on disk keeps its decoded name.
    split = urllib.parse.urlsplit(entry["url"])
    safe_url = urllib.parse.urlunsplit((
        split.scheme, split.netloc,
        urllib.parse.quote(split.path, safe="/%~!$&'()*+,;=:@"),
        urllib.parse.quote(split.query, safe="/%~!$&'()*+,;=:@?"),
        "",
    ))
    req = urllib.request.Request(safe_url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            declared = resp.headers.get("Content-Length")
            limit = _capped(entry["local"])
            # Read the length off the response we already have rather than
            # spending a HEAD on every file to find out. A HEAD preflight on
            # thousands of in-limit assets costs more than the rare oversize
            # download it avoids.
            if limit and declared and int(declared) > limit:
                return {"key": f"{entry['host']}/{entry['local']}",
                        "status": "over-limit", "bytes": int(declared)}
            body = resp.read(limit + 1 if limit else None)
            status = resp.status
    except urllib.error.HTTPError as exc:
        return {"key": f"{entry['host']}/{entry['local']}", "status": f"http-{exc.code}"}
    except UnicodeEncodeError as exc:
        # Not a network error, so no amount of retrying helps. Encode the path
        # and try once more rather than letting this kill the whole run.
        return {"key": f"{entry['host']}/{entry['local']}",
                "status": "unicode-url", "error": str(exc)[:120]}
    except Exception as exc:  # noqa: BLE001
        return {"key": f"{entry['host']}/{entry['local']}",
                "status": "error", "error": f"{exc.__class__.__name__}"}
    if limit and len(body) > limit:
        return {"key": f"{entry['host']}/{entry['local']}", "status": "over-limit",
                "bytes": len(body)}
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    return {"key": f"{entry['host']}/{entry['local']}", "status": "fetched",
            "bytes": len(body), "http": status}


BROWSER_FETCH = r"""async ({urls}) => {
  const out = [];
  for (const url of urls) {
    try {
      const r = await fetch(url, {cache: 'no-store'});
      const buf = await r.arrayBuffer();
      const bytes = new Uint8Array(buf);
      let bin = '';
      for (let i = 0; i < bytes.length; i += 0x8000) {
        bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
      }
      out.push({url, status: r.status, b64: btoa(bin),
                type: r.headers.get('content-type') || ''});
    } catch (e) {
      out.push({url, error: String(e).slice(0, 160)});
    }
  }
  return out;
}"""


def _fetch_via_browser(entries: list[dict], assets_dir: pathlib.Path) -> list[dict]:
    import base64

    results: list[dict] = []
    todo = [e for e in entries
            if not (assets_dir / e["host"] / e["local"]).exists()]
    for e in entries:
        dest = assets_dir / e["host"] / e["local"]
        if dest.exists() and dest.stat().st_size > 0:
            results.append({"key": f"{e['host']}/{e['local']}", "status": "cached",
                            "bytes": dest.stat().st_size})
    if not todo:
        return results
    # Tab index 1: the capture loop owns tab 0. Same browser, so the challenge
    # clearance is shared and no second window appears.
    with attach(page_index=1) as (_browser, _context, page):
        for start in range(0, len(todo), 12):
            chunk = todo[start:start + 12]
            rows = page.evaluate(BROWSER_FETCH, {"urls": [e["url"] for e in chunk]})
            for entry, row in zip(chunk, rows, strict=False):
                key = f"{entry['host']}/{entry['local']}"
                if "error" in row:
                    results.append({"key": key, "status": "error",
                                    "error": row["error"]})
                    continue
                body = base64.b64decode(row["b64"])
                # A Cloudflare challenge shell is a *successful-looking* response.
                # Saving it under the name of a stylesheet is how a site loses its
                # visual layer while every gate stays green.
                head = body[:400].decode("utf-8", "replace")
                if "Just a moment" in head or "cf_chl_opt" in head:
                    results.append({"key": key, "status": "challenge-shell",
                                    "bytes": len(body)})
                    continue
                if row["status"] != 200:
                    results.append({"key": key, "status": f"http-{row['status']}"})
                    continue
                dest = assets_dir / entry["host"] / entry["local"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(body)
                results.append({"key": key, "status": "fetched", "bytes": len(body)})
            print(f"  browser assets {min(start + 12, len(todo))}/{len(todo)}")
    return results


def run_fetch(plan_path: pathlib.Path, assets_dir: pathlib.Path, workers: int,
              timeout: float, report_path: pathlib.Path) -> int:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    entries = plan["entries"]
    plain = [e for e in entries if e["host"] in OPEN_HOSTS]
    browser = [e for e in entries if e["host"] in CHALLENGED_HOSTS]
    print(f"{len(plain)} assets over plain HTTP, {len(browser)} through the browser")

    started = time.time()
    results: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_fetch_plain, e, assets_dir, timeout) for e in plain]
        for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            results.append(fut.result())
            if i % 250 == 0:
                ok = sum(1 for r in results if r["status"] in ("fetched", "cached"))
                print(f"  plain {i}/{len(plain)} ok={ok} "
                      f"{i / max(0.001, time.time() - started):.0f}/s")

    results.extend(_fetch_via_browser(browser, assets_dir))

    tally = collections.Counter(r["status"] for r in results)
    report = {
        "schema_version": "monoprice.asset-fetch.v1",
        "plan": str(plan_path),
        "assets_dir": str(assets_dir),
        "requested": len(entries),
        "status_tally": dict(tally),
        "bytes_written": sum(r.get("bytes", 0) for r in results
                             if r["status"] == "fetched"),
        "seconds": round(time.time() - started, 1),
        "failures": [r for r in results
                     if r["status"] not in ("fetched", "cached")][:400],
        "failures_total": sum(v for k, v in tally.items()
                              if k not in ("fetched", "cached")),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "failures"}, indent=2))
    if report["failures_total"] > len(report["failures"]):
        print(f"NOTE: the failure list in the report is capped at 400 of "
              f"{report['failures_total']}. Read status_tally for the true counts.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan")
    p.add_argument("--capture-dir", required=True)
    p.add_argument("--out", required=True)

    f = sub.add_parser("fetch")
    f.add_argument("--plan", required=True)
    f.add_argument("--assets-dir", required=True)
    f.add_argument("--report", default="scope/asset-fetch.json")
    f.add_argument("--workers", type=int, default=12)
    f.add_argument("--timeout", type=float, default=20.0)

    args = ap.parse_args()
    if args.cmd == "plan":
        return build_plan(pathlib.Path(args.capture_dir), pathlib.Path(args.out))
    return run_fetch(pathlib.Path(args.plan), pathlib.Path(args.assets_dir),
                     args.workers, args.timeout, pathlib.Path(args.report))


if __name__ == "__main__":
    raise SystemExit(main())
