"""One long-lived browser for the whole monoprice run.

Every other tool here attaches to this one browser over CDP instead of launching
its own. Two reasons, and the second is the load-bearing one:

1. This machine is shared with other sessions and a human operator. Repeatedly
   launching and killing headed Chromium windows steals focus and is rude.
2. www.monoprice.com is behind a Cloudflare *managed* challenge. A fresh context
   navigates fine, but its first in-page fetch() burst comes back challenged --
   clearance is earned by the context over its first page load and then reused.
   Throwing the browser away between tools throws that away too, and every tool
   pays the challenge again.

The profile directory lives outside the repository and holds only live session
state. Nothing from it is ever copied into evidence, artifacts or logs.

    python3 tools/browser_session.py start     # idempotent
    python3 tools/browser_session.py status
    python3 tools/browser_session.py stop      # stops only the PID it started

Other tools:

    from browser_session import attach
    with attach() as (browser, context, page):
        ...
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import pathlib
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

# A port of this run's own. Never scan for or kill anything else on this box:
# other sessions are working here at the same time.
PORT = int(os.environ.get("MONOPRICE_CDP_PORT", "9411"))
STATE_DIR = pathlib.Path(
    os.environ.get(
        "MONOPRICE_BROWSER_STATE",
        pathlib.Path.home() / ".cache" / "websitebench-monoprice-browser",
    )
)
PID_FILE = STATE_DIR / "browser.pid"
PROFILE_DIR = STATE_DIR / "profile"
CDP = f"http://127.0.0.1:{PORT}"

HOME = "https://www.monoprice.com/"


def _endpoint_alive() -> dict | None:
    try:
        with urllib.request.urlopen(f"{CDP}/json/version", timeout=3) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


def _port_taken() -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def _chromium_path() -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        return pw.chromium.executable_path


def start() -> dict:
    alive = _endpoint_alive()
    if alive:
        return {"action": "reused", "cdp": CDP, "browser": alive.get("Browser"),
                "pid": int(PID_FILE.read_text()) if PID_FILE.exists() else None}
    if _port_taken():
        raise SystemExit(
            f"port {PORT} is held by something that is not answering CDP. "
            "It may belong to another session on this machine -- pick a different "
            "MONOPRICE_CDP_PORT rather than killing it.")

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [
            _chromium_path(),
            f"--remote-debugging-port={PORT}",
            f"--user-data-dir={PROFILE_DIR}",
            # Offscreen. A headed window is required (headless is challenged and
            # never clears), but it must not cover the operator's screen.
            "--window-position=-2400,-2400",
            "--window-size=1440,900",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=Translate,MediaRouter",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    PID_FILE.write_text(str(proc.pid))
    for _ in range(60):
        info = _endpoint_alive()
        if info:
            return {"action": "started", "cdp": CDP, "pid": proc.pid,
                    "browser": info.get("Browser")}
        time.sleep(0.5)
    raise SystemExit("browser did not expose a CDP endpoint within 30s")


def stop() -> dict:
    """Stop only the process this tool started, by its recorded PID."""
    if not PID_FILE.exists():
        return {"action": "nothing-to-stop", "reason": "no pid file"}
    pid = int(PID_FILE.read_text().strip())
    try:
        os.kill(pid, 15)
    except ProcessLookupError:
        PID_FILE.unlink(missing_ok=True)
        return {"action": "already-gone", "pid": pid}
    for _ in range(20):
        time.sleep(0.25)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
    PID_FILE.unlink(missing_ok=True)
    return {"action": "stopped", "pid": pid}


def status() -> dict:
    info = _endpoint_alive()
    return {
        "cdp": CDP,
        "alive": bool(info),
        "browser": (info or {}).get("Browser"),
        "pid": int(PID_FILE.read_text().strip()) if PID_FILE.exists() else None,
        "profile": str(PROFILE_DIR),
    }


@contextlib.contextmanager
def attach(warm: bool = True, page_index: int = 0):
    """Attach to the running browser and yield (browser, context, page).

    `warm=True` makes sure the context has been through a real monoprice page
    load, which is what earns the Cloudflare clearance that in-page fetch()
    needs. It is a no-op once the page is already on the site.
    """
    from playwright.sync_api import sync_playwright

    start()
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(CDP)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        pages = [p for p in context.pages if not p.is_closed()]
        while len(pages) <= page_index:
            pages.append(context.new_page())
        page = pages[page_index]
        if warm and "monoprice.com" not in (page.url or ""):
            page.goto(HOME, wait_until="domcontentloaded", timeout=90_000)
            _settle_until_cleared(page)
        try:
            yield browser, context, page
        finally:
            # Deliberately not closing: the browser outlives every tool.
            with contextlib.suppress(Exception):
                browser.close()  # detaches the CDP client only


def _settle_until_cleared(page, tries: int = 30) -> bool:
    """Wait until the context can actually fetch same-origin HTML."""
    for _ in range(tries):
        try:
            ok = page.evaluate(
                """async () => {
                    const r = await fetch('/robots.txt', {cache: 'no-store'});
                    const t = await r.text();
                    return r.status === 200 && !t.includes('Just a moment');
                }"""
            )
        except Exception:  # noqa: BLE001 - navigation in flight
            ok = False
        if ok:
            return True
        page.wait_for_timeout(1_000)
    return False


def warm() -> dict:
    """Bring the single browser to a state where bulk fetching works."""
    with attach(warm=True) as (_browser, context, page):
        cleared = _settle_until_cleared(page)
        names = sorted(
            c["name"] for c in context.cookies("https://www.monoprice.com")
        )
        # Cookie *names* only. Values are never read, printed or persisted.
        return {"cleared": cleared, "url": page.url, "cookie_names": names}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["start", "stop", "status", "warm"])
    args = ap.parse_args()
    print(json.dumps({"start": start, "stop": stop, "status": status,
                      "warm": warm}[args.command](), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
