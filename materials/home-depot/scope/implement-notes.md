# Implementation contract (durable working notes) — home-depot

Frozen-snapshot + interaction-JS clone: captured post-render pages are served
at their real routes with scripts stripped; dynamic behavior is re-implemented
in `static/site/hd-app.js` against a local JSON API backed by the vendored
`websitebench.site_backend` seam. This file is the human-readable inventory of
what the clone supports; the machine authority is the sibling JSON files
(`purpose.json`, `journeys.json`, `routes.json`, `checkpoints.json`,
`invariants.json`, `coverage.json`, `verify.json`, `backend-capabilities.json`).

## File layout (owners)

- `clone/app.py` — composition root: frozen-page routing, JSON API, cookies,
  admin reset. No business logic.
- `clone/backend/catalog_db.py` — business schema + semantics on the
  `websitebench.site_backend` seam (catalog/cart/checkout/orders/lists/auth).
- `clone/backend/seed_data.json` — deterministic seed (products/stores/orders/
  lists; fully synthetic identities).
- `clone/frontend/pages/*.html` — localized frozen snapshots (zero remote refs).
- `clone/static/site/hd-app.js` — the interaction layer (only file that
  mutates page behavior at runtime).
- `clone/static/assets/…` — content-addressed localized assets.
- `clone/tests/` — site test suite (must stay green).

## Server routes (frozen pages and shells)

| Route | Serves |
|---|---|
| `/` | home (desktop; mobile variant captured) |
| `/b/Tools/N-5yc1vZc1xy`, `/b/Drills/N-5yc1vZc27f` | category PLPs |
| `/p/<slug>/320326787` | anchor PDP (Milwaukee 3697-22) |
| `/s/<query>` | search results / no-results (live panel over shell) |
| `/cart`, `/checkout`, `/order-confirmation` | home shell + live panel |
| `/myaccount/*`, `/list/*` | home shell + live account panel |
| `/auth/view/signin`, `/auth/view/createaccount` | email-first auth entry |
| `/c/customer-service`, `/c/customer_service` | help center |
| anything else | branded 404 (full footer + nav) |
| `/healthz`, `/favicon.ico`, `/external/<slug>`, `/__admin/reset` | infra |

## JSON API contract

- `GET /api/search` — `q`, `sort` (`default` = captured Top-Sellers order,
  `top_rated` = review-volume-weighted rating (Bayesian, m=50, c=4.6),
  `price_low`, `price_high`, `reviews`), `limit`, `offset`, plus filters
  `brands`, `price_max`, `min_rating`; returns products + facets.
- `GET /api/products/{itemId}`, `GET /api/products/{itemId}/related`,
  `GET /api/category`.
- Cart: `GET /api/cart`; `POST /api/cart/add|update|remove`;
  `POST /api/cart/store` (switch pickup store); `GET /api/stores`.
- Gift card: `GET /api/giftcard/check?code=…`.
- Checkout: `POST /api/checkout` with `first_name`, `last_name`, `phone`,
  `scenario_id`, `fulfillment` (`pickup`|`delivery`), optional `gift_code`.
- Orders: `GET /api/orders`, `GET /api/order/{n}`,
  `POST /api/order/{n}/cancel|return|reorder`.
- Lists: `GET /api/lists`, `POST /api/lists/add`.
- Account: `GET /api/account`; `POST /api/account/login|logout`;
  `POST /api/account/register/start|complete`;
  `POST /api/account/password-reset/start|complete`.

## Sandbox & demo surface (everything a task run may rely on)

- **Demo account** (seeded, fully synthetic): `demo.shopper@example.test` /
  `HomeDepotDemo!2026` (“Jordan Reyes”). Deterministic reset restores the
  seed password even after an in-run password reset.
- **Payment scenarios** (`scenario_id`): `sandbox-approved`,
  `sandbox-declined`, `sandbox-retry`. No card/bank/Stripe field is accepted
  anywhere (payment-shaped keys are rejected before persistence).
- **Sandbox gift cards** (tender, see `payment-scope-decision.md`):
  `SANDBOX-GIFT-25` ($25), `SANDBOX-GIFT-100` ($100). Order totals are
  unchanged; the gift value reduces the amount charged through the sandbox.
  API field name is `gift_code` (a `*card*` key would be rejected by the
  payment-key guard).
- **Registration / password-reset OTP**: offline `mail_mode=LOCAL_ONLY`
  surfaces the 6-digit `sandbox_code` in the response/UI; the deployed
  `cloudflare-review` profile sends real mail and does not surface it.
- **Cookies**: session `__Host-websitebench-home-depot-session`
  (Secure/HttpOnly/Lax), guest cart `hd_cart`.
- **Admin reset**: `POST /__admin/reset` with header
  `X-WebsiteBench-Admin-Token` (env `WEBSITEBENCH_HOME_DEPOT_ADMIN_TOKEN`);
  atomically restores the full deterministic seed (catalog, stores, seed
  orders `WD12340001` Completed $150.12 / `WD12345678` Ready for Pickup
  $430.92, “Workshop” list, demo account + password, clears run accounts,
  carts, placed orders).

## Business rules (frozen from source evidence)

- Anchor: Milwaukee 3697-22 / itemId `320326787`, $399.00, rating
  4.7664 / 3981 reviews — the highest-rated SKU for the 535 query (walk-frozen
  oracle); `top_rated` sort must rank it first.
- Catalog: 90 real public SKUs in captured Top-Sellers DOM order
  (`sort_order`); stores seed `#1287 Niagara Falls` (default) + 2 more.
- Cart: “Limit 3 per order” clamp; est. tax 8% (matches captured
  $399 → $430.92); remove supports one-step Undo restore.
- Fulfillment: `pickup` → status “Ready for Pickup”; `delivery` → “Ordered”
  (requires street address).
- Order actions: cancellable = {Ready for Pickup, Processing, Ordered};
  returnable = {Completed, Picked Up}; reorder copies items to the cart.
- Checkout validation: first/last/phone required (inline messages); delivery
  additionally requires an address.

## Behavior evidence sources

- `source-current/2026-08-18.home-depot-r1/` — 27 anonymous checkpoints
  (frozen DOM authority for order, copy, layout).
- Gitignored `source-auth-scratch/walk-535/` — authorized synthetic checkout
  walk (checkout accordion structure, totals, ranked search snapshot).

## Known-difference policy

Documented, intentional differences from the live source:

- Header is re-implemented (clean logo/store/search/Shop-All flyout/account/
  cart) because the frozen React header collapses without its JS.
- Registration / password-reset screens were never captured (deferred at the
  auth handoff); they are truthful styled panels, not frozen pixels.
- PDP media gallery is rebuilt as main-image + thumbnail strip (the frozen
  gallery loses its sizing script).
- Personalised home modules (php-hydrator, “Loading …” recommendation rails)
  are filled with real catalog content or collapsed — never left as skeletons.
- Product catalog is an authorized subset (first-2-pages ruling); product
  content is not claimed to match the live site day-to-day.
- The classless “CHRISTMAS CAME EARLY” promo strip renders unstyled on `/c/`
  (its CSS never shipped in that bundle); cosmetic.
