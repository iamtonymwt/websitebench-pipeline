# Offline-clone final handoff — home-depot

- Site: `home-depot` (WB062, The Home Depot)
- Status: complete for the authorized offline-clone scope; all 23 inventory
  tasks (T01–T23) implemented and browser-verified end-to-end
- Current reference: `references/08-deploy.md`
- Next reference: none
- Worktree disposition: committed on branch `add-home-depot` and submitted as
  PR #5 (`iamtonymwt:add-home-depot` → `tuxyw123/websitebench-pipeline:main`);
  no workflow dispatch or deployment was performed.

## Authorization ceiling

- Source mutation was limited to the authorized
  `anonymous-cart-checkout-walk` (synthetic identity, hard stop before any
  payment/order submission on the live site).
- `REAL_EMAIL_AUTHORIZED=false`, `STRIPE_TEST_AUTHORIZED=false`,
  `LIVE_PAYMENT_AUTHORIZED=false`.
- `PUSH_AUTHORIZED=false`, `PR_AUTHORIZED=false`,
  `PUBLIC_DEPLOYMENT_AUTHORIZED=false`; deployment work stopped after local
  `--check-only` and `--dry-run`.
- Committed fixtures are fully synthetic; authenticated source evidence lives
  only in gitignored `source-auth-scratch/`.

## Delivered contract (what the clone supports)

- Frozen anonymous surface at real routes: home, Tools/Drills PLPs, anchor
  PDP (Milwaukee 3697-22), search results/no-results, cart, checkout, order
  confirmation, email-first sign-in, help center, branded 404 — localized
  with zero remote runtime references.
- Full commerce loop: search (captured Top-Sellers default order,
  review-weighted Top Rated, price/reviews sorts, brand/price/rating facets,
  compare), PDP (gallery, qty w/ Limit-3, variant options, related strip,
  save-to-list), cart (qty update, remove + one-step Undo restore), checkout
  (store pickup w/ store switch + curbside, delivery w/ address validation,
  inline required-field validation, sandbox gift-card tender, local-sandbox
  payment scenarios), order confirmation reflecting all choices and totals
  ($399.00 / $31.92 / $430.92 anchor math).
- Accounts on the `websitebench.site_backend` seam: sign-in/out
  (`__Host-` session cookie), registration and password reset with local-
  outbox OTP, account dashboard (orders w/ cancel/return/reorder guards,
  lists, profile), seeded demo account and order history, deterministic
  admin reset restoring the full seed.
- Sandbox surface for task runs (details in `implement-notes.md`): demo
  account `demo.shopper@example.test`, scenarios
  `sandbox-approved|declined|retry`, gift cards `SANDBOX-GIFT-25|100`,
  surfaced OTP codes offline, `/__admin/reset`.
- The frozen current authority is `purpose.json`, `journeys.json`,
  `routes.json`, `checkpoints.json`, `invariants.json`, `coverage.json`,
  `verify.json`, `backend-capabilities.json`; `derived-task-brief.json` is
  the retained planning record.

## Current machine evidence

- Clone tests: **51 passed** (auth, catalog/cart/checkout incl. gift-card
  math and sort oracles, lifecycle, no-remote-refs, smoke).
- Offline-clone diagnostic: static **clean** — 0 findings, 0 remote
  references, 0 secrets, 12 files scanned, execution complete. Live section
  is `incomplete` on macOS (candidate sandbox requires Linux) and runs in CI,
  same as the ASPCA precedent.
- Repo gates: `ruff` clean; prompt freshness 15 passed; full repo suite at
  last full run: 390 passed with the 10 documented macOS Linux-only baseline
  failures, 0 regressions, none referencing home-depot.
- Harbor: strict same-id v2 draft pair (`harbor/sites/home-depot` +
  `harbor/instances/home-depot`), `validate` = draft / scorable:false /
  missing 200 cases (intentional — case authoring is a separate task);
  OpenCLI interaction contract with 6 browser:false profiles; official
  `run-opencli` replay = `opencli-unavailable` (binary not on PATH,
  sanctioned outcome); independent node confirmation of the generated
  adapters: **9/9 assertions hold**; adapters in-sync; corpus valid.
- Deployment package: `deployment.home-depot.v2.json` schema-valid;
  dispatcher workflow mirrors the ASPCA structure; `npm test` 23 passed /
  2 skipped; `prepare --check-only` valid with 0 warnings
  (domain `home-depot.website-bench.com`); `deploy --dry-run` complete with
  0 warnings (worker `websitebench-home-depot-demo`).

## Remaining work (outside this handoff)

- `verify --section live` in CI (Linux-only sandbox).
- 200-case scorable benchmark authoring (separate task; instance is a
  sanctioned non-scorable draft until then).
- Real public deployment — requires an explicit human grant
  (`deploy=true` dispatch) for this exact candidate.
