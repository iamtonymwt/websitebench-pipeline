# Humble Bundle offline clone delivery report

Assignment `63` / site `humble-bundle` / category `gaming` / source `https://www.humblebundle.com/`.

This is an internal loopback-only technical delivery. The formal trace is preserved verbatim: `[671] Register an account on Humble Bundle, add a currently active game bundle to cart, set custom price to $15, and proceed to checkout Confirm the final review or confirmation view visibly reflects the requested choices and totals`. Every exercised identity in the clone uses `@example.test`, all keys are synthetic `SANDBOX-` values, and payment and mail are local simulations. No real payment, deployment or remote side effect was performed. Source evidence came from anonymous GET page loads plus one authorized authenticated handoff (`scope/handoff-findings.md`), whose only source-side mutations were the sanctioned cart and wishlist writes; nothing was submitted and no account data enters a tracked file.

## Formal task source

- Main task and expanded inventory `WB063-T01..T23`: supplied verbatim by the human in-session; the task-671 text above is the bound `human_trace_text` (`ht-001`).
- Repository scope and implementation contracts: `scope/`, `clone.yaml`, `backend/runtime.json`, `clone/tests/`, and the same-id Harbor site/instance.
- Evidence grades for every claim: `scope/claims.jsonl` (74 claims — 67 directly-observed, 6 unavailable, 1 inferred).

## Frozen business oracles

