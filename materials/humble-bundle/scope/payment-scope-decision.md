# Payment-scope decision — humble-bundle

Decision: **`local-sandbox` only; `stripe-test` is absent, so no
`scope/payment-scope.json` proposal is required** (per
`references/05-implement.md`, the `check-payment-scope` gate applies only when
enabling `stripe-test`).

Humble-specific shape of the local checkout:

- The pay-what-you-want amount chosen on the bundle page (preset tier or
  custom amount, e.g. the task-671 $15) **is** the order amount. It is
  validated server-side against the frozen tier floor (CA$9.71 for the anchor
  bundle) and tier thresholds; the charged amount and the unlocked item set are
  recomputed server-side from the persisted cart, never trusted from the
  client.
- The only client payment input is an opaque sandbox scenario id
  (`sandbox-approved`, `sandbox-declined`, `sandbox-retry`). Card, CVV,
  expiry, bank, wallet and Stripe-shaped keys are rejected before persistence
  by the payment-key guard.
- Charity split (Default / Extra to Charity / Custom) is order metadata that
  must sum to the paid amount using the frozen split shapes
  (publishers/Humble/charity); it never changes the charge.
- An approved attempt creates the purchase, the library entitlements and the
  synthetic `SANDBOX-` keys in one site-bound SQLite transaction; declined and
  retryable attempts create nothing.
- Promo/gift options (T13) will be modeled after the handoff walk freezes the
  real checkout surface; whatever form they take, they remain sandbox tender
  or metadata with no real-world effect.
- The source walk hard-stops before any payment submission, so no behavioral
  claim is made about the source's real payment processing (observed only:
  checkout entry surface).

Authorization remains `STRIPE_TEST_AUTHORIZED=false` and
`LIVE_PAYMENT_AUTHORIZED=false`; no real mail or payment side effect is in
scope.
