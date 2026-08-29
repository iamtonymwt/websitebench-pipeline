"""Checkout through the local-sandbox seam (invariants
``payment-sandbox-only`` and ``checkout-math``)."""

import pytest

ANCHOR = "yes-chef-cooking-bundle"


def _purchase_count(db) -> int:
    return len(db.list_purchases(db.DEMO_OWNER)) + len(db.list_purchases(None))


def test_payment_key_guard(db) -> None:
    """Payment-shaped keys are rejected before any persistence; only opaque
    sandbox scenario ids are payment input."""

    for bad_key in (
        "card_number",
        "cardNumber",
        "cvv",
        "cvc",
        "pan",
        "expiry_month",
        "security-code",
        "payment_method",
        "stripe_token",
        "bank_account",
        "routing_number",
        "iban",
        "wallet_id",
    ):
        assert db.PAYMENT_KEY_RE.search(bad_key), bad_key
        with pytest.raises(db.PaymentFieldRejected):
            db.reject_payment_keys({bad_key: "4242424242424242"})

    # Benign business keys must never trip the guard.
    for good_key in (
        "scenario_id",
        "amount_minor",
        "gift_email",
        "allocations",
        "paypalgivingfund",
        "humblebundle",
        "discount_pct",
        "mode",
    ):
        assert not db.PAYMENT_KEY_RE.search(good_key), good_key
    db.reject_payment_keys({"scenario_id": "sandbox-approved", "amount_minor": 1500})

    # Nested payment-shaped keys inside splits are refused with no writes.
    db.cart_add("cart-guard", "bundle", ANCHOR, amount_minor=1500)
    before = _purchase_count(db)
    with pytest.raises(db.PaymentFieldRejected):
        db.place_order(
            "cart-guard",
            db.DEMO_OWNER,
            "sandbox-approved",
            splits={"mode": "custom", "allocations": {"card": 1500}},
        )
    assert _purchase_count(db) == before
    assert db.cart_view("cart-guard")["count"] == 1  # cart untouched


def test_declined_scenario_creates_no_order(db) -> None:
    """sandbox-declined raises the typed error and writes no business rows;
    the cart survives for a retry, which can then be approved."""

    db.cart_add("cart-declined", "bundle", ANCHOR, amount_minor=1500)
    before = len(db.list_purchases(db.DEMO_OWNER))

    with pytest.raises(db.PaymentDeclined):
        db.place_order("cart-declined", db.DEMO_OWNER, "sandbox-declined")
    assert len(db.list_purchases(db.DEMO_OWNER)) == before
    assert db.cart_view("cart-declined")["count"] == 1

    with pytest.raises(db.PaymentRetryable):
        db.place_order("cart-declined", db.DEMO_OWNER, "sandbox-retry")
    assert len(db.list_purchases(db.DEMO_OWNER)) == before
    assert db.cart_view("cart-declined")["count"] == 1

    # The same cart can then complete: retry-after-decline is supported.
    placed = db.place_order("cart-declined", db.DEMO_OWNER, "sandbox-approved")
    assert placed["placed"] is True
    assert len(db.list_purchases(db.DEMO_OWNER)) == before + 1
    assert db.cart_view("cart-declined")["count"] == 0


def test_totals_reflect_custom_price(db) -> None:
    """The pay-what-you-want amount IS the order amount: totals, charged
    amount, entitlements and custom split math all reflect it."""

    db.cart_add("cart-custom", "bundle", ANCHOR, amount_minor=1500)

    # A custom split that does not sum to the total is rejected, no writes.
    with pytest.raises(db.SplitInvalid):
        db.place_order(
            "cart-custom",
            db.DEMO_OWNER,
            "sandbox-approved",
            splits={"mode": "custom", "allocations": {"publisher": 100}},
        )
    assert db.cart_view("cart-custom")["count"] == 1

    placed = db.place_order(
        "cart-custom",
        db.DEMO_OWNER,
        "sandbox-approved",
        splits={
            "mode": "custom",
            "allocations": {
                "publisher": 900,
                "paypalgivingfund": 400,
                "humblebundle": 200,
            },
        },
    )
    assert placed["placed"] is True
    purchase = db.get_purchase(db.DEMO_OWNER, placed["order_no"])
    assert purchase["total_minor"] == 1500  # pre-tax subtotal: the split base
    # The buyer is charged the summary Total. Custom mode allocates 400 to the
    # charity party, so the taxable base is 1500 - 400 and the tax line 143.
    assert purchase["tax_minor"] == 143
    assert purchase["charity_minor"] == 400
    assert purchase["charged_minor"] == 1500 + 143
    assert purchase["grand_total_minor"] == purchase["charged_minor"]
    assert purchase["currency"] == "CAD"
    assert purchase["status"] == "Completed"
    assert purchase["items"][0]["kind"] == "bundle"
    assert purchase["items"][0]["amount_minor"] == 1500
    # $15 unlocks exactly the 7-item tier.
    assert len(purchase["keys"]) == 7
    assert purchase["splits"]["mode"] == "custom"
    assert purchase["splits"]["allocations"] == {
        "publisher": 900,
        "paypalgivingfund": 400,
        "humblebundle": 200,
    }
    assert sum(purchase["splits"]["allocations"].values()) == 1500
    # Frozen split shapes ride along for the review surface.
    parties = [p["class"] for p in purchase["splits"]["bundles"][ANCHOR]]
    assert parties == ["publisher", "paypalgivingfund", "humblebundle"]
    assert db.cart_view("cart-custom")["count"] == 0


