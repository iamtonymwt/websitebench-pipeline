# Rebuild order

These tools run in an order. This file exists from the start of the run rather
than after something broke, because on the previous site the order lived only in
scattered docstrings and two tools silently undid each other's work for a full
day before anyone wrote it down.

Every command runs from `materials/monoprice/`. Nothing here talks to the source
except step 1 and step 3.

## 0. The browser

    python3 tools/browser_session.py start     # idempotent
    python3 tools/browser_session.py warm      # earn the Cloudflare clearance
    python3 tools/browser_session.py status
    python3 tools/browser_session.py stop      # stops only the PID it started

**One browser for the whole run.** Everything else attaches to it over CDP.
Two reasons: this machine is shared and repeatedly launching headed windows is
rude, and — the load-bearing one — Cloudflare clearance is earned by the
*context*. Throw the browser away between tools and every tool pays the
challenge again.

**Headless does not work on this site and never will.** The preflight table in
`scope/channel-preflight.json` has the measurements: plain HTTP is answered 403
with a challenge shell, headless Chromium sits on `Just a moment...` forever,
headed Chromium clears silently. There is no fallback channel this run —
Browserbase credentials are not exported.

## 1. Capture

    python3 tools/capture_pages.py frontier --sitemap scope/sitemap-source.xml \
      --out scope/capture-queue.json --seed https://www.monoprice.com/
    python3 tools/capture_pages.py run --queue scope/capture-queue.json
    python3 tools/capture_pages.py status --queue scope/capture-queue.json
    python3 tools/capture_pages.py reclassify --queue scope/capture-queue.json

Writes `source-current/<date>.browser-fetch/<slug>/{dom.html.gz,fetch.json}`
and, for product pages, `extract.json`.

**Do not edit the queue while a capture is running.** The process holds the whole
queue in memory and writes it back after every batch, so your edit is gone at the
next save and nothing reports it. Stop it by PID first.

**`reclassify` is the cheap path.** The classification rule is the part of
capture most likely to be wrong first time; it re-reads captured bodies from disk
with no network and no browser.

## 2. Assets

    python3 tools/fetch_assets.py plan --capture-dir source-current \
      --out scope/asset-plan.json
    python3 tools/fetch_assets.py fetch --plan scope/asset-plan.json \
      --assets-dir source-assets --report scope/asset-fetch.json

Two transports, and the split is not optional: `images.monoprice.com` is open to
plain HTTP and carries every product photo; `www.monoprice.com/assets/` is behind
the same challenge as the HTML and must come through the browser (tab 1, so it
does not fight the capture loop on tab 0).

**A challenge shell is a successful-looking response.** It is a well-formed 5.7 KB
body with status 403, and saving it under the name of a stylesheet is how a site
loses its entire visual layer while every closure gate stays green. The fetcher
checks content, not just status.

## 3. Catalogue

    python3 tools/extract_catalogue.py --capture-dir source-current \
      --out data/catalogue.json --report scope/catalogue-extract.json

Products come from each page's own `schema.org` Product block. Category
membership comes from **both** the breadcrumb and the listing pages, and each
membership records which — because a listing page is the only place that
relationship is written down, and skipping one takes its category's entire
contents with it.

`image` is a JSON string containing a JSON array. It is decoded in exactly one
place, in this file. Do not add a second reader for it.

The report separates `memberships_dangling` (a listing links to a product we
never captured — our capture gap) from `categories_with_no_products` (the source
itself renders it empty — a source fact). Only the first is a defect.

## 4. Freeze

    python3 tools/build_frozen_pages.py --capture-dir source-current \
      --assets-dir source-assets --catalogue data/catalogue.json \
      --out-root clone/static/frozen --report scope/frozen-pages.json

Needs `--catalogue`: without it the freeze completes and the pages advertise
products that 404.

Reads `data/catalogue.json`, so **step 3 must have run against the current
capture.** Both are easy to skip and neither omission fails anything.

## Not yet written

Steps below this line are still to come; they are listed so the order is decided
before the tools exist rather than after.

5. `patch_served_scripts.py` — anything the page assembles at run time that a
   static rewrite cannot reach. **Must re-run after any step that copies assets
   over the served tree.**
6. Derived pages: page shell and product detail template, both cut from frozen
   pages, so both are stale until step 4 has run.
7. Gates: link closure, remote requests, **same-origin failures**, control
   surface, secret scan, `ruff`. The same-origin census is not optional here:
   Google Analytics is proxied through the first-party path `/securemetrics/`,
   so a remote-request audit is structurally blind to it.
8. Harbor.

## The two traps this site has that the gates cannot see

**Status code carries no signal.** An absent product answers **200** with the
title `Products no longer Available` and a fixed 380,458-byte body. An unknown
category path answers **200** with a 516 KB page whose title is built from the
slug. Only an unknown root path answers a real 404. Everything classifies by
content.

**The search type-ahead is a client-side Unbxd call on every keystroke.** No
page-load audit can see it, because it only fires when someone types. The clone
answers it locally; the Harbor case generator must reject any candidate that
leaves loopback, which is how the identical defect was caught on the last site.
