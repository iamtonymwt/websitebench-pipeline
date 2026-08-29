#!/usr/bin/env python
"""Phase-6 three-frame visual-stability calibration capture for humblebundle.com.

Captures N (default 3) independent frames of every anonymous P0/P1
checkpoint x viewport cell -- each frame from a fresh ephemeral browser
context, frame starts spaced >= ~20s apart -- so the repository
calibrate-visual tool can derive pixel-MAE thresholds from source
self-variance. Reuses the checkpoint URL + readiness table and the
settle/sweep/viewport identities of capture_static_matrix.py.

Usage (from repo root):
  .venv/bin/python materials/humble-bundle/tools/capture_calibration_frames.py
  ... --only home,login --viewports desktop --frames 3 --out /path/to/frames

Hard rules (task brief + AGENTS.md):
  * read-only public GET page loads only; robots-disallowed paths refused
  * HEADED chromium only -- headless is served Cloudflare 403 on
    /store/api/* and error shells on store pages (verified in the
    static-matrix phase)
  * fresh ephemeral context per frame; no cookies/tokens/headers persisted
  * max 2 attempts per failing frame; 2 parallel browser contexts
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
import capture_static_matrix as csm  # noqa: E402  checkpoint table + helpers

CALIBRATION_CHECKPOINT_IDS = [
    "home",
    "bundles",
    "games",
    "bundle-anchor",
    "store",
    "store-search",
    "store-search-noresults",
    "store-product-satisfactory",
    "login",
    "signup",
    "membership",
    "notfound-404",
]

DEFAULT_OUT = Path(
    "/Users/wentaoma/Desktop/websitebench-pipeline/materials/humble-bundle/"
    "source-current/calibration/frames"
)
FRAME_GAP_S = 20.0
WORKERS = 2
ATTEMPT_TIMEOUT_S = 300


def checkpoints_by_id():
    table = {cp["id"]: cp for cp in csm.build_checkpoints()}
    missing = [cid for cid in CALIBRATION_CHECKPOINT_IDS if cid not in table]
    if missing:
        raise SystemExit(f"checkpoint ids missing from matrix table: {missing}")
    return table


async def capture_frame(browser, cp, vp, frame_dir, attempt):
    """One frame: fresh context -> settle -> readiness -> sweep -> screenshots."""
    frame_dir.mkdir(parents=True, exist_ok=True)
    context = await browser.new_context(**csm.context_kwargs(vp))
    notes = []
    result = {"ok": False, "reason": None, "http_status": None}
    try:
        await context.route("**/*", csm.route_block_skiphosts)
        page = await context.new_page()
        url = csm.assert_allowed(cp["url"])
        t0 = time.monotonic()
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except (PlaywrightTimeout, PlaywrightError) as exc:
            result["reason"] = f"goto-error: {str(exc).splitlines()[0][:200]}"
            return result
        status = resp.status if resp else None
        result["http_status"] = status
        await asyncio.sleep(csm.BASE_SETTLE_MS / 1000)
        readiness_ok = True
        if cp.get("readiness"):
            try:
                await page.wait_for_function(
                    cp["readiness"], timeout=cp.get("readiness_ms", 15000)
                )
            except PlaywrightTimeout:
                readiness_ok = False
            except PlaywrightError as exc:
                readiness_ok = False
                notes.append(f"readiness-eval-error: {str(exc).splitlines()[0][:120]}")
        challenged = False
        try:
            challenged = bool(await page.evaluate(csm.CHALLENGE_JS))
        except PlaywrightError:
            pass
        if challenged:
            # a challenge shell must never enter the variance sample set
            result["reason"] = "cloudflare-challenge"
            return result
        capture_anyway = attempt >= 2 or bool(cp.get("soft"))
        if not readiness_ok and not capture_anyway:
            result["reason"] = "readiness-timeout"
            return result
        if not readiness_ok:
            notes.append("readiness-timeout: captured after settle anyway")
        if status is not None and status >= 400 and not cp.get("any_status"):
            result["reason"] = f"http-{status}"
            return result

        # identical lazy-load sweep as the static matrix; ends scrolled to top
        sweep_steps = None
        for _ in range(2):
            try:
                sweep_steps = await page.evaluate(csm.SWEEP_JS)
                break
            except PlaywrightError:
                await asyncio.sleep(1.0)
        notes.append("sweep-failed" if sweep_steps is None else f"sweep_steps={sweep_steps}")

        try:
            await page.screenshot(path=str(frame_dir / "screenshot.png"), timeout=60000)
        except PlaywrightError as exc:
            result["reason"] = (
                f"viewport-screenshot-failed: {str(exc).splitlines()[0][:120]}"
            )
            return result
        try:
            await page.screenshot(
                path=str(frame_dir / "screenshot-full.png"),
                full_page=True,
                timeout=120000,
            )
        except PlaywrightError as exc:
            notes.append(f"fullpage-screenshot-error: {str(exc).splitlines()[0][:120]}")
            try:
                h = await page.evaluate(csm.SCROLL_HEIGHT_JS)
                clip_h = max(vp["height"], min(int(h), 16000))
                await page.screenshot(
                    path=str(frame_dir / "screenshot-full.png"),
                    clip={"x": 0, "y": 0, "width": vp["width"], "height": clip_h},
                    timeout=120000,
                )
                notes.append(f"fullpage-fallback-clip-height={clip_h}")
            except PlaywrightError as exc2:
                notes.append(
                    f"fullpage-fallback-failed: {str(exc2).splitlines()[0][:120]}"
                )

        meta = {
            "url": url,
            "final_url": page.url,
            "http_status": status,
            "ts_utc": csm.now_utc(),
            "viewport": {
                k: vp[k]
                for k in ("label", "width", "height", "device_scale_factor", "is_mobile")
            },
            "settle_ms": int((time.monotonic() - t0) * 1000),
            "attempt": attempt,
            "notes": notes,
        }
        (frame_dir / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
        result["ok"] = True
        return result
    finally:
        try:
            await context.close()
        except BaseException:
            pass


async def run_cell(browser, cp, vp, n_frames, out_root, manifest, manifest_path):
    key = f"{cp['id']}/{vp['label']}"
    cell = manifest["cells"].setdefault(key, {})
    cell.setdefault("frames", {})
    cell["url"] = cp["url"]
    prev_start = None
    for idx in range(1, n_frames + 1):
        if prev_start is not None:
            wait = FRAME_GAP_S - (time.monotonic() - prev_start)
            if wait > 0:
                await asyncio.sleep(wait)
        prev_start = time.monotonic()
        frame_dir = out_root / cp["id"] / vp["label"] / f"frame-{idx}"
        rec = None
        attempts = 0
        for attempt in (1, 2):  # max 2 attempts per failing frame
            attempts = attempt
            try:
                rec = await asyncio.wait_for(
                    capture_frame(browser, cp, vp, frame_dir, attempt),
                    timeout=ATTEMPT_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                rec = {
                    "ok": False,
                    "reason": f"attempt-timeout-{ATTEMPT_TIMEOUT_S}s",
                    "http_status": None,
                }
            except RuntimeError as exc:
                rec = {"ok": False, "reason": str(exc), "http_status": None}
                break
            except Exception as exc:
                rec = {
                    "ok": False,
                    "reason": f"unexpected: {type(exc).__name__}: {str(exc)[:200]}",
                    "http_status": None,
                }
            if rec["ok"]:
                break
            if attempt == 1:
                await asyncio.sleep(3.0)
        cell["frames"][f"frame-{idx}"] = {
            "status": "ok" if rec["ok"] else "failed",
            "attempts": attempts,
            "reason": rec.get("reason"),
            "http_status": rec.get("http_status"),
        }
        csm.flush_manifest(manifest, manifest_path)
        extra = f" reason={rec['reason']}" if rec.get("reason") else ""
        csm.log(
            f"[{'ok' if rec['ok'] else 'FAILED'}] {key} frame-{idx} "
            f"http={rec.get('http_status')} attempts={attempts}{extra}"
        )
    cell["status"] = (
        "ok"
        if all(f["status"] == "ok" for f in cell["frames"].values())
        else "incomplete"
    )
    csm.flush_manifest(manifest, manifest_path)


async def amain(args):
    out_root = Path(args.out).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    manifest_path = out_root / "capture-manifest.json"
    manifest = {"run": {}, "cells": {}}
    if manifest_path.exists():
        try:
            prev = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(prev.get("cells"), dict):
                manifest["cells"] = prev["cells"]
        except json.JSONDecodeError:
            pass

    table = checkpoints_by_id()
    wanted = list(CALIBRATION_CHECKPOINT_IDS)
    if args.only:
        sel = [w.strip() for w in args.only.split(",") if w.strip()]
        unknown = [w for w in sel if w not in CALIBRATION_CHECKPOINT_IDS]
        if unknown:
            raise SystemExit(
                f"unknown checkpoint ids {unknown}; valid: {CALIBRATION_CHECKPOINT_IDS}"
            )
        wanted = sel
    checkpoints = [table[cid] for cid in wanted]
    viewports = csm.VIEWPORTS
    if args.viewports:
        labels = [w.strip() for w in args.viewports.split(",") if w.strip()]
        viewports = [vp for vp in csm.VIEWPORTS if vp["label"] in labels]
        if not viewports:
            raise SystemExit("no viewports selected")

    started = csm.now_utc()
    async with async_playwright() as p:
        # HEADED only (hard rule): headless chromium gets Cloudflare 403 on
        # /store/api/* and store pages render an error shell.
        browser = await p.chromium.launch(headless=False)
        manifest["run"] = {
            "purpose": "three-frame visual-stability calibration capture",
            "target": csm.BASE,
            "out_root": str(out_root),
            "started_utc": started,
            "browser_version": browser.version,
            "headless": False,
            "frames_per_cell": args.frames,
            "frame_gap_s": FRAME_GAP_S,
            "workers": WORKERS,
            "viewports": [vp["label"] for vp in viewports],
            "checkpoints": wanted,
            "base_settle_ms": csm.BASE_SETTLE_MS,
            "notes": [
                "fresh ephemeral browser context per frame; cookies/session state never persisted",
                "request/response headers never saved",
                "analytics/consent/captcha hosts route-blocked (same policy as the static matrix)",
                "read-only public GET page loads; robots-disallowed paths refused",
            ],
        }
        csm.flush_manifest(manifest, manifest_path)

        q = asyncio.Queue()
        for vp in viewports:
            for cp in checkpoints:
                q.put_nowait((cp, vp))

        async def worker(idx):
            await asyncio.sleep(2.0 * idx)
            while True:
                try:
                    cp, vp = q.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    await run_cell(
                        browser, cp, vp, args.frames, out_root, manifest, manifest_path
                    )
                except Exception as exc:
                    key = f"{cp['id']}/{vp['label']}"
                    cell = manifest["cells"].setdefault(key, {"frames": {}})
                    cell["status"] = (
                        f"runner-crash: {type(exc).__name__}: {str(exc)[:200]}"
                    )
                    csm.flush_manifest(manifest, manifest_path)

        await asyncio.gather(*(worker(i) for i in range(WORKERS)))
        await browser.close()

    cells = manifest["cells"]
    ok = sum(1 for c in cells.values() if c.get("status") == "ok")
    manifest["run"]["finished_utc"] = csm.now_utc()
    manifest["run"]["cells_ok"] = ok
    manifest["run"]["cells_incomplete"] = len(cells) - ok
    csm.flush_manifest(manifest, manifest_path)
    csm.log(f"DONE cells ok={ok} incomplete={len(cells) - ok}")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--frames", type=int, default=3, help="frames per cell (default 3)")
    ap.add_argument("--only", default=None, help="comma-separated checkpoint ids")
    ap.add_argument("--viewports", default=None, help="comma-separated: desktop,mobile")
    args = ap.parse_args()
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()