| Fact | Value |
|---|---|
| Anchor bundle | `/games/yes-chef-cooking-bundle`, three cumulative tiers CA$9.71 (7 items) / CA$18.03 (13) / CA$22.19 (16), CA$288.53 value, FarmLink charity |
| Task-671 custom price | `$15` renders `You will get 7 items. You're missing out on Tavern Manager Simulator and 8 more! Pay at least CA$22.19 to get all items.` |
| Secondary bundle | `/games/2k-megahits-2026-bundle`, single fixed tier CA$21.16 / 15 items (≈US$14.97, the origin of the task's "$15") |
| Currency | CAD as captured (the source derives currency from request IP) |
| Catalog subset | 69 store products with captured ranks, all 13 active game bundles with full tier data, the 57-bundle listing |
| No-results / 404 copy | `0 Results` / `The page you requested cannot be found` |

## Expanded task coverage

| ID | Implemented clone behavior | Primary executable evidence |
|---|---|---|
| T01 | Public home at `/`, primary navigation with hover mega-menu panels, canonical local routes and destination headings | `test_smoke.py::test_all_frozen_routes`, ledger `entry-nav` |
| T02 | Register → open an active game bundle → custom price $15 → cart → checkout review showing bundle, price and charity split | `test_checkout.py::test_totals_reflect_custom_price`, ledger `core-671` |
| T03 | Bundles listing with Games/Books/Software category pages and store category routes | `test_smoke.py`, ledger `browse` |
| T04 | Keyword search refined by genre, platform and DRM facets over the captured result set | `test_catalog.py::test_portal_search_captured_order`, ledger `search` |
| T05 | Four sort modes (bestselling, discount, alphabetical, newest) and two-product comparison by price, platform and rating | `test_catalog.py::test_alphabetical_sort_differs_from_captured_order`, ledger `sort-compare` |
| T06 | Product detail with media gallery, description, system requirements, price, availability and rating | `test_catalog.py`, ledger `detail` |
| T07 | Tier and custom-price selection driving the unlocked item set, per-item lock badges and the charity split panel | `test_bundle_tiers.py::test_custom_15_unlocks_tier1`, ledger `tiers` |
| T08 | Wishlist save and removal bound to the signed-in account | wishlist tests, ledger `wishlist` |
| T09 | Account registration with a local-outbox verification code and immediate sign-in | `test_auth.py`, ledger `register` |
| T10 | Sign-in, signed-in header state and sign-out on a `__Host-` session cookie | `test_auth.py::test_session_cookie_attributes`, ledger `login-logout` |
| T11 | Cart drawer add, amount edit, remove and one-step undo restore under the observed 20-item cap | `test_cart.py::test_cart_size_cap`, ledger `cart` |
| T12 | Digital delivery choice: to the buyer's own library or gifted to an address, with address validation | `test_checkout.py::test_gift_delivery_stays_out_of_library`, ledger `delivery-gift` |
| T13 | Charity-split modes, local-sandbox payment scenarios (approved, declined, retryable) and the final review | `test_checkout.py::test_payment_key_guard`, ledger `checkout-promo-declined` |
| T14 | Library entitlements, revealable synthetic keys, purchase receipts and gift records | `test_checkout.py::test_keys_are_sandbox_shaped_and_reveal_is_idempotent`, ledger `library-keys` |
| T15 | Exact `zzzz-no-match-websitebench` search rendering the frozen `0 Results` state with a route back | `test_catalog.py::test_no_results_copy`, ledger `no-results` |
| T16 | Sign-in entry with email, password, identity-provider choices and a recovery route, returned without submitting | frozen `/login`, ledger `login-logout` |
| T17 | Registration entry with identity fields, terms links and verification guidance, returned without creating an account | frozen `/signup`, ledger `register` |
| T18 | In-page password recovery with reset-address field, guidance and return-to-sign-in, plus the full local reset | `test_auth.py`, ledger `password-recovery` |
| T19 | Seeded purchase history: newest item status, detail, per-order options and route back to the collection | `test_auth.py::test_seeded_demo_history_is_visible_after_login`, ledger `history-manage` |
| T20 | Inline required-field and invalid-input validation, plus the signed-out `/home/*` permission redirect | `test_auth.py::test_secure_area_redirect`, ledger `validation-permissions` |
| T21 | Public help center home, category and article pages reachable without exposing account data | frozen `/support*`, ledger `help` |
| T22 | Branded HTTP 404 preserving navigation with a safe route back | `test_smoke.py::test_unknown_route_is_branded_404`, ledger `not-found` |
| T23 | Browser-level end-to-end task 671 from the public entry, ending on a confirmation that shows the choices and total | ledger `core-671`, browser walkthrough recorded in the lifecycle log |

## Machine evidence

- Clone tests **76 passed**, 0 skipped. `websitebench-offline-clone verify --section static` = **clean**, 0 findings.
- Interaction ledger: `scope/interaction-ledger.json`, 55 proven entries covering all 23 journeys, regenerated deterministically.
- Harbor: same-id draft pair; `validate` = draft / scorable false / missing exactly 200 cases; the OpenCLI contract derived with 0 pending items, adapters in sync, and 23/23 derived assertions independently confirmed (official replay records the sanctioned `opencli-unavailable`).
- Visual: three-frame calibration over 24 cells (21 acceptance-eligible, 3 desktop cells source-limited by an entrance animation); `tools visual-diff` region classification is recorded for every cell that does not reach 0.99 similarity.
- `tools frontend-spec` reports **0 console errors and 0 failed requests** on the home, anchor-bundle, product and support pages.
- Deployment package prepared and dry-run clean; publication remains authorization-gated and was not performed.

## Known differences

Documented in `scope/implement-notes.md`: CAD pricing frozen as captured; third-party SSO buttons render but no identity provider is reachable offline; captcha, fraud, analytics and consent vendors are stripped; external preview videos are not localized (their poster frames render and the `<source>` elements are dropped so nothing 404s); the help center is frozen as three representative pages; books and software bundle detail pages return the branded 404, matching how the source treats an expired bundle; and the product catalog is the authorized subset.

## Broken-link and deferred-image repair (2026-08-27)

A crawl of the served clone found 24 of its 119 internal links answering 4xx and
26 of the home page's 56 images never loading. Measured before and after:

| | before | after |
|---|---|---|
| internal links 4xx | 24 | 0 |
| 4xx links on the home page | 10 | 0 |
| images with no bytes, 21 routes | 196 | 0 |
| remote hosts reached at runtime | 0 | 0 |
| clone tests | 76 | 76 |

Five causes, each different:

**Deferred images never loaded.** Tiles are captured as
`<img class="js-lazyload" data-src="…" src="">` and the source's loader is not
part of this clone, so nothing moved `data-src` into `src`. The bytes were local
and serving 200 the whole time. `hb-app.js` now reveals them and watches for the
carousel's inserted slides, which is why scrolling left used to make it worse.

**The takeover buttons did nothing.** "Get the bundle" is a `<button>`, not a
link, and the source binds it in script. The home page carries two takeovers —
Humble Choice and the 2K bundle — and each one's destination is the
`aria-hidden` background anchor inside its own block. Both now navigate where
their own markup points.

**Nine promo paths could not be routed.** `/store/promo/<name>/` has two path
segments and `/store/{slug}` matches one. `books` and `software` redirect to the
listings the site already serves under those names, and are exact. The other
seven are curated selections the capture never visited; the catalogue supports
genre, platform, DRM, sort and an onsale filter but no price bound, so
`deals-under-10` cannot be reproduced as a query. They redirect to the store
listing they are a view of, with `filter=onsale` where the promo name says
"deals". A substitution, recorded here rather than hidden.

**A trailing slash 404ed.** `/store/` matched no route while `/store` served the
listing, because the path convertor requires at least one character.

**`data-lazy` was never localized.** `build_frozen_pages.py` localizes `src`,
`srcset`, `poster`, `background`, `data-src`, `data-srcset` and `data-poster`,
and lists `data-lazy-src` as inert — but plain `data-lazy` appeared in neither
list. The carousel library that would have promoted it is stripped from this
clone, so 34 images across the store listing, the membership page and a bundle
page rendered blank while still pointing at the source's image CDN: a
localization gap that looked like a rendering one. The builder's attribute list
now includes it, and `tools/localize_data_lazy.py` closed the already-frozen
references — 34 of 34 fetched, content-addressed and recorded in
`assets-provenance.json`.

Promoting `data-lazy` had to be done carefully. A first pass promoted every
value and took the site from 196 blank images to 67 — while opening requests to
`hb.imgix.net`, turning a blank image into the one thing an offline clone may
not do. The handler now promotes only references the clone holds; the
localization above is what actually closed the rest.

Four products the home page featured — ReStory, ACE COMBAT 8, IRON NEST and
Tomodachi Life — were linked and 404ing. Their title, price and cover image were
in the capture; they are added with those three fields and nothing else, and
each carries a `capture_note` saying the detail page was never visited.

### What the first pass got wrong

The first pass closed 14 of the 24 broken links and reported the other ten as
"no evidence exists". Two of those three claims were wrong, and both were wrong
the same way: the evidence was in the seed, in a table the search had not
opened.

**Six book bundles.** `/books/{slug}` 404ed unconditionally, on the reasoning
that book bundle detail was outside the frozen subset. True of `hb_bundles`,
which holds the thirteen captured game bundles — and wrong about the seed, which
carries nineteen book bundles in `bundles_listing` with their names, end dates,
highlight lines and tile images. They now serve their own pages.

That fix needed two more repairs to be honest. The client-side dispatcher routed
only `/games/{slug}` to the bundle page, so a book bundle first rendered the
frozen template untouched — showing the captured Yes Chef bundle's name, blurb
and tiers under an O'Reilly bundle's URL, which is worse than the 404 it
replaced. And a bundle known only from a tile has no tiers or prices, so the
purchase machinery is removed rather than left showing another bundle's.

**RimWorld and Slay the Spire.** Reported as having "no price anywhere in the
evidence" after searching `products`, `bundles`, `bundles_listing`,
`search_meta` and `suggest_orders`. The top-sellers strip on the captured
product page carries both at full price, discounted price, discount percentage,
Steam delivery, three operating systems and a cover image. They are in the
catalogue now, from those fields, and their footer links resolve.

A third correction, smaller: they were first written as Windows-only, which was
a guess. The tile lists Windows, macOS and Linux outright.

### Still not delivered

`/developer` and `/partner` are linked from every page's footer and are not
among the twenty-two captured pages. There is nothing to serve and nothing to
recover them from, so the two links are removed from the frozen footers by
`tools/drop_unheld_footer_links.py`. A link to something an offline clone does
not hold is not a feature of the clone.


## Not delivered

An authenticated handoff (2026-08-22) resolved the checkout, gift, account-route
and summary-math structures that the anonymous build had to infer; see
`scope/handoff-findings.md`. Two gaps remain and are recorded as `unavailable`
in `scope/claims.jsonl`: the **populated** library and purchase-history layouts,
which need a completed purchase and therefore a real payment, outside the
authorized scope (their empty states are now directly observed), and
registration's submit-time semantics, which stay out of evidence because the
credential segment is excluded by design. No machine-recorded source-side
trajectory exists — the walk was complete before the recorder would have
attached — so the interaction ledger is clone-side only and declares that.
`verify --section live` needs the Linux candidate sandbox and runs in CI. The
200-case scorable benchmark is a separate authoring task.