def test_keys_are_sandbox_shaped_and_reveal_is_idempotent(db) -> None:
    db.cart_add("cart-keys", "bundle", ANCHOR, amount_minor=2219)
    placed = db.place_order("cart-keys", db.DEMO_OWNER, "sandbox-approved")
    order_no = placed["order_no"]
    purchase = db.get_purchase(db.DEMO_OWNER, order_no)
    assert len(purchase["keys"]) == 16
    assert all(k["key_code"] is None for k in purchase["keys"])  # unrevealed

    machine = purchase["keys"][0]["machine_name"]
    first = db.reveal_key(db.DEMO_OWNER, order_no, machine)
    second = db.reveal_key(db.DEMO_OWNER, order_no, machine)
    assert first == second
    parts = first.split("-")
    assert parts[0] == "SANDBOX" and len(parts) == 4
    assert all(len(p) == 4 for p in parts[1:])
    assert first == first.upper()

    refreshed = db.get_purchase(db.DEMO_OWNER, order_no)
    revealed = {k["machine_name"]: k for k in refreshed["keys"]}
    assert revealed[machine]["revealed"] is True
    assert revealed[machine]["key_code"] == first

    entries = db.library(db.DEMO_OWNER)
    assert any(e["machine_name"] == machine for e in entries)


def test_gift_delivery_stays_out_of_library(db) -> None:
    db.cart_add("cart-gift", "product", "bridge-constructor-portal")
    db.cart_add("cart-gift", "bundle", ANCHOR, amount_minor=971)
    placed = db.place_order(
        "cart-gift",
        db.DEMO_OWNER,
        "sandbox-approved",
        delivery_kind="gift",
        gift_email="friend@example.test",
    )
    purchase = db.get_purchase(db.DEMO_OWNER, placed["order_no"])
    assert purchase["delivery_kind"] == "gift"
    assert purchase["gift_email"] == "friend@example.test"
    # 971 unlocks 7 bundle items + 1 store product = 8 keys on the order,
    # but gift purchases grant the buyer no library entitlements.
    assert len(purchase["keys"]) == 8
    library_names = {e["order_no"] for e in db.library(db.DEMO_OWNER)}
    assert placed["order_no"] not in library_names


def test_custom_splits_must_sum_to_total(db) -> None:
    """Negative of checkout-math: custom allocations that do not sum to the
    charged amount are rejected and create no purchase."""

    import backend.catalog_db as db_mod

    cart = db_mod.get_or_create_cart("splits-negative-cart")
    db_mod.cart_add("splits-negative-cart", kind="bundle",
                    slug="yes-chef-cooking-bundle", amount_minor=1500)
    before = len(db_mod.list_purchases("splits-negative-owner"))
    try:
        db_mod.place_order(
            "splits-negative-cart", owner="splits-negative-owner",
            scenario_id="sandbox-approved",
            splits={"mode": "custom",
                    "allocations": {"publishers": 100, "charity": 100, "humble": 100}},
        )
        raised = False
    except (db_mod.SplitInvalid, ValueError):
        raised = True
    assert raised
    assert len(db_mod.list_purchases("splits-negative-owner")) == before
    assert cart is not None


