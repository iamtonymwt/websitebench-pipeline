# Payment-scope decision — home-depot

Decision: **`local-sandbox` only; `stripe-test` is absent, so no
`scope/payment-scope.json` proposal is required** (per
`references/05-implement.md`, the `check-payment-scope` gate applies only when
enabling `stripe-test`).

The clone models a strictly local checkout so ordering semantics can be
exercised without collecting or simulating real credentials:

- The only accepted client payment input is one opaque sandbox scenario id:
  `sandbox-approved`, `sandbox-declined`, or `sandbox-retry`. Card number,
  expiry, CVV, bank/routing, Stripe identifiers and client-supplied totals are
  rejected before persistence by a payment-shaped-key guard (`*card*`, `cvv`,
  `pan`, `expir*`, `bank`, `routing`, …).
- Amount, currency, owner and canonical cart fingerprint are computed
  server-side from the persisted cart. An approved attempt creates the order,
  order items and cart clear in one site-bound SQLite transaction
  (create_intent → attempt → consume_approval). Declined/retryable attempts
  create no order.
- **Gift cards are sandbox tender, not discounts**: `SANDBOX-GIFT-25` ($25)
  and `SANDBOX-GIFT-100` ($100) mirror the source checkout's "Apply Gift
  Card" option. Order subtotal/tax/total are unchanged; the gift value
  reduces the amount charged through the payment sandbox and is stored as
  `gift_minor` on the order (confirmation shows "Gift Card applied −$X /
  Charged to card $Y"). The value is clamped so at least 1¢ still flows
  through the sandbox charge; an unknown code is a 400. The API field is
  `gift_code`, deliberately named to stay outside the payment-key guard while
  real instrument fields remain forbidden.
- This is a clone-local contract: the source walk stopped at the payment
  boundary (hard stop before order submission), so no behavioral claim is
  made about the source's real payment processing.

Authorization remains `STRIPE_TEST_AUTHORIZED=false` and
`LIVE_PAYMENT_AUTHORIZED=false`; no real mail or payment side effect is in
scope.
