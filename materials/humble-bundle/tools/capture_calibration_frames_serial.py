"""Three-frame calibration capture — SINGLE headed chromium instance, offscreen.

Single-browser rule: one launch, one context, one page, strictly serial.
Window is positioned offscreen (--window-position=-3200,100) so it never
steals focus. Frame-major rounds space same-cell frames a full round apart.
Resumable: complete frame dirs (both screenshots + meta) are skipped.
"""
import json
import datetime
import pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path("materials/humble-bundle/source-current/calibration/frames")
BASE = "https://www.humblebundle.com"
CPS = [
    ("home", "/"),
    ("bundles", "/bundles"),
    ("games", "/games"),
    ("bundle-anchor", "/games/yes-chef-cooking-bundle"),
    ("store", "/store"),
    ("store-search", "/store/search?search=portal"),
    ("store-search-noresults", "/store/search?search=zzzz-no-match-websitebench"),
    ("store-product-satisfactory", "/store/satisfactory"),
    ("login", "/login"),
    ("signup", "/signup"),
    ("membership", "/membership"),
    ("notfound-404", "/this-page-does-not-exist-websitebench"),
]
VPS = {"desktop": (1440, 900, 1), "mobile": (390, 844, 2)}
FRAMES = 3

def done(d):
    return all((d / n).exists() for n in ("screenshot.png", "screenshot-full.png", "meta.json"))

def capture(pg, cp, url, vp, d):
    w, h, dsf = VPS[vp]
    pg.set_viewport_size({"width": w, "height": h})
    pg.goto(BASE + url if url.startswith("/") else url, wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(4000)
    pg.evaluate("""async () => { for (let y = 0; y < document.body.scrollHeight; y += 800) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 180)); } window.scrollTo(0, 0); await new Promise(r => setTimeout(r, 700)); }""")
    d.mkdir(parents=True, exist_ok=True)
    pg.screenshot(path=str(d / "screenshot.png"))
    pg.screenshot(path=str(d / "screenshot-full.png"), full_page=True)
    json.dump({"url": pg.url, "title": pg.title(), "viewport": f"{w}x{h}", "dsf_note": f"window dsf native (target {dsf})",
               "ts_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "runner": "single-instance-serial-offscreen"}, open(d / "meta.json", "w"), indent=1)

with sync_playwright() as p:
    b = p.chromium.launch(headless=False, args=["--window-position=-3200,100", "--window-size=1500,980", "--mute-audio"])
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, locale="en-US", timezone_id="America/New_York")
    pg = ctx.new_page()
    todo = skipped = failed = 0
    for f in range(1, FRAMES + 1):
        for cp, url in CPS:
            for vp in VPS:
                d = ROOT / cp / vp / f"frame-{f}"
                if done(d):
                    skipped += 1
                    continue
                try:
                    ctx.clear_cookies()
                    capture(pg, cp, url, vp, d)
                    todo += 1
                    print(f"ok {cp}/{vp}/frame-{f}", flush=True)
                except Exception:
                    try:
                        ctx.clear_cookies()
                        capture(pg, cp, url, vp, d)
                        todo += 1
                        print(f"ok(retry) {cp}/{vp}/frame-{f}", flush=True)
                    except Exception as e2:
                        failed += 1
                        print(f"FAIL {cp}/{vp}/frame-{f}: {str(e2)[:120]}", flush=True)
    b.close()
    print(json.dumps({"captured": todo, "skipped_existing": skipped, "failed": failed}))
