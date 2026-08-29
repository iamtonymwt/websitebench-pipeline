"""Clone-vs-source visual audit: MAE similarity per checkpoint x viewport.

Compares the running local clone (127.0.0.1:8098) against the frozen source
screenshots from the static capture matrix. Diagnostic aid only.

Rendering identity: HEADED chromium (the source frames were captured headed;
headless anti-aliasing skews similarity by 1-2%). Single-browser rule: one
browser per viewport pass, ONE window, positioned offscreen so it never
disturbs the user. Waits for document.fonts.ready before shooting.
"""
import json
import pathlib

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path("materials/humble-bundle")
SRC = ROOT / "source-current/2026-08-20.humble-bundle-r1/static"
OUT = pathlib.Path("artifacts/humble-bundle-preflight/clone-audit/matrix")
BASE = "http://127.0.0.1:8098"
CELLS = json.loads((ROOT / "clone/frontend/pages-manifest.json").read_text())
SKIP = {"notfound-404"}  # route is a 404 handler; audited separately
VP_CTX = {
    "desktop": {"viewport": {"width": 1440, "height": 900}},
    "mobile": {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 2},
}
SETTLE_JS = """async () => {
  if (document.fonts && document.fonts.ready) { try { await document.fonts.ready; } catch (e) {} }
  for (let y = 0; y < document.body.scrollHeight; y += 800) {
    window.scrollTo(0, y); await new Promise(r => setTimeout(r, 120));
  }
  window.scrollTo(0, 0);
  await new Promise(r => setTimeout(r, 600));
}"""


def mae_similarity(a: Image.Image, b: Image.Image) -> float:
    if a.size != b.size:
        b = b.resize(a.size)
    diff = ImageChops.difference(a.convert("RGB"), b.convert("RGB"))
    h = diff.histogram()
    total = 0
    n = a.size[0] * a.size[1] * 3
    for ch in range(3):
        for v, c in enumerate(h[ch * 256:(ch + 1) * 256]):
            total += v * c
    return 1.0 - (total / n) / 255.0


rows = []


def run_pass(p, vp: str) -> None:
    b = p.chromium.launch(
        headless=False,
        args=["--window-position=-3200,100", "--window-size=1500,980", "--mute-audio"],
    )
    ctx = b.new_context(locale="en-US", timezone_id="America/New_York", **VP_CTX[vp])
    pg = ctx.new_page()
    for name, meta in sorted(CELLS.items()):
        if name in SKIP:
            continue
        route = meta["route"] if isinstance(meta, dict) else meta
        if not str(route).startswith("/"):
            continue
        src_png = SRC / name / vp / "screenshot.png"
        if not src_png.exists():
            continue
        try:
            pg.goto(BASE + route, wait_until="domcontentloaded", timeout=30000)
            pg.wait_for_timeout(3200)
            pg.evaluate(SETTLE_JS)
            d = OUT / name / vp
            d.mkdir(parents=True, exist_ok=True)
            shot = d / "clone.png"
            pg.screenshot(path=str(shot))
            sim = mae_similarity(Image.open(shot), Image.open(src_png))
            rows.append((round(sim, 4), name, vp))
        except Exception as e:  # noqa: BLE001 - diagnostic harness records and continues
            rows.append((0.0, name, vp, str(e)[:80]))
    b.close()


with sync_playwright() as p:
    for vp in ("desktop", "mobile"):
        run_pass(p, vp)

rows.sort()
for r in rows:
    print("\t".join(str(x) for x in r))
OUT.mkdir(parents=True, exist_ok=True)
json.dump(rows, open(OUT / "ranking.json", "w"), indent=1)