def test_summary_math_reproduces_captured_walk(db) -> None:
    """checkout-math oracle: the Order Summary quadruple captured on the real
    authenticated review (walk tr-001, anchor bundle at the custom price
    CA$15.00) — Subtotal CA$15.00, HST CA$1.85, Total CA$16.85, charity
    CA$0.75 — is reproduced by the clone's own rate + split data."""

    oracle = db.TAX_ORACLE
    assert oracle == {
        "bundle_slug": ANCHOR,
        "split_mode": "default",
        "subtotal_minor": 1500,
        "charity_minor": 75,
        "tax_minor": 185,
        "grand_total_minor": 1685,
    }
    # The rate is applied to the non-charity remainder; a flat rate on the
    # whole subtotal would give 195, which is NOT what the source showed.
    assert db.TAX_RATE_BP == 1300
    assert db.TAX_LABEL == "HST"
    computed = db.order_totals(oracle["subtotal_minor"], oracle["charity_minor"])
    assert computed["tax_minor"] == oracle["tax_minor"]
    assert computed["grand_total_minor"] == oracle["grand_total_minor"]
    assert db.order_totals(1500, 0)["tax_minor"] == 195  # negative control

    # The review summary the frontend renders comes from the cart view, and it
    # agrees with the capture line for line.
    db.cart_add("cart-oracle", "bundle", ANCHOR, amount_minor=1500)
    view = db.cart_view("cart-oracle")
    assert view["subtotal_minor"] == 1500
    assert view["charity_minor"] == 75          # bundle's own 5% split share
    assert view["charity_name"] == "Farmlink"   # captured callout charity
    assert view["tax_label"] == "HST"
    assert view["tax_minor"] == 185
    assert view["grand_total_minor"] == 1685

    # The placed order and the confirmation carry the same numbers.
    placed = db.place_order(
        "cart-oracle", db.DEMO_OWNER, "sandbox-approved", processor="paypal"
    )
    purchase = db.get_purchase(db.DEMO_OWNER, placed["order_no"])
    assert purchase["subtotal_minor"] == 1500
    assert purchase["tax_minor"] == 185
    assert purchase["charity_minor"] == 75
    assert purchase["charity_name"] == "Farmlink"
    assert purchase["grand_total_minor"] == 1685
    assert purchase["charged_minor"] == 1685
    assert purchase["processor"] == "paypal"

    # Extra-to-charity moves the donation and with it the taxable base.
    db.cart_add("cart-extra", "bundle", ANCHOR, amount_minor=1500)
    extra = db.cart_view("cart-extra", split_mode="extra-charity")
    assert extra["charity_minor"] == 225                       # 15% of 1500
    assert extra["tax_minor"] == db.order_totals(1500, 225)["tax_minor"]
    assert extra["grand_total_minor"] == 1500 + extra["tax_minor"]


def test_gift_by_email_requires_a_recipient(db) -> None:
    """Negative: the gift-by-email branch is refused without a correctly
    formatted address, and writes nothing."""

    db.cart_add("cart-gift-email", "bundle", ANCHOR, amount_minor=1500)
    before = _purchase_count(db)
    for bad in (None, "", "   ", "not-an-email", "a@b@c.test", "a b@example.test"):
        with pytest.raises(db.GiftRecipientInvalid):
            db.place_order(
                "cart-gift-email",
                db.DEMO_OWNER,
                "sandbox-approved",
                gift_mode="email",
                gift_email=bad,
            )
    assert _purchase_count(db) == before
    assert db.cart_view("cart-gift-email")["count"] == 1

    placed = db.place_order(
        "cart-gift-email",
        db.DEMO_OWNER,
        "sandbox-approved",
        gift_mode="email",
        gift_email="friend@example.test",
        gift_anonymous=True,
    )
    purchase = db.get_purchase(db.DEMO_OWNER, placed["order_no"])
    assert purchase["gift_mode"] == "email"
    assert purchase["delivery_kind"] == "gift"
    assert purchase["gift_email"] == "friend@example.test"
    assert purchase["gift_anonymous"] is True


def test_gift_by_link_needs_no_recipient(db) -> None:
    """The 'Email Gift Link to Me' branch mails the buyer, so it requires no
    recipient address — and stores none."""

    db.cart_add("cart-gift-link", "bundle", ANCHOR, amount_minor=1500)
    placed = db.place_order(
        "cart-gift-link", db.DEMO_OWNER, "sandbox-approved", gift_mode="link"
    )
    purchase = db.get_purchase(db.DEMO_OWNER, placed["order_no"])
    assert purchase["gift_mode"] == "link"
    assert purchase["delivery_kind"] == "gift"
    assert purchase["gift_email"] is None
    # Gifts grant the buyer no library entitlements, link branch included.
    assert placed["order_no"] not in {e["order_no"] for e in db.library(db.DEMO_OWNER)}


