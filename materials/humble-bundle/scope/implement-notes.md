# Implementation contract (durable working notes) — humble-bundle

Frozen-snapshot + interaction-JS clone: captured post-render pages served at
their real routes with scripts stripped; dynamic behavior re-implemented in
`static/site/hb-app.js` against a local JSON API backed by the vendored
`websitebench.site_backend` seam. Machine authority = sibling scope JSONs.

STATUS: skeleton — sections fill as phases complete (anonymous side done;
auth/cart/checkout interiors pending handoff walk tr-001).

## File layout (owners)

- `clone/app.py` — composition root: frozen-page routing, JSON API, cookies,
  admin reset. No business logic.
- `clone/backend/catalog_db.py` — business schema + semantics on the seam
  (catalog/bundles/tiers/cart/checkout/purchases/keys/wishlist/auth).
- `clone/backend/seed_data.json` — deterministic seed (69 products, 2 full
  bundles, 57-bundle listing, demo account, seeded purchases; built by
  `tools/build_seed.py` from api-harvest).
- `clone/frontend/pages/*.html` — localized frozen snapshots (built by
  `tools/build_frozen_pages.py`; zero remote runtime refs).
- `clone/static/site/hb-app.js` — the interaction layer.
- `clone/static/assets/…` — content-addressed localized assets.
- `tools/capture_static_matrix.py` — reusable capture harness (headed; headless
  gets CF 403 on /store/api/*).

## Frozen business facts (captured 2026-08-20, CAD)

- Anchor bundle `/games/yes-chef-cooking-bundle`: value line "CA$288.53 Value •
  Pay What You Want"; tiers CA$9.71 (7 items) / 18.03 (13) / 22.19 (16);
  presets 9.71/18.03/22.19/30/35/40; floor headline "Pay CA$9.71 Or More";
  $15 state msg "You will get 7 items. You're missing out on Tavern Manager
  Simulator and 8 more! Pay at least CA$22.19 to get all items." + Checkout;
  charity FarmLink; split options Default Donation / Extra to Charity /
  Custom Amount (rows: Publishers / Farmlink / Humble).
- Secondary `/games/2k-megahits-2026-bundle`: single fixed tier CA$21.16,
  15 items, MSRP CA$645.03, charity Covenant House (task text "$15" ≈ its
  US$14.97 price — currency is frozen as captured CAD; known difference).
- Checkout review (walk tr-001, authenticated): anchor bundle at the custom
  price CA$15.00 -> Subtotal CA$15.00 / HST CA$1.85 / Total CA$16.85 /
  charity CA$0.75. Charity is the bundle's own `paypalgivingfund` split share
  (sibling_split 0.05); the tax line is 13% (captured region's HST) of the
  NON-charity remainder, (1500-75)*13% = 185.25 -> 185. A flat 13% of the
  subtotal would be 195, so the taxable base excludes the donation. Frozen in
  `catalog_db.TAX_RATE_BP` / `TAX_LABEL_BUNDLE` / `TAX_ORACLE`. Humble Choice
  upsell offer: 5% off first month, CA$17.09, renewal CA$17.99 (offer copy).
- **Store cart drawer (walk-671, authenticated, one store product).** Sub-Total
  CA$1.37 / Sales Tax CA$0.17 / Total CA$1.54, plus `Wallet Credit Earned`
  CA$0.14 and a Humble Choice coupon offer of CA$1.95. Two things this pins
  that the bundle oracle could not:
  1. **The tax line truncates.** 137 * 13% = 17.81, and the drawer shows 17
     with a self-consistent 137 + 17 = 154. Half-up would have shown 18. The
     bundle oracle (1425 * 13% = 185.25 -> 185) is satisfied by floor *and*
     half-up, so it never discriminated. `catalog_db._bp_of` therefore floors,
     and `TAX_ORACLE_STORE` pins the discriminating case.
  2. **The tax label is per flow, not global.** The store drawer says
     `Sales Tax:`, the bundle checkout Order Summary says `HST` — same rate,
     same rounding. `order_totals(..., flow=)` carries the captured label with
     the numbers (`TAX_FLOW_LABELS`), and `_cart_view` picks the flow from the
     cart's own lines, so neither surface hardcodes a label.
  The wallet-credit rate is the store API's own per-product `rewards_split`
  (0.1 for this product in the 2026-08-20 harvest; 0.1 for 117 of 139 entries,
  with 0.05 and 0.0 the only other values). 137 * 10% = 13.7 and the captured
  figure is 14 — the NEAREST cent, where the tax line truncates — so the
  rewards line has its own helper (`_bp_of_nearest`, `WALLET_CREDIT_ORACLE`).
  One observation cannot separate nearest from ceiling; nearest is used.
- Store search: page_size 20; sorts discount|alphabetical|newest|bestselling;
  filters onsale|new; genres rpg,indie,vr,simulation,strategy,adventure,
  action,racing; captured orders for search "portal" (29) and
  genre=adventure bestselling (40) are the default-sort oracles.
- No-results copy: exactly "0 Results". 404: HTTP 404, "THE PAGE YOU
  REQUESTED CANNOT BE FOUND …" with nav intact.
- Auth: /login (Email/Password/forgot-button/LOG IN/Google+Facebook SSO);
  /signup (Email/Password ≥8/newsletter checkbox/click-to-agree ToS incl.
  mandatory arbitration/Google SSO only); in-page Password Reset state
  ("We'll send a password setup link to your account's email address.",
  RESET PASSWORD, Contact Support). No standalone recovery URL.
- Account area /home/*: anon → 302 /login?goto=<path>&qs=reason%3DsecureArea.
- Cart: client drawer, MAX_CART_SIZE 20, MAX_WISHLIST_SIZE 100; /cart is 404;
  checkout at /checkout (interior pending handoff).
- Search suggest: .site-search-results panel, rows "title | -NN% CA$x.xx".
- Support: Zendesk /hc/en-us localized under /support* (home + Key Redemption
  category 200166394 + one article frozen).

## Pending (fill after handoff tr-001)

- Registration submit semantics (verification step shape), signed-in header
  state, logout.
- Cart drawer DOM (empty/populated/removed), checkout surface (delivery/gift,
  promo/gift option, payment methods UI), review/confirmation copy.
- Library/purchases/keys interiors + wishlist surface/route.
- JSON API contract table + sandbox/demo surface (accounts, scenarios, reset
  token) — write when backend lands.


## JSON API contract (app.py <-> hb-app.js; backend functions in catalog_db.py)

- GET /api/search — search, genre, platform, drm, sort (bestselling|discount|alphabetical|newest), filter (onsale|new), page; returns {results, num_results, num_pages, page_size: 20}. Captured-order oracles: query "portal" and genre=adventure bestselling. "newest" is a documented deterministic fallback (inferred).
- GET /api/suggest?q= — top-5 title matches {human_name, slug, discount_pct, current_price_minor}.
- GET /api/product/{slug}; GET /api/bundles (per-category listing); GET /api/bundle/{slug}.
- GET /api/bundle/{slug}/preview?amount_minor= — tier engine: {valid, floor_minor, unlocked_tier_ids, unlocked_count, total_count, missing_count, missing_first_name, next_threshold_minor}. The frontend renders the captured line as nodes, not text, because the source wraps its middle clause in `<strong>`: `You will get 7 items. <strong>You're missing out</strong> on Tavern Manager Simulator and 8 more! Pay at least CA$22.19 to get all items.` `next_threshold_minor` is **always** the all-items threshold (the top tier), never the floor — CA$9.71 unlocks 7 of 16 items, so returning it as the price that "gets all items" was wrong. Below the floor the frontend switches the trailing clause to the source's own captured minimum-price sentence off `valid` + `floor_minor` (`… and 15 more! The minimum price for this bundle is CA$9.71.`), which is also what `.js-error-and-infotip` shows.
- Cart: GET /api/cart[?split_mode=default|extra-charity|custom]; POST /api/cart/add {kind: bundle|product, slug, amount_minor?}; /api/cart/update {item_id, amount_minor?|qty?}; /api/cart/remove {item_id} (returns restore snapshot); /api/cart/restore. MAX 20 items. The GET also returns the checkout review's Order Summary numbers — subtotal_minor, original_total_minor, charity_minor, charity_name, tax_flow, tax_label, tax_minor, grand_total_minor — plus the store drawer's rewards_credit_minor / rewards_label and choice_coupon_minor, so the drawer, the review, the order row and the confirmation all share one server-side computation. `tax_flow` is `store` (label `Sales Tax`) for a product-only cart and `bundle` (label `HST`) as soon as a bundle line is present; `original_total_minor` is the undiscounted sub-total behind the drawer's struck-through original. Product lines additionally carry machine_name, unit_full_price_minor, line_full_total_minor, platforms and drm, which are what the captured drawer row renders. `qty` stays in the update contract and in the line payload, but no surface presents a quantity control — see the known-difference list.
- Checkout: POST /api/checkout {scenario_id: sandbox-approved|declined|retry, processor: paypal|card|alipay, gift {mode: none|email|link, recipient?, anonymous?}, leaderboard_name?, splits {mode, allocations?}} (legacy flat form delivery_kind: self|gift + gift_email still accepted); payment-shaped keys rejected (PAYMENT_KEY_RE). Rejections: 422 unknown_processor, 422 gift_email_invalid, 422 below_floor, 422 split_invalid, 400 empty_cart, 400 payment_field_rejected, 402 declined|retryable. `processor` is a label only — the opaque sandbox scenario id stays the sole payment input.
- Account: POST /api/account/login|logout, /api/account/register/start|complete, /api/account/password-reset/start|complete; GET /api/account (adds `delivery_email` for a signed-in session: the settings override if the account edited it, otherwise the sign-in address).
- Settings (/user/settings, /user/wallet): GET /api/account/settings — {sign_in_email, delivery_email, delivery_email_is_override, subscriptions, subscription_fields[{name,label}], charity_preference, community_donated_display, wallet{currency,funds_minor,expiring_minor}}; POST /api/account/delivery-email {email} (400 invalid_email on a malformed address); POST /api/account/contact-prefs {subscriptions?, charity_preference?} (400 invalid_preferences on an unknown subscription name). Preferences live in `hb_account_prefs`, keyed by the business owner key, and `POST /__admin/reset` restores the captured defaults.
- Library: GET /api/library, /api/purchases, /api/purchase/{order_no}; POST /api/purchase/{order_no}/reveal-key {machine_name}. Library entries and purchase keys carry `created_at`, `platforms`, `drm` and `delivery_methods` — what the captured library Platform select, its Recently-updated sort and the keys table's `Type` column need. A bundle entitlement is named by the bundle's own item machine name, which the store catalog does not carry, so its platform lists stay empty rather than guessed.
- Wishlist: GET /api/wishlist; POST /api/wishlist/add|remove {slug}. Rows carry `machine_name`, `platforms`, `drm` and `media` as well as the price pair, because the captured wishlist row is a full store entity, not a name and a price.
- Infra: GET /healthz {"ok":true,"site_id":"humble-bundle"}; POST /__admin/reset (X-WebsiteBench-Admin-Token, env WEBSITEBENCH_HUMBLE_BUNDLE_ADMIN_TOKEN).

## Known-difference policy (running list)

- **Bundle purchase is routed through the clone's own cart.** The source keeps
  the two flows separate: a bundle goes straight from its page to the review and
  the store drawer stays empty. This clone puts the bundle line in the same cart
  so a single checkout implementation serves both flows, which is also what
  makes the drawer's amount edit available as the answer to the task
  inventory's change-quantity clause. Recorded as
  `claim.difference.bundle-routed-through-cart`; the source-side claim
  `claim.structural.bundle-checkout-is-separate` stands unchanged.

- Currency frozen as captured CAD (geo-derived); source varies by IP.
- SSO buttons render but external IdP flows are offline-impossible → truthful
  local message; recorded difference.
- reCAPTCHA/Sift/analytics/consent stacks stripped; clone validates locally.
- Bundle countdown timers tick from frozen end timestamps (source-relative).
- Catalog is the authorized subset; content not claimed to match live site
  day-to-day.
- Bundle item hover/preview videos (steamstatic) intentionally not localized;
  posters render, playback inert offline.
- Support (Zendesk) frozen as three representative pages (home, Key Redemption
  category, one article) under local /support*; other categories/articles are
  out of the frozen subset.
- bundles/games/store-search DESKTOP visual cells are reference-evidence-only
  (source entrance animation instability); their mobile cells carry the
  thresholds.
- **Cart quantity has no source surface.** The captured drawer has no quantity
  control, no quantity text and no quantity field (every `qty`/`quantity` hit
  in `source-auth-scratch/walk-671/cart-drawer-populated/dom.html` is inside
  the analytics bundle; zero `input[type=number]`), and a store product is a
  single license. The clone therefore presents none: the invented `Qty 1`
  line is gone from the drawer row. `POST /api/cart/update {item_id, qty}`
  remains in the API contract (line totals stay `unit_price_minor * qty`) so
  the seam keeps a per-line multiplier, but it is not exposed as a control.
  T11's "change quantity" clause is satisfied instead by the amount edit on a
  bundle line — the source's real per-line editable amount — and NOT by an
  invented quantity stepper.
- **Remove/restore: the undo is clone-invented and deliberate.** The source's
  `div.cart-notifications.js-cart-notifications` is present but EMPTY in every
  capture (populated authenticated drawer and anonymous store drawer alike);
  the only removal affordance is the `✕` icon, which is one-way. The clone
  keeps a `Removed <name> — Undo` notification with a `js-hb-cart-undo`
  control backed by `/api/cart/remove` (returns a snapshot) and
  `/api/cart/restore`, because it is the only thing that makes T11's "restore"
  half completable offline. Disclosed addition, not source behaviour.
- **Store purchase controls reroute to the local `/checkout`.** In the source
  `Pay with Paypal` (`data-processor="paypal"`) and `Pay with card`
  (`data-processor="stripe_checkout"`) hand the store cart to an external
  processor, and `/checkout` is the *bundle* flow. Offline there is no
  processor, so both drawer controls navigate to the local review instead; the
  drawer's own `input#giftcheckbox.js-gift-box` is rendered as captured but is
  not carried across that navigation (the review has its own captured gift
  opt-in). Deliberate offline substitution.
- **Wallet-credit rate is applied uniformly.** The harvest carries a
  per-product `rewards_split` (0.1 / 0.05 / 0.0), but the seed does not, so
  the clone applies the modal 10% to every store line. The Humble Choice
  coupon offer is reproduced as the single captured value (CA$1.95,
  `CHOICE_COUPON_MINOR`); the copy's "Save even more by adding items!" implies
  the real amount scales with the cart, and no second cart was captured, so no
  scaling rule is invented.
- **Drawer product price drifts from the newer authenticated capture.** The
  seed is generated from the 2026-08-20 harvest and gives
  `bridge-constructor-portal-portal-proficiency` CA$5.53 full / CA$1.38
  discounted; the 2026-08-22 authenticated drawer shows CA$5.48 / CA$1.37.
  Both are internally consistent at the same captured -75%, both floor to the
  same CA$0.17 tax line, and the difference is a two-day CAD price refresh —
  the same FX drift the catalog-subset policy above already covers, now named
  for the one product the drawer evidence pins. **The 08-20 harvest stays
  authoritative for the catalog**: `tools/build_seed.py` regenerates
  `clone/backend/seed_data.json` byte-identically from that tracked run, so
  hand-editing one product's price would silently desynchronize the seed from
  its own provenance (and leave a catalog mixing two snapshots) — the next
  rebuild would revert it unnoticed. The rounding oracles are pinned on the
  captured figures directly (`TAX_ORACLE_STORE` 137 -> 17 -> 154,
  `WALLET_CREDIT_ORACLE` 137 -> 14) so the rate math is verified against the
  capture regardless of which snapshot the seed carries.
- **Suggest rows are restricted to destinations the clone serves.** The
  captured `portal` panel's most prominent row is
  `/software/massive-unreal-engine-bundle-software`, a books/software bundle
  detail page that is out of subset and returns the branded 404 — on the exact
  row the source's own trajectory (tr-001) activated. The panel now serves only
  rows whose destination resolves (a seeded store product, or a seeded game
  bundle), on the captured path and the fallback path alike, so no suggest row
  anywhere dead-ends. The seed keeps the captured row as the evidence record;
  `_suggest_href_servable` in `catalog_db.py` is the single rule. Alternative
  considered and rejected: serving books/software bundle detail would mean
  inventing an entire bundle page with no capture behind it, which is a worse
  fidelity loss than one fewer suggest row.
- **Settings' Email Address edits a local delivery address, not the sign-in
  credential.** See `claim.difference.settings-delivery-email-is-local`; the
  page says so in place.
- **The captured Security section and the Payment Information action controls
  are omitted rather than rendered dead.** See
  `claim.difference.settings-security-section-omitted`.
- **Populated account interiors are labelled as seeded demo data.** See
  `claim.difference.seeded-account-interiors-labelled`.
- **Absolute image URLs embedded in seed description HTML are dropped on
  injection.** 38 of the 69 products carry 212 `src="https://…"` references
  inside their own description bodies; they were never localized, the clone's
  CSP blocks every remote origin, and injecting them verbatim produced a broken
  image plus a console error each. `setSeedHtml` parses seed HTML in an inert
  `<template>` and removes those nodes before the browser can fetch them —
  the same policy as the frozen pages' `dropped_missing_references`. Layout and
  text are unaffected; only the inline screenshots inside a description are
  absent.

## hb-app.js page modules

One IIFE, loaded with `defer` on every frozen page; modules bind by
location.pathname at init and feature-detect every selector (a missing hook
no-ops; module failures log one console warning). Shared helpers: qs/qsa/el,
`money` (CA$ + thousands commas + 2 decimals), `moneyTrim` (drops ".00" —
preset labels and split rows), `mediaUrl` (accepts plain URL strings or
`{local, source_url}` seed media objects), `api` fetch wrapper, debounce.

- header (all pages): `input.js-search` → /api/suggest → rows in
  `.js-search-holder`/`.js-results` using the captured
  `.product-search-result` markup family (title | -NN% | CA$x.xx); Enter →
  /store/search?search=; Escape/outside click closes.
  `a.js-account-login`/`a.js-create-account` → /login | /signup; when
  GET /api/account is authenticated both hide behind an injected account
  dropdown (display name → Library/Purchases/Keys/Wishlist/Log Out →
  POST logout + reload). Cart badge: store sub-nav `button.js-cart
  .js-item-count` opens the drawer; pages without it get a navbar cart icon
  injected only when count > 0 (anonymous frozen header has none;
  REFINE-AFTER-HANDOFF).
- cart drawer (all pages, REFINE-AFTER-HANDOFF): reuses the captured
  `#js-cart-container` modal on /store* pages (opens by showing
  `.js-grayout`), constructs an equivalent (same class names + inline
  styles) elsewhere; bundle rows edit amount via /api/cart/update, remove →
  one-step Undo banner in `.js-cart-notifications` (snapshot →
  /api/cart/restore), subtotal, Checkout → /checkout.
- bundle (/games/{slug}): wires `form.js-go-to-checkout` —
  `input.js-preset-price` radios + `input.js-custom-amount` (debounced) →
  /api/bundle/{slug}/preview → `.js-item-count-text` unlock-message oracles,
  Checkout disabled below floor, additive per-tile lock badges
  ("Pay at least CA$X to get this item"; frozen tiles carry no badge — all
  16 were unlocked at the captured $30), split rows in
  `.js-default-preset-splits`/`.js-extra-charity-preset-splits` and slider
  `.js-amount-container` amounts recomputed from the bundle's split
  fractions; `.js-splits-toggle`, `.js-split-allocation` (mode →
  sessionStorage for checkout), `.js-tier-filter`/`.js-tier-header`;
  countdown ticks `.js-days/hours/minutes` from end_at. Submit = cart_add
  {kind: bundle, amount_minor} → /checkout. The two frozen slugs keep their
  DOM at load; any other seeded slug hydrates title/logo/value line/preset
  radios/quick facts (floor headline, sold count)/tier chips/item grid/
  charity panel/split rows from /api/bundle + /api/bundles.
- search (/store/search, /store/c/{token}): state from query params (URL
  `page` is 1-based per frozen pagination hrefs). /store/search?search=portal
  with no genre/platform/drm/sort/filter/page params leaves the frozen grid
  untouched (controls still wired); otherwise renders `ul.js-entities-list`
  tiles in the frozen entity markup pattern, `.js-title-text` "N Results" /
  "0 Results" (+ additive clear-search route back), `.js-filter-dropdown`
  open handling, `a.js-option` (sort/filter), `input.js-filter-option`
  checkboxes (genre/platform/drm — API is single-valued per facet), and
  `.js-pagination` (page_size 20, num_pages).
- product (/store/{slug}): satisfactory wires buttons only (plus promoting its
  frozen thumbnails' `data-lazy` to `src`, which the stripped slick lazy
  loader never did); other slugs hydrate from /api/product — title/h1/capsule,
  prices + discount gem (hidden with the promo timer at 0% discount),
  description and system requirements through `setSeedHtml` (inert-template
  parse, remote refs dropped), developer/publisher/links, platform/DRM/OS
  icons, **the Steam user-rating summary and the Critical Reception block**
  (`bindUserRating` / `bindReviews` — see "Product detail: per-product rating
  and reviews"), and a main-image + click-to-swap-thumbnails gallery replacing
  the inert slick carousel. Add to Cart → cart_add + drawer; Checkout →
  cart_add + /checkout; wishlist button ↔ /api/wishlist add/remove (`saved`
  class), anonymous → /login?goto=. No frozen hook exists for product genres.
- checkout (/checkout; server gates anonymous): rebuilt from the
  authenticated capture (walk tr-001). Renders `.checkout-page
  js-checkout-page grid` into `.js-page-content` — two columns. Left, top to
  bottom: `You Might Also Like` Humble Choice upsell (`add-upsell`, unchecked;
  when checked it only previews a Choice line on the summary and never
  enrolls anything); `Delivery Information` (signed-in account email +
  `Not You?` / `js-sign-out-redirect` → POST logout + reload); `Payment
  Method` (three `name="processor-type"` radios Paypal / Credit Card /
  Alipay with trailing brand icons, the captured redirect notice, and a hint
  line stating the offline demo simulates the redirect locally); the
  `gifting-enabled` opt-in revealing the `gift-type` pair
  (gift-recipient-email — validated inline via `js-gift-email-input-error` —
  vs gift-recipient-link, which needs no recipient) plus the anonymous-gift
  box; the `Include me in the Leaderboard` opt-in with its `leaderboard-name`
  field; then a demo-only sandbox-outcome control (`name="hb-scenario"`,
  approved/declined/retry — clearly labelled as absent from the source) and
  `button.js-submit-button` "Continue to Payment" + `Back to Bundle`. Submit
  is a no-op until a processor is chosen: it mirrors the captured payment
  step by adding `js-has-errors has-errors` to `.payment-method-view` and
  unhiding `Please Select a Payment Method`. Right column: `Order Summary`
  (per-item lines, `Subtotal`, the regional tax line, bold `Total`, the
  `You're Supporting Charity` callout and the all-caps license notice) fed by
  GET /api/cart. Then POST /api/checkout → confirmation (order_no, items,
  the same subtotal/tax/total/charity quadruple, gift + leaderboard echo,
  keys teaser, View in Library) | HTTP 402 inline error with retry hint |
  empty cart → message + link to /bundles. The donation mode still comes
  from the bundle page via sessionStorage: the source has no split chooser on
  the review.
- login (/login): form → POST /api/account/login; success redirects to the
  goto param (same-origin paths starting "/" only, "//" rejected) else "/";
  rejects surface in `.js-status-message`. `.js-password-reset` swaps
  `.js-view-body` to the captured in-page Password Reset panel (heading,
  copy, email field, RESET PASSWORD, Contact Support → /support) →
  password-reset/start (sandbox_code hint) → code + new password →
  complete → signed in. SSO buttons show the truthful offline notice.
- signup (/signup): ≥8-char client password check mirroring the placeholder
  copy → register/start → verification step (sandbox_code hint) →
  register/complete → "/". Google SSO shows the same offline notice.
- account (/home/{library|purchases|keys|coupons}, /store/wishlist,
  /user/{settings|wallet}): replaces `.inner-main-wrapper` of the served shell.
  For /home/* it reproduces the captured shell shape — `nav.tabbar` of the four
  captured `a.tabbar-tab` tabs with their icons, all five `js-*-holder` panels
  with the inactive ones `is-hidden`, the `.bottom-tab-shortcuts` footer strip
  — and each interior's captured controls, wired locally against the existing
  APIs: Library (`#switch-platform.js-platform`, `#search.js-search`,
  `#sort-order.js-sort-order`, `#download-method.js-download-method`,
  `.js-subproducts-holder` rows against a `.js-details-holder` download-detail
  pane), Purchases (`#purchase-search`, `#purchase-sort`, the
  `Product`/`Date`/`Total` heading columns, `Total` = `charged_minor`), Keys
  (`#key-search.js-key-search`, `#key-sort.js-key-sort`, `#hide-redeemed`,
  `table.unredeemed-keys-table` with `Type`/`Game`/`Key or Entitlement`), and
  Coupons (the captured empty card, rendered into its holder on every tab as
  the source does). `.no-results` "Nothing found" is reachable on all three
  whenever a search or filter empties the list. Populated rows carry the
  `Seeded demo data` marker. /store/wishlist renders as a store page with **no**
  tab strip: the captured `My Wish List` header with its share affordances plus
  the full `li.wishlist-entity` tile family, or `.empty-wishlist` > h2
  "Your wish list is empty." /user/settings and /user/wallet render the
  settings sections listed under "Signed-in account surfaces". Skips DOMs that
  are not the served shell (e.g. the branded 404).

## Local visual audit disposition (2026-08-21 review round)

Method: `tools/audit_visual_diff.py` — offscreen headed chromium (matches the
capture pipeline; headless AA skews MAE 1-2%), MAE similarity vs the frozen
source frames, 43 cells. Result: 27 cells >= 0.99 (terms/mobile = 1.0);
every cell >= 0.94; all sub-0.99 cells are classified:

- store-product desktop 0.913: the source embeds an external video trailer;
  the clone fills the slot with the trailer's own poster thumbnail (external
  embed not reproducible offline; playback inert) — known difference.
- store-search desktop 0.942, games/bundles desktop 0.978, books/software
  desktop 0.969: source entrance-animation instability (calibration marked
  the calibrated ones source-limited; books/software are the same listing
  template) — reference-evidence class, not clone defects.
- login 0.982 / signup 0.989 desktop and a few text-page mobile cells
  (~0.977-0.989): sub-2% pixel-level rendering variance between local
  sessions; DOM, geometry (card-top/header rows byte-aligned with source)
  and copy verified identical; side-by-side visually indistinguishable.
  Recorded as a local-measurement caveat; the formal comparison runs in CI's
  single-environment live section.

Interaction parity fixes from the round: nav dropdown open/close (evidence:
interactive/nav-*-dropdown), listing countdown ticking, slick arrows
(delegated; includes membership .games-nav-*), splits panel toggle, suggest
panel pinned to the captured 5-row portal oracle with real row markup,
store-product featured slot repair, mobile parity fixups
(static/site/mobile-fixups.json: mobile-only lazy collages, mobile carousel
subtrees, Sofia Pro vertical-metric override <=767px, theia padding
neutralization), external links -> /external/<slug> interstitials
(verify static: CLEAN, 0 findings).

## Interaction ledger and the defects it exposed

`scope/interaction-ledger.json` (52 entries, all 23 journeys) is produced by
`tools/walk_interaction_ledger.py`: a headless walk of the running clone that
hit-tests every control, activates it, and re-verifies both a visible-text and
a raw-markup proof against the post-action document before accepting a row, so
an unproven row cannot be emitted. It brackets itself with `/__admin/reset` and
refuses to record key material, order numbers, addresses or credentials.

Walking the matrix that way surfaced defects the unit suites structurally could
not, all fixed and re-verified in a browser:

- **Seeded history was unreachable through the API.** The app resolved the
  session owner from the auth subject id while the seed writes business rows
  under the account's normalized email, so a freshly reset demo account signed
  in to an empty library and purchase history. The unit tests missed it because
  they read back rows they had just written under the same key.
  `clone/tests/test_auth.py::test_seeded_demo_history_is_visible_after_login`
  now pins the app-layer path (2 purchases, 8 entitlements).
- **Injected panels were pointer-blocked at the canonical viewport.** The
  frozen shell keeps an absolutely positioned hero layer that painted over the
  checkout and account panels, so their radios could not be clicked at
  1440x900. `clearFrozenOverlays()` neutralizes it on those routes.
- **Signup validation was invisible.** The frozen stylesheet hides
  `.js-input-error` until the site's own error class is applied, so the
  short-password message rendered into a hidden slot; it is now shown
  explicitly and mirrored into the visible status line.
- **The drawer's purchase controls did nothing.** They live in
  `.payment-buttons`, outside the `.checkout-section` subtree that was being
  wired; both are now routed into the local checkout.
- **Split-allocation radios changed nothing observable** (they only wrote
  session storage); they now switch which split breakdown is displayed.
- **The featured-image swap landed on a play-icon overlay** because a video
  thumbnail holds a poster plus an overlay and the last listener won; the
  holder is now bound once and always swaps in its poster, guarding against
  the lazy thumbnails whose `src` never shipped.
- The undo control gained a stable `js-hb-cart-undo` hook for contract use.

Two ledger observations are recorded rather than fixed: the frozen
`.js-close-cart` sits under the sticky navbar (not in required coverage), and
most media thumbnails carry no `src` because the site's lazy loader was
stripped, so only the ten that shipped an image are clickable.

## Upstream migration (2026-08-22) and the official diagnostic tools

The original upstream repository disappeared with its owner account; the
project moved to a new remote whose `main` is a direct continuation of the same
history, 121 commits ahead of this site's build baseline. This site was rebased
onto that `main` (conflict-free: every path it adds is new) and every gate was
re-run on the newer baseline. The shared contracts this site depends on —
`prompts/`, `websitebench/schemas/`, `deploy/generic-offline-clone/`,
`tools/offline_clone/`, `AGENTS.md` — were unchanged by those 121 commits.

That baseline also added two shared diagnostics this site now uses instead of
its own equivalents, per the repository rule to reuse existing CLIs:

- `websitebench-offline-clone tools visual-diff` supersedes the hand-rolled
  band analysis: it reports SSIM, changed-pixel ratio and **classified
  difference regions** with bounding boxes. It independently localizes this
  site's largest known difference to the featured-media slot on the product
  page, which is a far better artifact than a bare similarity number. The
  site's own `tools/audit_visual_diff.py` is kept only as the capture driver
  that sweeps checkpoint x viewport and produces the candidate frames the
  official tool consumes; it no longer stands as the classification evidence.
- `websitebench-offline-clone tools frontend-spec` extracts a page's controls,
  forms, data points and, critically, its console errors and failed requests.
  Running it exposed a defect nothing else had caught: unresolved assets were
  rewritten to a deterministic `/static/assets/missing/<sha>` path that does
  not exist, so the anchor bundle page fired **ten 404s and ten console
  errors** the source never emits.

  The fix is in `tools/build_frozen_pages.py`: a `<source>` or `<link>` whose
  only purpose is fetching an asset that was never localized is now **dropped**
  rather than pointed at a placeholder, and the URL is disclosed in the build
  report under `dropped_missing_references` (17 references: the ten external
  preview videos, six head-level preview/icon images and one script). Poster
  frames and layout are unaffected, the known difference stays honest, and
  `frontend-spec` now reports 0 console errors and 0 failed requests on the
  home, anchor-bundle, product and support pages.

  That reading held only for the **frozen** product page, `/store/satisfactory`:
  `dropped_missing_references` covers frozen head references, not seed media
  hydrated by `hb-app.js`, and a hydrated product page fired a 404 per
  unlocalized gallery reference. Two further fixes closed that:
  `tools/build_frozen_pages.py` no longer prunes runtime-referenced seed media
  (2,192 seed media refs, 0 missing — pinned by
  `clone/tests/test_no_remote_refs.py::test_seed_media_files_exist_on_disk`),
  and `hb-app.js` now injects seed HTML through an inert `<template>` and drops
  the absolute image URLs the source's own description bodies embed (212
  remote refs across 38 products, never localized) *before* the browser can
  fetch them. Measured headlessly after both: `/store/portal-knights` 0 broken
  images and 0 failed requests (was 47 broken / 48 failed), `/store/abiotic-factor`
  0/0, `/store/satisfactory` 0/0 — the frozen page's 31 broken thumbnails were
  the stripped slick lazy loader never promoting `data-lazy` to `src`, which
  `repairFrozenFeatured` now does (all 31 files were already on disk).

`tools/frontend_samples.json` stays as it is: it is the input
`websitebench-harbor derive-from-clone` reads, not a duplicate of the new
frontend-spec tool.

## What the authenticated handoff changed (2026-08-22)

Findings and their evidence are in `scope/handoff-findings.md`; the raw capture
stays in the gitignored `source-auth-scratch/walk-671/`. It corrected four
things the anonymous build had to guess:

1. **Wishlist route.** The source serves it at `/store/wishlist`, not
   `/home/wishlist`. Corrected in `app.py` (with the same secure-area gate),
   in the account menu, in the store sub-nav icon and in the panel dispatch.
2. **Bundle checkout is its own flow.** A bundle goes from its page straight to
   `/checkout` with a `Back to Bundle` link, and the store cart drawer stays
   empty while a bundle checkout is in flight.
3. **Checkout structure.** Two columns: a Choice offer card, a Delivery
   Information panel naming the destination account with a sign-out affordance,
   a Payment Method panel of three processor radios plus a redirect notice, a
   gift opt-in (recipient email versus gift link, with an anonymous option), a
   leaderboard opt-in, and a submit control that stays put until a payment
   method is chosen. The right column is an Order Summary with per-item lines,
   Subtotal, the regional tax line, a bold Total, a charity panel and a
   license notice.
4. **Summary math oracle.** The walked custom price produced subtotal CA$15.00,
   HST CA$1.85, total CA$16.85 and CA$0.75 to the bundle's charity.

Account empty-state headings are now frozen too: `Humble Library`,
`Purchased Products`, `Keys & Entitlements`, `Humble Coupons` and the wishlist's
`Your wish list is empty.`

**Still unavailable**, and honestly so: the populated library and purchase
history. The handoff account is new, and populating it needs a completed
purchase, which needs a real payment — outside the authorized scope. The clone
seeds those surfaces with synthetic entitlements so the journeys are exercisable,
but their layout is not claimed to match the source. Registration's submit-time
semantics stay out of evidence because the credential segment is excluded by
design, and no machine-recorded source-side trajectory exists: the human's walk
was already complete when the recorder would have attached, so the interaction
ledger is clone-side only and says so.

## Store cart drawer rebuilt from the authenticated capture (T11)

`source-auth-scratch/walk-671/cart-drawer-populated/` (gitignored) is the only
capture of a *populated* store drawer, and the drawer is now rebuilt against
it selector for selector, so contract selectors resolve against real source
structure rather than clone-invented hooks:

- **Row.** `div.js-shopping-cart-row.shopping-cart-row` inside
  `.js-shopping-cart-row-holder > .cart-group`, with two `div.row-contents`.
  The first holds `a.js-remove-from-cart.remove-from-cart` (icon
  `i.hb.hb-times-circle`, `aria-label="Remove from cart"`),
  `div.cart-item-information-wrapper` >
  `a.cart-item-name[href="/store/<slug>"][title]` +
  `ul.platforms.cart-platforms` (the DRM icon with its own `aria-label`, then
  one `Redeem for <OS>` line per operating system inside
  `aside.platform-info`), and `p.js-cart-item-price.cart-item-price` carrying
  the `sr-only` `Original amount` / `<s>` / `sr-only` `Discounted amount` /
  `span.current-price.discounted` sequence. The second holds
  `div.product-error-holder.js-product-error-holder-<machine_name>`.
  Icon classes and OS/DRM display labels are the source's own (the frozen
  store page's `li.operating-system.hb.hb-<icon>[title="<label>"]` and the
  store platform facets), not guesses.
- **Totals.** Three `div.total-row` in `.js-shopping-cart-total-holder`:
  `Sub-Total:` and `Total:` with the `total-amount is-original` /
  `is-discounted` pair, and the tax row with a single `total-amount`. The
  struck-through original on the `Total` row is the undiscounted sub-total,
  not sub-total + tax — that is what the capture shows (CA$5.48 / CA$1.54).
  The clone previously printed one `Total:` row that was really the subtotal.
- **Rewards / promo.** `.js-rewards-total-holder` loses the frozen `inactive`
  class and renders `div.humble-rewards-breakdown > .rewards-line-item` with
  `Wallet Credit Earned` + amount; `.js-rewards-section` loses `is-hidden`
  (its `Manage Your Rewards` link is in the capture's control list);
  `.js-shopping-cart-monthly-promo` renders
  `div.monthly-promo-wrapper.humble-choice` with the captured `h2`, offer
  paragraph and `p.small-link` fine print. Both amounts come from the same
  server computation as the totals.
- **Identity.** The signed-in `.email-holder` replaces the anonymous
  `Must be logged in to purchase` text node and Login link with
  `input.email-input.js-email` (disabled, generic
  `placeholder="your@emailaddress.com"`, `value` = the signed-in account's own
  address read at runtime) plus `span.email` `Not <address>?` and
  `a.logout.js-shopping-cart-logout`. It reads `account.email_normalized` —
  the field `/api/account` actually returns; the old code read a
  never-returned `email` key and silently fell back to the display name, so
  the drawer showed a person's name where the source shows an address.
- **Signed-in chrome.** The source drops the
  `Subscribe to hear about more deals!` checkbox and the Terms of Service
  paragraph once signed in. Both carry the source's own
  `js-newsletter-section` class and the captured signed-in drawer has zero of
  them, so both are removed from the frozen markup on sign-in.

Deliberately **not** reproduced from this capture, with reasons:

- The Optimizely/analytics payload and the vendor stacks (already covered by
  the stripped-vendor-stack known difference).
- The trailing empty `<p></p>` the source's promo template leaves after
  `p.small-link`, and the empty `title=""` on OS icons inside the redemption
  aside: rendering artifacts of the source's own templating with no content
  or behaviour attached.
- `data-model-id` carries the clone's cart line id, not the source's opaque
  model id (`c307`), which is server-side state the clone has no basis for.
- The absolute prices, which follow the seed's 2026-08-20 provenance rather
  than this 2026-08-22 capture — see the drift entry in the known-difference
  list.
- Per-DRM operating-system availability. The source's cart row renders one
  `li` per DRM with its own `aside.platform-info`, and the harvest's
  `icon_dict` values carry per-DRM availability; the seed keeps only
  `icon_dict`'s keys, so every DRM entry lists the product's full OS set. A
  two-DRM product therefore repeats its redemption lines once per store.

## Product detail: per-product rating and reviews (T06)

The product route serves the frozen `/store/satisfactory` page for every
product and hydrates it client-side. `hydrateProduct` rebound the title, price,
gem, platform badges, parties, description, system requirements and gallery —
but not `.user-rating-view` and not `.reviews-view`, so **every** non-frozen
product showed Satisfactory's `96% | Overwhelmingly Positive` and Satisfactory's
three OpenCritic quotes (PC Gamer / IGN / God is a Geek). That is a correctness
failure, not a cosmetic one: an agent reading the page reports another game's
facts.

Both sections are now rebound per product:

- `bindUserRating(product)` rebuilds `.review-text` as the captured shape
  (steam icon + `NN% |` + the label) and `.tooltip-text` as
  `NN% of the <count> user reviews on Steam in the last 30 days are positive.`
  The `review_text` token maps to its label by title-casing its words, which
  reproduces the one captured value (`overwhelmingly_positive` →
  `Overwhelmingly Positive`) and covers the other six the seed carries. The
  recency clause belongs to `display_user_ratings: "steam_recent"`; for
  `"steam_overall"` (6 of the 22 rated products) the clause is **dropped**
  rather than reworded, because that variant's copy was not captured.
  A product with no `user_rating` (47 of 69) gets the whole property emptied
  and hidden — never the frozen page's numbers.
- `bindReviews(product)` clears `.reviews-collection` and builds one
  `.reviews-entity` per `product.reviews` entry (snippet / score / author /
  outlet / url). No product in the authorized subset carries critic reviews, so
  in practice the section renders empty with a truthful note naming the product
  and saying Critical Reception was captured for one product only, and the
  OpenCritic attribution is hidden. See
  `claim.unavailable.product-critic-reviews`.

`clone/tests/test_product_detail.py` pins both directions: the API carries
distinct per-product ratings, no product claims critic reviews, `hydrateProduct`
calls both binders, `bindUserRating` empties **and** hides the property when
there is no rating, and — the actual regression guard — none of Satisfactory's
rating or review strings appear anywhere in executable `hb-app.js`.

## /store/c/{token}: one category namespace over three facets (T03)

`/store/c/{token}` was mapped to the `genre` facet alone, so all 8 Top-Platforms
links plus both `All` links rendered `0 Results` while the 8 genre links were
correct. The captured navigation's 16 distinct `/store/c/` tokens actually span
three facets, and the captured search page carries the authoritative
vocabularies (17 Genre, 11 Platform, 7 DRM `input.js-filter-option` values).
`searchPage` now resolves the token against those vocabularies **as rendered on
the page it is already serving**, in the order genre → platform → drm:

- `all` means no facet at all (the nav lists it as both `All Genres` and
  `All platforms`) → 69 results.
- `vr` is a **Genre** value (`Virtual Reality`), even though the nav files it
  under Top Genres alongside platform-looking siblings.
- `switch` is both a Platform and a DRM value; the nav files it under Top
  Platforms, which is why platform precedes drm.
- a token outside every vocabulary keeps the genre reading, so the page shows an
  honest `0 Results` rather than silently widening.

Measured on the running clone: `all` 69, `windows` 67, `steam` 61, `adventure`
40 (the captured oracle), `rpg` 26, `action` 52, `indie` 21, `mac` 14,
`simulation` 14, `linux` 13, `strategy` 8, `racing` 2, `switch` 2,
`oculus-rift` 1, and honest zeros for `switch2` and `vr` (the subset seeds no
`switch2` platform and no `vr` genre). `clone/tests/test_product_detail.py`
replays the resolution in Python over the captured DOMs, so a nav link that
stops resolving fails the suite.

The 8 `/store/promo/*` links in the same dropdown still return the branded 404
and are **not** in scope here: no promo listing page was captured, so there is
no oracle for what they should contain.

## Signed-in account surfaces

`/user/settings` and `/user/wallet` are routed behind the secure-area gate and
now render panels built from `source-auth-scratch/walk-671/user-settings`:
Account Information (Email Address + Update, Location, Language), Humble Choice,
Charity Contribution (Total Donated, Your Contribution + Calculate
Contribution, Charity Preference + Update), Payment Information (Saved
Payments, Humble Wallet), Contact Preferences (the ten captured subscription
checkboxes in captured order, only `abandoned_purchase_notification_emails`
checked, + Update) and Linked Accounts (Steam, Battle.net, Epic Games, GOG).
Three controls perform real local writes — the delivery email, the contact
preferences and the charity preference — and every control that cannot is
disclosed in place instead of being rendered dead:

- **Email Address → Update** writes a clone-side *delivery* address that the
  checkout review honours; the sign-in credential is unchanged because the
  vendored auth store owns it. Disclosed on the page and in
  `claim.difference.settings-delivery-email-is-local`.
- **Payment Information** keeps its heading and the empty saved-cards list but
  omits Billing history / Add credit card / Add PayPal, and says why.
- **Humble Wallet** shows the captured zero state and says there is no funding
  path, so `Add Funds` is not offered.
- **Language** renders the captured six-locale select and says only the
  captured English locale is served.
- **Linked Accounts** reuse the existing offline-SSO notice.
- The captured **Security** section is omitted whole — see
  `claim.difference.settings-security-section-omitted`.

The header account dropdown now matches the captured one exactly (Purchases,
Library, Keys & Entitlements, Coupons, Wish List, Wallet, Settings, Logout),
which is also what makes the two new routes reachable by navigation.

`/home/*` reproduces the captured shell shape: one `nav.tabbar` of exactly the
four captured tabs (`Purchases | Library | Keys & Entitlements | Coupons`, with
their captured icons), all five `js-*-holder` panels present with the inactive
ones `is-hidden`, and the `.bottom-tab-shortcuts` footer strip. Every captured
interior control is reproduced and wired against the existing APIs, filtering
and sorting the rendered rows locally:

- **Library** — `Platform` (`select#switch-platform.js-platform`, `all` plus
  only the platform values the account's entitlements actually carry),
  `input#search.js-search` with its clear icon, `Sort`
  (`#sort-order.js-sort-order`: Alphabetical / Recently updated), `Download
  method` (`#download-method.js-download-method`: BitTorrent / direct link),
  `.no-results.js-no-results` `Nothing found`, and the captured
  `.hb-download-list` split of `.js-subproducts-holder` against
  `.js-details-column`/`.js-details-holder`. Selecting a row fills the detail
  pane with that entitlement's delivery platforms, its download method and its
  key-reveal control — **this is T14's "inspect downloads" surface**, which had
  none before. It carries the same sandbox disclosure the checkout uses: there
  is no download payload in this clone and the key is a synthetic `SANDBOX-`
  code.
- **Purchases** — `input#purchase-search`, `Sort` (`#purchase-sort`:
  Alphabetical / Most recent) and the captured `.results .heading` columns
  `Product` / `Date` / `Total`. The `Total` column now prints `charged_minor`,
  the same figure the purchase detail calls `Total`; it printed the pre-tax
  subtotal, so one order showed two different totals (G17).
- **Keys** — `input#key-search.js-key-search`, `Sort` (`#key-sort`:
  Alphabetical / Most recent), `input#hide-redeemed` with its
  `Hide redeemed keys & entitlements` label, and
  `table.unredeemed-keys-table` with the captured `Type` / `Game` /
  `Key or Entitlement` headers. Revealing a key updates the local row so the
  hide-redeemed toggle takes effect without a refetch.
- **Wishlist** — the captured `.wishlist-header-container` (`My Wish List` +
  the pencil icon, `Share Wish List` with its checked `input[name=share]`, and
  the mail / Facebook / Twitter share affordances) and the populated
  `ul.entities-list.js-entities-list > li.wishlist-entity` tile family: entity
  link, image, title, the `saved` wishlist button, platform and OS icon lists,
  the discount gem with its `Discount Breakdown` and price pair, the
  `.price-button` (price / `Add` / `Buy`) and `.wishlist-edit-actions >
  .remove-wishlist`. The account tab strip the clone used to inject here is
  **gone**: the source serves the wishlist as a store page and its capture has
  zero `tabbar-tab`. The share links point at this origin's own wishlist route
  (the source shares an absolute `/store/wishlist/<id>` URL) and the social
  ones surface the offline notice instead of navigating off-origin.

Because the walked account was empty, the populated library, purchases, keys
and purchase-detail views each carry a discreet `Seeded demo data` line saying
the rows are the clone's own construction and that only the surrounding layout
and controls come from the capture
(`claim.difference.seeded-account-interiors-labelled`).

**Reproduced from the capture but with the source's own empty state kept
reachable:** `Nothing found` was previously unreachable because the demo
account is always populated. It now renders whenever a search or filter
empties the list on any of the three interiors, which is how the captured copy
gets exercised.

**Not reproduced, with reasons.** The captured `Location` select is disabled in
the source too, so it stays disabled and no location write exists. The
`Humble Coupons` sidebar the meta headings suggest is in fact the hidden
`js-coupon-holder` panel (`is-hidden` in every capture), so it is reproduced as
a hidden holder rather than as a visible card. `/home/<unknown>` still falls
back to the library rather than 404-ing (G20.1, untouched).

**Ledger note.** `tools/walk_interaction_ledger.py` is updated for all of the
above (the cart rows now pin the source row markup and the
`js-remove-from-cart[aria-label="Remove from cart"]` control, and three new
signed-in rows pin the totals block, the wallet-credit line and the email
identity block), but `scope/interaction-ledger.json` has NOT been regenerated:
a full re-walk currently aborts inside the account-panel journeys, and those
interiors have now been rebuilt to the captured shape (`js-hb-account-content`
is gone entirely — the panels render inside the captured `js-purchase-holder` /
`js-library-holder` / `js-key-manager-holder` / `js-coupon-holder` shell, the
tab strip is the captured four tabs, and the library/purchases/keys interiors
gained their captured search, sort, platform, download-method and
hide-redeemed controls). The walker's two interior selectors were realigned
with the new shape and both resolve against the running clone
(`.js-library-holder .js-details-holder button` for the key reveal,
`.js-purchase-holder .results .body > a:first-child` for the newest purchase
row), but until a walk completes end to end the committed ledger's five
`Qty 1` cart proofs describe the previous drawer and its `js-hb-account-content`
account-panel proofs describe the previous interiors; both are stale.

## Countdown timers are anchored to the capture instant (2026-08-23)

The clone's "now" is the capture instant — every price, listing, tier and
availability state in it is frozen there — so the countdowns are too. On load
each timer starts at the remaining time the source rendered into the frozen
markup and ticks down in real time from there.

The alternative, recomputing against the absolute `end_at` dates, was what the
clone did before and it is wrong in two ways at once: the tiles that were
ending soonest at capture are now past their end date and pin at
`00:00:00:00`, and every surviving tile drifts one day further from its frozen
`N Days Left` label per day that passes. Anchoring keeps the first paint
identical to the capture and the badge alive.

Three markup families are driven, all of them read from the frozen DOM rather
than from the API, so no timer depends on a seeded date:

- pill + red pair inside `.js-countdown-view` (home, `/bundles`, `/games`)
- `.timer.blocky-timer` unit cells (`/store`)
- the pill's `data-countdown` attribute and any time-phrase `aria-label`

Known cost, measured: because the badges now change, two screenshots of the
same page eleven seconds apart are no longer bit-identical. Full-page MAE
similarity across that interval is 0.99984 on `/bundles` (57 timers), 0.99999
on `/store`, 0.99994 on `/games` and 0.99999 on the home page — far below the
per-cell visual thresholds, but it is a real loss of frame determinism and is
recorded here rather than left to be rediscovered.

## Signed-in navbar rebuilt against the captured markup (2026-08-23)

The account menu had been improvised: a text button printing the display name
plus a hand-styled panel. The authenticated captures show the source printing
no name at all — a user-circle icon and a caret inside a
`user-dropdown-container`, with the account routes in a click-to-open panel.
The clone now reproduces that markup, and the signed-out `Sign Up` / `Log In`
anchors carry `?goto=<path>` the way the source's do. Both are covered by
`claim.structural.navbar-account-menu` and `claim.structural.header-auth-goto`.

One divergence is deliberate: the source hides the panel with a bare `hidden`
class whose rule is not in any stylesheet the capture localized, so this layer
keeps the class for markup fidelity and drives visibility itself.
