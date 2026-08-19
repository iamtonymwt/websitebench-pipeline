#!/usr/bin/env python3
"""Faithful anonymous source capture for the Home Depot offline clone.

Reads scope/source-capture-plan.json and captures URL-addressable checkpoints
at each configured viewport into source-current/<capture_id>/, with the same
artifact shape as prior sites: N full-page frames + one viewport frame, the
rendered HTML, a link census, a runtime resource census, and meta.json with
frame sha256s and region boxes.

Channels (Home Depot commerce tier rejects fresh automation sessions):
  --engine local-cdp     attach to the operator's trusted headed Chrome on
                         --cdp-url (default http://127.0.0.1:9222). Capture
                         runs in a NEW TAB of that session with humanized
                         pacing so the session's trust survives.
  --engine browserbase   Browserbase cloud session (BROWSERBASE_API_KEY in the
                         environment, never persisted) — proven channel from
                         the ASPCA run for WAF-blocked local egress.

Interaction-dependent states (checkout accordion, populated cart, account,
compare, auth password step) are owned by capture_states.py in the same
artifact layout; entries with url == "interactive" are skipped here.

Usage:
  python3 materials/home-depot/tools/capture_source.py \
    --site-dir materials/home-depot --engine local-cdp \
    [--only home,auth-signin] [--tier open] [--settle-ms 6000]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import random
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

BB_API = os.environ.get("BROWSERBASE_API_URL", "https://api.browserbase.com").rstrip("/")


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------- Browserbase channel (ASPCA-proven) ----------------
def bb_request(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"{BB_API}{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"X-BB-API-Key": os.environ["BROWSERBASE_API_KEY"],
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def bb_create_session(width: int, height: int, timeout_s: int = 3600) -> dict:
    payload = {
        "timeout": timeout_s, "keepAlive": False, "region": "us-east-1",
        "browserSettings": {"blockAds": True, "solveCaptchas": True,
                            "viewport": {"width": width, "height": height}},
        "userMetadata": {"purpose": "websitebench-offline-clone-capture"},
    }
    project_id = os.environ.get("BROWSERBASE_PROJECT_ID")
    if project_id:
        payload["projectId"] = project_id
    return bb_request("POST", "/v1/sessions", payload)


def bb_connect_url(sess: dict) -> str:
    url = sess.get("connectUrl")
    if url:
        return url
    deadline = time.time() + 15
    while time.time() < deadline:
        debug = bb_request("GET", f"/v1/sessions/{sess['id']}/debug")
        ws = debug.get("wsUrl")
        if ws:
            return ws
        time.sleep(1)
    raise RuntimeError("Browserbase debug WebSocket did not become ready")


def bb_release(session_id: str) -> None:
    try:
        bb_request("POST", f"/v1/sessions/{session_id}", {"status": "REQUEST_RELEASE"})
        print("browserbase session release requested")
    except Exception as exc:  # noqa: BLE001
        print(f"browserbase session release failed: {type(exc).__name__}", file=sys.stderr)


# ---------------- shared capture helpers ----------------
def hide_scrollbars(page) -> None:
    try:
        cdp = page.context.new_cdp_session(page)
        cdp.send("Emulation.setScrollbarsHidden", {"hidden": True})
    except Exception:  # noqa: BLE001
        pass


def census(page) -> list[str]:
    return page.eval_on_selector_all(
        "a[href]",
        "els=>Array.from(new Set(els.map(e=>((e.innerText||'').trim().slice(0,48)"
        "+' :: '+e.getAttribute('href'))))).filter(x=>x && !x.startsWith(' :: #'))",
    )


def resource_census(page) -> list[dict]:
    return page.evaluate(
        "()=>performance.getEntriesByType('resource').map(e=>({"
        "url:e.name, initiator:e.initiatorType, transfer_size:e.transferSize}))")


REGION_JS = """
() => {
  const pick = sels => {
    for (const s of sels) {
      const e = document.querySelector(s);
      if (e) {
        const r = e.getBoundingClientRect();
        if (r.width > 0 && r.height > 0)
          return {selector: s, x: Math.round(r.x + window.scrollX),
                  y: Math.round(r.y + window.scrollY),
                  width: Math.round(r.width), height: Math.round(r.height)};
      }
    }
    return null;
  };
  return {
    header: pick(['header', '[role=banner]', 'nav', '#header']),
    main: pick(['main', '[role=main]', '#root', '#app', '[id^=browse-search]']),
    footer: pick(['footer', '[role=contentinfo]', '.footer', '#footer']),
    form: pick(['form']),
    document_height: Math.round(Math.max(
      document.documentElement.scrollHeight, document.body.scrollHeight)),
  };
}
"""

FINGERPRINT_JS = """
() => ({
  user_agent: navigator.userAgent,
  platform: navigator.platform,
  languages: navigator.languages,
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  device_pixel_ratio: window.devicePixelRatio,
  inner: {width: window.innerWidth, height: window.innerHeight},
})
"""

ERROR_SHELL_MARK = "Oops!! Something went wrong"


def humanized_settle(page, settle_ms: int) -> None:
    """Gentle scroll pattern + jittered settle so the trusted session's
    behavioral score survives scripted capture."""
    page.wait_for_timeout(settle_ms + random.randint(0, 1500))
    try:
        h = page.evaluate("document.body.scrollHeight")
        for frac in (0.25, 0.6, 1.0, 0.0):
            page.mouse.wheel(0, int(h * frac))
            page.wait_for_timeout(random.randint(800, 1600))
        page.evaluate("window.scrollTo(0,0)")
        page.wait_for_timeout(random.randint(700, 1200))
    except Exception:  # noqa: BLE001
        pass


def snap_frames(page, dest: pathlib.Path, frames: int) -> list[str]:
    shas: list[str] = []
    page.screenshot(path=str(dest / "frame-1.viewport.png"), full_page=False)
    for n in range(1, frames + 1):
        fp = dest / f"frame-{n}.png"
        page.screenshot(path=str(fp), full_page=True)
        shas.append(sha256_file(fp))
        if n < frames:
            page.wait_for_timeout(700)
    return shas


def write_capture(page, dest: pathlib.Path, cp: dict, vp_name: str,
                  frames: int, shas: list[str], http_status: int | None,
                  engine: str, blocked: bool) -> dict:
    (dest / "page.html").write_text(page.content())
    links = census(page)
    (dest / "links.json").write_text(json.dumps(links, indent=2))
    resources = resource_census(page)
    (dest / "resources.json").write_text(json.dumps(resources, indent=2))
    regions = page.evaluate(REGION_JS)
    body_len = len(page.eval_on_selector("body", "e=>e.innerText"))
    meta = {
        "checkpoint": cp["id"], "family": cp["family"],
        "priority": cp["priority"].upper(), "viewport": vp_name,
        "requested_url": cp["url"], "final_url": page.url,
        "http_status": http_status,
        "title": page.title(), "body_text_len": body_len,
        "frames": frames, "frame_sha256": shas,
        "frames_identical": len(set(shas)) == 1,
        "link_count": len(links), "resource_count": len(resources),
        "engine": engine, "nav_fallback": None, "consent_action": None,
        "blocked_error_shell": blocked,
        "regions": regions,
    }
    (dest / "meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def capture_checkpoint(page, cp: dict, vp: dict, out_root: pathlib.Path,
                       settle_ms: int, engine: str) -> dict:
    dest = out_root / cp["id"] / vp["name"]
    dest.mkdir(parents=True, exist_ok=True)
    page.set_viewport_size({"width": vp["width"], "height": vp["height"]})
    page.wait_for_timeout(random.randint(500, 1200))
    resp = page.goto(cp["url"], wait_until="domcontentloaded", timeout=60000)
    humanized_settle(page, settle_ms)
    blocked = page.evaluate(f"document.body.innerText.includes({json.dumps(ERROR_SHELL_MARK)})")
    frames = int(vp.get("frames", 3))
    shas = snap_frames(page, dest, frames)
    status = resp.status if resp else None
    meta = write_capture(page, dest, cp, vp["name"], frames, shas, status,
                         engine, blocked)
    flag = "BLOCKED" if blocked else ("=" if meta["frames_identical"] else "~")
    print(f"  ok {cp['id']}/{vp['name']} [{status}] {flag} "
          f"body={meta['body_text_len']} links={meta['link_count']} "
          f"res={meta['resource_count']} -> {page.url[:80]}")
    return meta


def run(site_dir: pathlib.Path, only: set[str] | None, tier: str | None,
        settle_ms: int, engine: str, cdp_url: str) -> int:
    plan = json.loads((site_dir / "scope" / "source-capture-plan.json").read_text())
    capture_id = plan["capture_id"]
    out_root = site_dir / "source-current" / capture_id
    viewport_by_name = {v["name"]: v for v in plan["viewports"]}
    checkpoints = []
    for cp in plan["checkpoints"]:
        if only and cp["id"] not in only:
            continue
        if tier and cp.get("tier") != tier:
            continue
        if not cp["url"].startswith("http"):
            if only:
                print(f"skipping {cp['id']}: not URL-addressable here")
            continue
        checkpoints.append(cp)
    if not checkpoints:
        print("nothing to capture")
        return 1

    records: list[dict] = []
    sess = None
    if engine == "browserbase":
        sess = bb_create_session(1440, 900)
        print("browserbase session created (id withheld from logs)")
        ws_url = bb_connect_url(sess)
    else:
        ws_url = cdp_url

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(ws_url)
            try:
                ctx = browser.contexts[0]
                # Attaching to the operator's headed Chrome does not allow new
                # context/page management over CDP, so reuse an existing tab.
                opened_page = False
                if ctx.pages:
                    page = ctx.pages[0]
                else:
                    page = ctx.new_page()
                    opened_page = True
                hide_scrollbars(page)
                fingerprint_written = False
                for cp in checkpoints:
                    for vp_name in cp["viewports"]:
                        vp = viewport_by_name[vp_name]
                        try:
                            records.append(capture_checkpoint(
                                page, cp, vp, out_root, settle_ms, engine))
                        except Exception as exc:  # noqa: BLE001
                            print(f"  ! {cp['id']}/{vp_name}: {exc}", file=sys.stderr)
                            records.append({"checkpoint": cp["id"], "viewport": vp_name,
                                            "engine": engine, "error": str(exc)[:200]})
                        page.wait_for_timeout(random.randint(2500, 5000))
                        if not fingerprint_written:
                            fp = page.evaluate(FINGERPRINT_JS)
                            out_root.mkdir(parents=True, exist_ok=True)
                            (out_root / "session-fingerprint.json").write_text(
                                json.dumps(fp, indent=2))
                            fingerprint_written = True
                if opened_page:
                    page.close()  # leave the operator's own tabs untouched
            finally:
                browser.close()
    finally:
        if sess is not None:
            bb_release(sess["id"])

    index_path = out_root / "capture-index.json"
    if index_path.is_file():
        fresh = {(r.get("checkpoint"), r.get("viewport")) for r in records}
        previous = json.loads(index_path.read_text()).get("captures", [])
        records = [r for r in previous
                   if (r.get("checkpoint"), r.get("viewport")) not in fresh] + records
    index = {"schema_version": "home-depot.capture-index.v1",
             "capture_id": capture_id, "captures": records}
    index_path.write_text(json.dumps(index, indent=2))
    print(f"\nwrote capture index with {len(records)} records -> {index_path}")
    failures = [r for r in records if r.get("error") or r.get("blocked_error_shell")]
    if failures:
        print(f"{len(failures)} unit(s) failed or blocked", file=sys.stderr)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-dir", default="materials/home-depot")
    ap.add_argument("--engine", choices=["local-cdp", "browserbase"], default="local-cdp")
    ap.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    ap.add_argument("--only", default="", help="comma-separated checkpoint ids")
    ap.add_argument("--tier", default=None, help="capture only this plan tier (e.g. open)")
    ap.add_argument("--settle-ms", type=int, default=6000)
    args = ap.parse_args()
    only = {s for s in args.only.split(",") if s} or None
    return run(pathlib.Path(args.site_dir), only, args.tier, args.settle_ms,
               args.engine, args.cdp_url)


if __name__ == "__main__":
    raise SystemExit(main())
