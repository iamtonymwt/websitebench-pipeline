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

## 5. Patch served assets

    python3 tools/patch_served_assets.py --assets-dir source-assets \
      --report scope/served-asset-patch.json

Rewrites absolute references that live *inside* served CSS and JS. **Must re-run
after any step that copies assets over the served tree**, or the tree holds a mix
of patched and unpatched files and nothing says so.

This step is why step 4 strips Subresource Integrity: rewriting a file's bytes
invalidates the `integrity` hash the page declares for it, and a browser silently
discards a stylesheet whose hash does not match. See the trap section below.

## 5b. Content-fill fragments

    python3 tools/capture_fragments.py probe                      # look first
    python3 tools/capture_fragments.py run --catalogue data/catalogue.json \
      --report scope/fragments.json
    python3 tools/build_frozen_fragments.py --fragments scope/fragments.json \
      --assets-dir source-assets --catalogue data/catalogue.json \
      --out-root clone/static/fragments --report scope/frozen-fragments.json

Six first-party endpoints fill visible content *after* load, and the filler in
`mp_homepage.js` / `mp_productPage_more.js` hides the container **before** the
request and reveals it only on success. So an endpoint that does not answer does
not degrade the page — it deletes a section of it permanently.

The clone answered none of them. `/home/*` returned 404; the three `/product/*`
ones were swallowed by the catch-all, which saw `p_id` and returned the entire
407 KB product page for injection into a carousel. The source shows 35 product
tiles on a product page and the clone showed 1; the source renders 9,264
characters of home page and the clone rendered 3,678.

`probe` before `run`: it measures which endpoints vary per product. Only
`GetCustomersAlsoShoppedFor` does. Fetching all three per product would have
meant 11,577 requests to the source for 3,859 distinct answers and two
constants.

