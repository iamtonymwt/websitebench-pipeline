# Authenticated handoff findings (tr-001, 2026-08-22)

The human registered an account personally and walked the bound trace
(`ht-001`, inventory task 671) to the checkout review, stopping before any
payment submission. The agent then explored the authenticated surfaces in that
session. Raw captures — DOM, viewport and full-page screenshots, per-state
metadata — live only in the gitignored
`source-auth-scratch/walk-671/`; nothing containing the account's real address
enters a tracked file or a clone fixture.

Every statement below is `directly-observed` from that session.

## Account route map (corrects an implementation guess)

| Surface | Real route | Empty-state heading |
|---|---|---|
| Library | `/home/library` | `Humble Library` |
| Purchases | `/home/purchases` | `Purchased Products` |
| Keys | `/home/keys` | `Keys & Entitlements` |
| Coupons | `/home/coupons` | `Humble Coupons` |
| Wishlist | **`/store/wishlist`** | `Your wish list is empty.` |
| Settings | `/user/settings` | sections: Account Information, Email Address, Location, Language, Humble Choice, Charity Contribution, Total Donated, Your Contribution |
| Wallet | `/user/wallet` | not captured |

The wishlist lives under `/store/`, not `/home/`. The clone had guessed
`/home/wishlist`; that is a real routing difference to correct.

## Bundle checkout is its own flow, not the store cart

A bundle goes straight from its page to `/checkout` (the review offers
`Back to Bundle`). The store cart drawer is a separate surface and showed
`Cart (0 items)` while a bundle checkout was in flight. The clone currently
routes a bundle through the same cart the store products use.

## Checkout review structure (single page, redirect-based payment)

- **Delivery Information** — states that the bundle will be sent to the account
  email, with a `Not You? Sign out` affordance. There is no self-versus-gift
  radio pair here; gifting is a separate opt-in (below).
- **Payment Method** — three radio choices labelled `Paypal`, `Credit Card`,
  `Alipay` (`name="processor-type"`, Stripe-backed values), plus the notice
  that after clicking `Continue to Payment` the buyer is redirected to complete
  the purchase securely, and a prompt to select a method first. The submit
  control stays on the review until a method is chosen, which is why the review
  does not advance on its own.
- **Gift flow** — a `This purchase is a gift` opt-in
  (`name="gifting-enabled"`) revealing a `gift-type` choice between
  `gift-recipient-email` and `gift-recipient-link`, a
  `Gift Recipient Email Address` field, and an anonymous-gift checkbox.
- **Leaderboard opt-in** — `Include me in the Leaderboard` with a
  `Leaderboard Name` field.
- **Humble Choice upsell** — an unchecked `add-upsell` checkbox whose offer copy
  describes a monthly membership that would renew automatically. It was not
  enrolled: the box was already clear and the renewal sentence is offer copy in
  the markup, not an active subscription.
- **Order Summary** — bundle name, item count (`7 Items` at the walked price),
  the chosen amount, `Subtotal`, `HST`, `Total`, then a
  `You're Supporting Charity` line naming the amount that goes to the bundle's
  charity. At the walked custom price of CA$15.00: subtotal CA$15.00,
  HST CA$1.85, total CA$16.85, charity CA$0.75.

Tax is labelled **HST** for this region, and the charity contribution is a
visible summary line rather than only a split panel.

## Second pass: surfaces that needed only a cart mutation

The first pass filed several surfaces as unavailable too quickly. Adding an
item to the cart and to the wishlist is explicitly inside the authorized walk
(it mutates account state, not money), so these were captured on a second pass
with nothing submitted:

- **Wishlist, populated.** Saving a store product flips its control to an
  on-wishlist state and the wishlist page lists the product.
- **Store cart drawer, populated.** With one product in it the drawer shows the
  product title, per-platform redemption lines, an original-versus-discounted
  amount pair, a `Sub-Total` with the same pair, a `Sales Tax` line, a `Total`
  with the pair, a wallet-credit-earned line, a Humble Choice coupon offer, and
  two purchase controls (`Pay with Paypal`, `Pay with card`) alongside account
  controls. Note the store drawer labels tax `Sales Tax`, where the bundle
  checkout labels it `HST`, and it carries the strike-through original amount
  the clone's drawer does not.