def test_unknown_processor_is_rejected(db) -> None:
    """Negative of payment-sandbox-only: only the three captured
    ``processor-type`` choices are accepted, and none is an instrument."""

    assert db.PROCESSORS == ("paypal", "card", "alipay")
    db.cart_add("cart-processor", "bundle", ANCHOR, amount_minor=1500)
    before = _purchase_count(db)
    for bad in ("stripe", "bitcoin", "", "PAYPAL", None):
        with pytest.raises(db.ProcessorInvalid):
            db.place_order(
                "cart-processor", db.DEMO_OWNER, "sandbox-approved", processor=bad
            )
    assert _purchase_count(db) == before
    assert db.cart_view("cart-processor")["count"] == 1
    for good in db.PROCESSORS:
        assert db.PROCESSOR_SCENARIOS[good] == "sandbox-approved"


def test_leaderboard_name_round_trips(db) -> None:
    """The leaderboard opt-in name is carried into the order record."""

    db.cart_add("cart-leaderboard", "bundle", ANCHOR, amount_minor=1500)
    placed = db.place_order(
        "cart-leaderboard",
        db.DEMO_OWNER,
        "sandbox-approved",
        leaderboard_name="  Riley C  ",
    )
    purchase = db.get_purchase(db.DEMO_OWNER, placed["order_no"])
    assert purchase["leaderboard_name"] == "Riley C"

    # Opting out stores nothing, and the source's 70-char cap is honoured.
    db.cart_add("cart-leaderboard-2", "bundle", ANCHOR, amount_minor=1500)
    plain = db.place_order("cart-leaderboard-2", db.DEMO_OWNER, "sandbox-approved")
    assert db.get_purchase(db.DEMO_OWNER, plain["order_no"])["leaderboard_name"] is None
    db.cart_add("cart-leaderboard-3", "bundle", ANCHOR, amount_minor=1500)
    long_name = db.place_order(
        "cart-leaderboard-3",
        db.DEMO_OWNER,
        "sandbox-approved",
        leaderboard_name="x" * 200,
    )
    stored = db.get_purchase(db.DEMO_OWNER, long_name["order_no"])["leaderboard_name"]
    assert stored == "x" * db.LEADERBOARD_NAME_MAX


def test_api_checkout_rejects_bad_gift_email_and_processor(db) -> None:
    """App layer: the review's new fields ride through /api/checkout, an
    invalid gift email and an unknown processor are both 422."""

    pytest.importorskip("fastapi.testclient", reason="app layer pending")
    app_module = pytest.importorskip("app", reason="app layer pending")
    from fastapi.testclient import TestClient

    client = TestClient(app_module.app, base_url="https://testserver")
    login = client.post(
        "/api/account/login",
        json={"email": db.DEMO_EMAIL, "password": db.DEMO_PASSWORD},
    )
    if login.status_code == 404:
        pytest.skip("app layer pending: login API not wired yet")
    assert login.status_code == 200, login.text
    added = client.post(
        "/api/cart/add",
        json={"kind": "bundle", "slug": ANCHOR, "amount_minor": 1500},
    )
    assert added.status_code == 200, added.text

    bad_gift = client.post(
        "/api/checkout",
        json={
            "scenario_id": "sandbox-approved",
            "processor": "card",
            "gift": {"mode": "email", "recipient": "nope"},
        },
    )
    assert bad_gift.status_code == 422, bad_gift.text
    assert bad_gift.json()["error"] == "gift_email_invalid"

    bad_processor = client.post(
        "/api/checkout",
        json={"scenario_id": "sandbox-approved", "processor": "stripe"},
    )
    assert bad_processor.status_code == 422, bad_processor.text
    assert bad_processor.json()["error"] == "unknown_processor"

    ok = client.post(
        "/api/checkout",
        json={
            "scenario_id": "sandbox-approved",
            "processor": "alipay",
            "gift": {"mode": "link", "anonymous": True},
            "leaderboard_name": "Riley C",
            "splits": {"mode": "default"},
        },
    )
    assert ok.status_code == 200, ok.text
    purchase = ok.json()["purchase"]
    assert purchase["processor"] == "alipay"
    assert purchase["gift_mode"] == "link"
    assert purchase["gift_email"] is None
    assert purchase["leaderboard_name"] == "Riley C"
    assert purchase["subtotal_minor"] == 1500
    assert purchase["tax_minor"] == 185
    assert purchase["charity_minor"] == 75
    assert purchase["grand_total_minor"] == 1685
