"""Browser-channel preflight for monoprice.

The entry prompt requires this table before any capture harness is built around
one channel. www.monoprice.com sits behind a Cloudflare *managed* challenge that
answers plain HTTP clients with 403 for HTML **and** for /assets/, so the only
question that matters here is which channels come back with the real page rather
than the "Just a moment..." shell.

Each channel is asked four things:

1. can it create a session;
2. does it get the real page rather than a challenge shell, a 403 or a 5xx;
3. can it read rendered text (proving the font/render path works); and
4. can it drive input -- typed into the site's own search box, since that is the
   control every later capture depends on.

Item 4 is tested directly and never assumed.

Run:  python3 tools/preflight_channels.py --report scope/channel-preflight.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
from typing import Any

HOME = "https://www.monoprice.com/"
# The first version of this check looked for "challenge-platform" anywhere in the
# document and called the page a challenge shell when it found it. That is wrong,
# and wrong in the direction that matters: Cloudflare injects
# /cdn-cgi/challenge-platform/ scripts into *served* pages too, so a headed
# browser that had sailed through and was showing the real home page came back
# reported as blocked. The distinguishing fact is the title, which the shell
# replaces wholesale, plus the shell's own <title>Just a moment...</title>.
CHALLENGE_TITLE = "just a moment"
# A phrase only the real home page carries, taken from its <title>.
REAL_TITLE_MARKER = "home theater accessories"


def _verdict(page_html: str) -> str:
    import re

    m = re.search(r"<title[^>]*>(.*?)</title>", page_html, re.I | re.S)
    title = (m.group(1) if m else "").strip().lower()
    if CHALLENGE_TITLE in title:
        return "challenge-shell"
    if REAL_TITLE_MARKER in title:
        return "real-page"
    if not title:
        return "unknown"
    return "other-page"


def _probe_playwright(headless: bool) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    label = f"local-playwright-{'headless' if headless else 'headed'}"
    out: dict[str, Any] = {"channel": label, "session": False, "real_page": False,
                           "rendered_text": False, "interactive": False, "notes": []}
    started = time.time()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=headless,
                # Offscreen: this machine runs other sessions and a headed window
                # must not steal focus or cover the operator's screen.
                args=[] if headless else ["--window-position=-2400,-2400"],
            )
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                locale="en-US",
                timezone_id="America/Los_Angeles",
            )
            page = context.new_page()
            out["session"] = True

            page.goto(HOME, wait_until="domcontentloaded", timeout=60_000)
            # A managed challenge resolves itself; give it room before judging.
            for _ in range(20):
                html = page.content()
                if _verdict(html) == "real-page":
                    break
                page.wait_for_timeout(1_000)
            html = page.content()
            verdict = _verdict(html)
            out["verdict"] = verdict
            out["real_page"] = verdict == "real-page"
            out["title"] = (page.title() or "")[:90]

            if out["real_page"]:
                # 3: rendered text, not markup. inner_text is what Harbor reads.
                text = page.locator("body").inner_text()[:4000]
                out["rendered_text"] = "Monoprice" in text or len(text) > 500
                out["rendered_text_bytes"] = len(text)

                # 4: drive the site's own search input.
                try:
                    box = page.locator("#keyword").first
                    box.wait_for(state="visible", timeout=15_000)
                    box.click()
                    box.type("hdmi", delay=60)
                    out["interactive"] = box.input_value() == "hdmi"
                    out["typed_value"] = box.input_value()
                except Exception as exc:  # noqa: BLE001 - report, do not raise
                    out["notes"].append(f"input probe failed: {exc.__class__.__name__}: {exc}"[:200])

                # Bulk-fetch throughput, the number the capture plan depends on.
                t0 = time.time()
                got = page.evaluate(
                    """async () => {
                        const ids = [44627,47035,44565,44619,45390,49197,18601,47205];
                        const out = await Promise.all(ids.map(async id => {
                            const r = await fetch('/product?p_id='+id);
                            const t = await r.text();
                            return {s: r.status, n: t.length,
                                    c: t.includes('Just a moment')};
                        }));
                        return out;
                    }"""
                )
                out["bulk_fetch"] = {
                    "pages": len(got),
                    "ok": sum(1 for g in got if g["s"] == 200),
                    "challenged": sum(1 for g in got if g["c"]),
                    "seconds": round(time.time() - t0, 2),
                }
            context.close()
            browser.close()
    except Exception as exc:  # noqa: BLE001 - a failed channel is a result
        out["notes"].append(f"{exc.__class__.__name__}: {exc}"[:300])
    out["elapsed_seconds"] = round(time.time() - started, 1)
    return out


def _probe_plain_http() -> dict[str, Any]:
    """Not a browser channel -- included to record *why* one is required."""
    import urllib.error
    import urllib.request

    out: dict[str, Any] = {"channel": "plain-http-urllib", "session": True,
                           "real_page": False, "rendered_text": False,
                           "interactive": False, "notes": []}
    req = urllib.request.Request(HOME, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8", "replace")
        out["verdict"] = _verdict(body)
        out["status"] = 200
    except urllib.error.HTTPError as exc:
        out["status"] = exc.code
        out["verdict"] = _verdict(exc.read().decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001
        out["notes"].append(f"{exc.__class__.__name__}: {exc}"[:200])
    out["real_page"] = out.get("verdict") == "real-page"
    return out


def _probe_browserbase() -> dict[str, Any]:
    import os

    have = bool(os.environ.get("BROWSERBASE_API_KEY")) and bool(
        os.environ.get("BROWSERBASE_PROJECT_ID"))
    return {
        "channel": "browserbase",
        "session": False,
        "real_page": False,
        "rendered_text": False,
        "interactive": False,
        "verdict": "not-attempted",
        "notes": ["BROWSERBASE_API_KEY / BROWSERBASE_PROJECT_ID are not exported "
                  "in this environment; the channel cannot be created."]
        if not have else ["credentials present but probe not implemented here"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--headed", action="store_true",
                    help="also probe a headed browser (slower; one window, offscreen)")
    args = ap.parse_args()

    rows = [_probe_plain_http(), _probe_browserbase(), _probe_playwright(headless=True)]
    if args.headed:
        rows.append(_probe_playwright(headless=False))

    working = [r for r in rows if r["real_page"] and r["interactive"]]
    report = {
        "schema_version": "monoprice.channel-preflight.v1",
        "target": HOME,
        "channels": rows,
        "selected": working[0]["channel"] if working else None,
        "selection_reason": (
            "only channel that returned the real page AND drove the site's own "
            "search input" if working else
            "no channel satisfied all four preflight items"),
    }
    path = pathlib.Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if working else 1


if __name__ == "__main__":
    sys.exit(main())