## Recorded trajectory (tr-001) and the two-sided comparison

A second handoff session recorded the bound trace in the human's own browser
with `websitebench-browser-trajectory`. The recorder omits input values,
element text and URL queries by design, so this establishes structure only —
routes, redirects, selectors, step order and form actions — never pixels, copy
or network closure. Login was already complete, so no credential segment
existed to discard.

What it establishes beyond the earlier captures:

- The human reaches the bundle through the **header search**, not the bundles
  listing: the search input is focused, a query is entered, and a result is
  activated straight onto the bundle route.
- The price is typed into the **custom-amount field**; no event in the ledger
  touches a preset control, and the walked $15 is not among the bundle's preset
  prices, so the custom field is the only route to it. (An earlier draft of this
  file claimed a preset was activated; that was inferred from the shared
  `name="amount"` attribute without checking the recorded class, and the ledger
  contradicts it.)
- The bundle page **submits a form** whose action lands on the checkout review.

The same journey was then recorded against the running clone and compared with
the repository's diff command (diagnostic only, no gate). Similarity 0.82 with
four findings, all dispositioned as **demonstration differences rather than
clone omissions**: every element the source ledger names — the search input,
the amount control, the submitting form — exists in the clone and was exercised
in the candidate run. The two unaligned entries are bare `SPAN` and `DIV` clicks
the recorder cannot identify because it omits element text, and the extra
candidate event is one additional change event from the scripted typing. No
candidate repair item was raised.

## What the handoff did NOT establish

A free store product was pursued specifically to populate the library without
spending money; it is gated behind linking a third-party Steam account, which
would create a persistent external account association outside the granted
scope, so the attempt was stopped at the dialog. The free-claim flow itself is
therefore recorded as a distinct surface: activating a free product opens a
dedicated modal rather than adding to the cart.

The account is newly created, so the library, purchases and keys surfaces were
captured in their **empty** states only. Their populated layouts still require
a completed purchase, which needs a real payment — outside the authorized
scope. The `claims.jsonl` entries for those interiors therefore stay
`unavailable`, narrowed to the populated case: their empty states are now
directly observed. The payment processor's own form was not opened; the walk
stopped at the review, as authorized.

## Anonymous header re-check (2026-08-23)

A reviewer reported that the source's top-right area carries a dropdown the
clone did not have. An anonymous re-visit of the live source separates the two
states, and only one of them was a clone defect.

**Signed out — the clone was already right.** The desktop navbar holds exactly
logo, tabs, search, `Sign Up`, `Log In`; both auth controls are
`href="javascript:void(0)"`, hovering either opens nothing, and clicking
navigates. The clone's navbar matched node for node. What did differ is the
destination: the source carries the origin path forward as
`/signup?goto=%2F` and `/login?goto=%2Fgames%2Fyes-chef-cooking-bundle`, where
the clone went to a bare `/login`. Corrected, and the round trip now returns to
the originating page after sign-in, as the source's does.

**Signed in — the clone was wrong.** The authenticated captures show the source
swapping the Sign Up / Log In pair for a single `user-dropdown-container`
holding a `hb-user-circle-o` icon and a caret, with the account routes in a
click-to-open panel. It never prints the display name in the navbar. The clone
had been rendering the display name as a text button with an improvised panel.
Rebuilt against the captured markup: class list, attribute set, icon pair,
item order, labels, hrefs and the `js-navbar-logout` hook are the captured
ones, and the logged-in navbar no longer keeps the auth pair around hidden.

The reporter was comparing a browser still signed in to the source against a
signed-out clone, which is why the difference read as missing on the public
page; the underlying signed-in defect was real.

## Countdown timers: the capture instant is recoverable (2026-08-23)

The same review found the countdowns frozen. They resolve to a single instant:
subtracting each detailed timer's D:H:M:S from its bundle's `end_date` gives
**2026-08-20T22:36:58** for all nine tiles that render one, across three
different end dates. Since the whole clone is frozen at that instant, the
timers are now anchored to the remaining time the source itself rendered and
run forward from page load, rather than being recomputed against absolute end
dates — an absolute reading drifts a day per day and pins every tile that has
since expired at `00:00:00:00`, which is the state the reviewer saw.

The pill/red swap threshold is bounded but not fixed by the capture; see
`claim.inferred.countdown-swap-threshold`.