Fragments must be localised (step 5b's second command) before being served.
They are injected at run time, so a fragment full of `images.monoprice.com`
URLs puts remote requests back into pages that currently make none — and the
remote-request audit, which measures page load, would keep reporting 0.

## 5c. The variant map

    python3 tools/build_variant_map.py --frozen-root clone/static/frozen \
      --catalogue data/catalogue.json --out clone/static/variant-map.json \
      --report scope/variant-map.json

Product pages carry a `Length:` / `Color:` chooser whose options hold **no
product id** — the source resolves the combination server-side, at
`/product/selectpid`. So the map is derived offline: the clicked value replaces
the currently selected value in the product's name, and the result must match a
catalogue product name **exactly**. 3,807 of 4,720 selectable options resolve
that way (80.7%); the other 913 are listed in the report and deliberately left
out of the map.

Unresolved options return the *current* product unchanged. Guessing a
neighbouring product would be worse than doing nothing, because a wrong product
under the right variant label looks correct.

Reads frozen pages, so it comes after step 4. Only the 600 products with a
frozen body have a chooser at all — the detail template carries none, so the
3,257 template-rendered products show no variant control, which matches their
donor.

## 6. Derived pages — RE-RUN THESE AFTER EVERY FREEZER CHANGE

    python3 tools/extract_page_shell.py --page clone/static/frozen/about-us.html.gz \
      --out clone/static/page-shell.html --report scope/page-shell.json
    python3 tools/extract_detail_template.py --frozen-root clone/static/frozen \
      --catalogue data/catalogue.json --out clone/static/detail-template.html \
      --report scope/detail-template.json
    python3 tools/extract_search_template.py --frozen-root clone/static/frozen \
      --catalogue data/catalogue.json --out clone/static/search-template.json \
      --report scope/search-template.json

**There are three of them, and the third is easy to miss.** The search template
is `search-template.json`, not `.html`; a check written for `*.html` reports two
clean artifacts and never looks at it. That is exactly what happened — the shell
and the detail template were re-cut, search was not, and the search page kept
hiding all 316 of its results.

All three are **cut out of frozen pages**, so all three carry whatever the
freezer was doing on the day they were cut. Editing `build_frozen_pages.py` and
re-freezing does not update them, and **no gate in step 7 detects the
mismatch** — they are first-party local files, so link closure, remote requests,
the same-origin census and the test suite all pass on artifacts that are weeks
of fixes behind.

This is not hypothetical. The freezer was fixed to stop rewriting `type="text/css"`
into `type="/text/css"`; the frozen pages were correct afterwards and the shell
was not re-cut. Every page rendered from the shell — cart and checkout — kept
serving a `<link>` the browser refuses to apply, and lost six stylesheets
including `js_megamenu.css` and `mp-global.css`. The header rendered 19,844px
tall with the megamenu fully expanded. Nothing failed. It was found by a person
opening the page.

If you change the freezer, re-run this step. Treat it as part of step 4.

## 7. Gates

    python3 tools/audit_runtime.py --port <port> --report scope/runtime-audit.json
    python3 tools/audit_visible.py --port <port> --report scope/visible-audit.json
    python3 -m pytest clone/tests -q
    ruff check tools clone

`audit_visible.py` is the one that answers "does this look right", and it is the
only gate here that compares against the source page rather than against a
threshold written by hand. It measures page height, visible text length, visible
product-tile count, CSS rules in force, stylesheets that never applied, and
images that are broken *and* visible — then flags each family by its ratio to
the source. Run it after any change to the freezer, the shell, or the app's
rendering.

Link closure, remote requests, **same-origin failures**, control surface, secret
scan, `ruff`. The same-origin census is not optional here: Google Analytics is
proxied through the first-party path `/securemetrics/`, so a remote-request audit
is structurally blind to it.

**These gates measure references, not rendering.** All of them passed on a
category page that carried 165 product links and displayed none of them. If you
change anything in the freezer or the shell, look at a page from each family with
your eyes, and measure *visible* content — see the third trap below.

## 8. Harbor

    python3 tools/build_harbor_cases.py candidates ...
    python3 tools/build_harbor_cases.py prove ...

Case actions are proven against the running clone, so **every proven case is
invalidated by a behaviour fix.** Re-prove after step 6.

## The traps this site has that the gates cannot see

**Status code carries no signal.** An absent product answers **200** with the
title `Products no longer Available` and a fixed 380,458-byte body. An unknown
category path answers **200** with a 516 KB page whose title is built from the
slug. Only an unknown root path answers a real 404. Everything classifies by
content.

**The search type-ahead is a client-side Unbxd call on every keystroke.** No
page-load audit can see it, because it only fires when someone types. The clone
answers it locally; the Harbor case generator must reject any candidate that
leaves loopback, which is how the identical defect was caught on the last site.

**Third-party scripts own the visibility of first-party markup.** HawkSearch
serves every listing with *both* result containers hidden and lets its hosted
script reveal the right one:

    <div style="padding-top: 15px; display: none;" id="existresult">   results
    <div style="... display: none; ..."            id="noresult">      empty state

That script is third-party and stripped, so neither was ever revealed. A category
page held 165 product links and showed none; a search page held 316 and showed
none. Markup complete, references closed, zero remote requests, zero same-origin
failures, 4,910 CSS rules in force — and a blank page. The freezer now makes that
decision from a fact the page itself carries (whether it has `p_id=` tiles).

The general form: **stripping a third party can leave first-party content
present but unreachable.** The same site already did this twice with globals —
`dataLayer` from GTM and `_satellite` from Adobe Launch, both called by the
site's own add-to-cart chain. Removing a script removes its side effects, and
some of those side effects were load-bearing.

**Subresource Integrity outlives the bytes it describes.** Webflow pages declare
`integrity="sha384-..."` on their stylesheets. Step 5 rewrites URLs inside those
files, so the hash stops matching and the browser drops the sheet — status 200,
no request to anywhere, no console error the audit was watching for. The Webflow
page rendered with 1,079 CSS rules against 4,910 on its siblings. Step 4 strips
the attribute rather than recomputing it: a hash recomputed over our own rewrite
asserts nothing.

**Measure visible content, not present content.** Every check written during this
run answered "is it there?" and the four defects a person found were all "it is
there and you cannot see it". The probe that actually finds this class asks the
browser for: page height, `innerText` length, count of product links *whose
bounding box is non-zero*, `document.styleSheets` rule totals per family, and
count of images that are broken *and* visible. Compare those numbers **across
page families** — a single page's numbers look plausible in isolation, and it was
only cart's 2,418 rules next to product's 5,684 that showed anything was wrong.

**When patching a tool with a script, use raw strings.** A patch applied through
a normal Python string turned the `\b` in a new regex into a literal backspace
byte. The file looked right in an editor, `ruff` passed, the pattern compiled —
and it matched nothing, so the new fix silently did not run while reporting
success. Half the wasted time on this site came from checks that could not
distinguish "passed" from "never executed".

**Hidden-until-revealed is this site's signature failure.** Four separate
mechanisms in this codebase render content that is present and invisible, and
all four were introduced by removing a third party or by failing to answer a
request:

| what | who was supposed to reveal it | what it cost |
|---|---|---|
| `#existresult` / `#noresult` | HawkSearch's hosted script | category showed 0 of 165 tiles, search 0 of 316 |
| `#AlsoBought`, `#RecommandationsForYou`, `.home-layer3`, `.home-layer7` | the site's own AJAX, hidden before the call | product 1 tile vs 35; home 3,678 chars vs 9,264 |
| every stylesheet on cart/checkout | nothing — a damaged `type` attribute | 19,844px header, megamenu fully open |
| the Webflow main stylesheet | nothing — a stale SRI hash | 1,079 CSS rules against 4,910 |

When something looks empty on this site, the first question is not "did we
capture it" — it usually is captured. The question is "what was supposed to
turn it on".

## The first-party endpoint inventory

Every `url:` literal in the site's own served scripts, and what the clone does
with it. This list was worth building: six of the fifteen fill visible content
and all six were unanswered, and the only way to find them was to read the
scripts, because none of them is referenced statically in any page.

| endpoint | clone | note |
|---|---|---|
| `/home/getRecommendationsForYou` | captured fragment | fills `.home-layer3`, 12 tiles |
| `/home/getTopSellers` | captured fragment | 16 tiles |
| `/home/getRecentlyViewed` | empty, as the source | session history; empty on the source too |
| `/product/GetCustomersAlsoShoppedFor` | captured per product | the only per-product one |
| `/product/getrecommendationsforyou` | captured once | identical for every product |
| `/product/getrecentlyviewed` | empty, as the source | |
| `/product/selectpid` | variant map, 80.7% resolved | claim cl-019 |
| `/cart` | implemented | |
| `/MyAccount/GetContactList` | not reproduced | claim cl-020 |
| `/MyAccount/CreateUpdateContact` | not reproduced | claim cl-020 |
| `/QAS/ValidZipcodeByState` | not reproduced | claim cl-020 |
| `/Home/EmailSubcription` | not reproduced | claim cl-020 |
| `//player.vimeo.com/...`, `//vimeo.com/api/...`, `//$1/p/$2/media/` | third party | stripped |

To regenerate the list:

    grep -rhoE "url:\s*[\"'](/[^\"']{3,70})[\"']" \
      source-assets/www.monoprice.com/assets/js/*.js | sort -u

**Measure whether a control is broken before supplying one.** A facet-toggle
shim was written into the freezer on the strength of a user report ("the box on
the left does not work either") and it *broke a control that worked*. The search
page carries the site's own first-party inline handler:

    $(".hawk-groupHeading").on('click', function () {
      if ($(this).hasClass("plus")) { ... slideDown ... }
      else if ($(this).hasClass("minus")) { ... slideUp ... }
    });

It survives third-party stripping because it belongs to the site, not to
HawkSearch. jQuery binds to the element, so it runs before a delegated handler
on `document`: the shim then read `display` in the middle of the slideDown
animation, saw `block`, concluded the panel was open, and closed it again. One
click, two handlers, nothing moves.

The evidence that finally showed it was the inline style caught mid-animation —
`overflow: hidden; height: 3.84843px; padding-top: 0.15px; display: block` —
which is jQuery's slide, not a static state. Four probes before that one all
said "the handler ran and nothing happened", which is exactly what a fight
between two handlers looks like.

Every other shim in `build_frozen_pages.py` was verified broken first: the
result containers were `display:none` with no remaining script that referenced
them, and the stripped globals threw `ReferenceError` by name, on the clone and
not on the source. This one was assumed. The user's report was real, but its
cause was the results being hidden — there was nothing to filter, which reads as
a filter that does nothing.

`tools/verify_interactions.py` exists to answer this question first. Run it
before adding behaviour, not only after.

## The controls, and what drives each one

Three separate defects on this site were "a control that does nothing", and all
three were found by a person clicking, never by a gate. They do not share a
mechanism, so there is no single check for them — this is the list.

| control | how it works | where it is answered |
|---|---|---|
| search box | inline shim; Enter → `/search/index?keyword=` | `search_page` |
| facet group heading | the **site's own** inline jQuery `slideDown`/`slideUp` | nothing to do — do not shim it |
| facet value link | an ordinary `<a href>` carrying `*_uFilter=` | `selected_facets` + `matches_facets` |
| sort dropdown | `js_sort` → current path + the option's `data-url` | `sort_clause`, six modes |
| page size dropdown | same `js_sort`, `rows=25/50/75/100` | `page_size` |
| variant value | POST `/product/selectpid` | `clone/static/variant-map.json` |
| Add to Cart | `MPI.ee.addToCart` → POST `/Cart` | `/cart` + case bridge |
| checkout | form POST `/checkout` with a sandbox scenario | `commerce.py` |

`tools/verify_interactions.py` drives every row of this table in one browser
context. Run it after touching the app or the freezer. Testing the endpoint is
not testing the control: Add to Cart was dead for a day while 39 tests passed,
because every one of them POSTed to `/cart` directly.

**Two of the checks in that tool were themselves wrong before they were right.**
The facet-link check first asserted `filtered <= unfiltered`, which passed while
the handler ignored every facet parameter, because equality satisfies it. Then
it asserted `filtered < unfiltered`, which failed on a filter that worked
correctly — facets are applied *before* the page limit, so a filtered search
fills a full page exactly as an unfiltered one does. What is actually true is
that the set of products changes: 24 products, 16 of them new.

## Sort and page size

`/search/index` honours both, because it renders per request:

    sort=                                    Best Match (relevance)
    sort=title asc
    sort=sellingPrice asc | desc
    sort=rating_count desc,sort_rating desc
    sort=first_instock_date desc,sku desc    (no date in the catalogue; the
                                              sku half is reproduced, claim cl-024)
    rows=25 | 50 | 75 | 100                  default 24

The clause is chosen from a table keyed on the source's own strings, never built
from the parameter.

A **category** page is frozen source markup, so its order is fixed and a sort
selection does not reorder it. Before this pass such a URL answered 404
outright, because `js_sort` appends `menuDisStr`, `sort` and `TotalProducts` and
none of that matched the route map. The catch-all now retries the lookup without
those four parameters. See claim cl-024.
