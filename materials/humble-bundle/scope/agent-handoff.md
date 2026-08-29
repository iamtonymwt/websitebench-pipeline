# Offline-clone handoff — humble-bundle

- Site: `humble-bundle` (WB063, Humble Bundle)
- Status: the anonymous scope is complete and machine-clean; the authenticated
  surfaces are functionally complete but their layout is not yet frozen from
  source evidence, because the one authenticated handoff has not happened yet.
- Current reference: `references/08-deploy.md` (deployment preparation done)
- Next reference: `references/03-human-handoff.md` (the outstanding handoff)
- Worktree disposition: committed on branch `add-humble-bundle`; no push, no
  PR, no workflow dispatch, no deployment.

## Authorization ceiling

- `AUTHORIZED_SOURCE_MUTATIONS = ["registered-bundle-cart-checkout-walk"]`.
  Nothing in that allowance has been exercised yet: every byte of source
  evidence in this build came from anonymous GET page loads.
- `REAL_EMAIL_AUTHORIZED=false`, `STRIPE_TEST_AUTHORIZED=false`,
  `LIVE_PAYMENT_AUTHORIZED=false`, `PUBLIC_DEPLOYMENT_AUTHORIZED=false`,
  `PUSH_AUTHORIZED=false`, `PR_AUTHORIZED=false`.
- `RIGHTS_OR_REDISTRIBUTION_STATUS=unknown`. The source `robots.txt` carries a
  Ziff Davis notice prohibiting automated scraping and AI-training use without
  written permission. It is recorded for human rights review; no conclusion in
  this build authorizes redistribution or publication.
- Committed fixtures are fully synthetic. No credential, cookie, token, OTP,
  key value or order number appears in any tracked artifact.

## What the clone supports

- **Frozen anonymous surface at real routes**: home, bundles listing and the
  games/books/software category pages, the anchor bundle and the fixed-tier
  bundle, the store landing, store search (results and the captured
  no-results state), a store product page, Humble Choice, sign-in, sign-up,
  five legal pages, three help-center pages and the branded 404 — 25 pages,
  localized to 544 assets with zero remote runtime references.
- **Pay-what-you-want tier engine** (the site's core mechanic): cumulative
  tier thresholds, preset buttons, custom amounts, per-item lock badges, the
  floor rejection, and the charity split panel in its default, extra-charity
  and custom modes. All 13 active game bundles carry full tier data, so the
  engine generalizes beyond the anchor.
- **Commerce loop**: store search with genre/platform/DRM facets, four sort
  modes over the captured order oracles, the header suggest panel pinned to
  its captured five-row shape, product detail hydration, a cart drawer with
  amount edits and one-step undo restore, checkout with digital-delivery and
  gift choices, sandbox payment scenarios (approved, declined, retryable) and
  an order confirmation reflecting the chosen price and split.
- **Accounts on the `websitebench.site_backend` seam**: registration with a
  local-outbox verification code, sign-in and sign-out on a `__Host-` session
  cookie, the in-page password-reset flow, the `/home/*` secure-area gate
  reproducing the source's `goto` redirect, a seeded demo account with two
  purchases, library entitlements with revealable synthetic `SANDBOX-` keys,
  purchase history, wishlist, and a deterministic admin reset.
- **Machine authority** for the above is the sibling scope files
  (`purpose.json`, `routes.json`, `journeys.json`, `checkpoints.json`,
  `invariants.json`, `coverage.json`, `claims.jsonl`, `verify.json`,
  `backend-capabilities.json`); `derived-task-brief.json` is the retained
  planning record. Human-readable inventories are `implement-notes.md`,
  `data-contract-notes.md`, `payment-scope-decision.md` and
  `deployment-notes.md`.

## Current machine evidence

- Clone tests: **39 passed**, 0 skipped (catalog and suggest order oracles,
  tier math, cart cap, checkout guards and split validation, auth gate and
  cookie attributes, lifecycle reset and replay, smoke over every frozen
  route). Every p0 invariant carries a non-empty positive and negative test.
- Offline-clone diagnostic: `verify --section static` = **clean**, execution
  complete, 0 findings. The `live` section requires the Linux-only candidate
  sandbox and runs in CI, as with the earlier sites.
- Visual: three-frame source calibration over 24 checkpoint cells produced
  per-cell thresholds; 21 cells are acceptance-eligible and 3 desktop cells
  are source-limited by an entrance animation and kept as reference evidence.
  A separate local clone-versus-source sweep of 43 cells placed 27 at or above
  0.99 similarity with every cell at or above 0.91; each sub-0.99 cell is
  classified in `implement-notes.md`.
- Harbor: same-id draft pair (`harbor/sites/humble-bundle` +
  `harbor/instances/humble-bundle`); `validate` = draft / scorable false /
  missing exactly 200 cases (T1 20, T2 165, T3 15) as a new site should be;
  `validate-corpus` = valid. The OpenCLI interaction contract was derived from
  the clone's own samples with **0 pending items**, both `browser: false`
  adapter sets are in sync, and the instance selects the `core` profile.
  Official replay records `opencli-unavailable` (the binary is not on this
  machine's PATH — a sanctioned outcome), so an independent Node confirmation
  of the derived assertions was run instead: **23/23 hold**.
- Deployment package: `deployment.humble-bundle.v2.json` schema-valid;
  `deploy-humble-bundle-public.yml` exposes only the `deploy` boolean;
  `npm test` 23 passed / 2 skipped, `prepare --check-only` valid with 0
  warnings, `deploy --dry-run` complete with 0 warnings. Persistence is
  disclosed as ephemeral (`cloudflare-review`).
- Interaction ledger: `scope/interaction-ledger.json`, 52 proven entries
  covering all 23 journeys, regenerated deterministically by
  `tools/walk_interaction_ledger.py`. The walk exposed seven clone defects
  (including seeded history being unreachable through the app's owner key and
  injected panels being pointer-blocked at 1440x900); all are fixed, re-verified
  in a browser and described in `implement-notes.md`.
- Repo gates: `ruff` clean; prompt freshness 15 passed; the offline-clone,
  harbor and project suites report 381 passed with exactly the 10 documented
  macOS Linux-only baseline failures, none of which reference this site.

## What is not done, and why

1. **The authenticated handoff (blocking, human-only).** The source's
   registration submit semantics and the interiors of checkout, the library,
   the key list, purchase history and the wishlist sit behind a login wall,
   and the credential boundary belongs to the human. Nine `claims.jsonl`
   entries are recorded `unavailable` for exactly these surfaces. The clone
   implements them truthfully from their JSON contracts and marks the affected
   code `REFINE-AFTER-HANDOFF`, but their layout is not claimed to match the
   source. This is also what a formal source-side trajectory for inventory
   task 671 requires.
2. **`verify --section live`** needs the Linux candidate sandbox: CI only.
3. **The 200-case scorable benchmark** is a separate authoring task; the
   instance is a sanctioned non-scorable draft until then.
4. **Real publication** needs an explicit human grant for this exact
   candidate, plus a Cloudflare custom domain and the repository secrets
   listed in `deployment-notes.md`.
