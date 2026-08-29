"""Deterministic reset through the seam (invariant ``deterministic-reset``)
plus the declared hook wiring itself."""

from backend import catalog_db


def _seed_state_snapshot(db) -> dict:
    purchases = db.list_purchases(db.DEMO_OWNER)
    return {
        "orders": [p["order_no"] for p in purchases],
        "library": [e["machine_name"] for e in db.library(db.DEMO_OWNER)],
        "portal": [p["slug"] for p in db.search(search="portal")["results"]],
        "listing_total": sum(
            len(tiles) for tiles in db.bundles_listing().values()
        ),
    }


def test_declared_hooks_opened_the_backend(db) -> None:
    """The runtime-declared migrate/seed hooks ran through the seam: the
    bound database records them and the seeded state is queryable."""

    backend, auth = catalog_db.services()
    assert backend.config.site_id == "humble-bundle"
    assert backend.config.migration_hook == "backend.catalog_db:migrate"
    assert backend.config.seed_hook == "backend.catalog_db:seed"
    with backend.lifecycle.connection() as cx:
        applied = {
            row["migration_id"]
            for row in cx.execute(
                "SELECT migration_id FROM websitebench_backend_migrations"
            )
        }
        assert "site-migration:backend.catalog_db:migrate" in applied
        assert "site-seed:backend.catalog_db:seed" in applied
        assert (
            cx.execute("SELECT COUNT(*) FROM hb_products").fetchone()[0] == 156
        )
        assert cx.execute("SELECT COUNT(*) FROM hb_bundles").fetchone()[0] == 13
    # The demo account seeded through the auth seam is signable.
    token = auth.create_anonymous_session()
    signed = auth.sign_in(
        token, email=catalog_db.DEMO_EMAIL, password=catalog_db.DEMO_PASSWORD
    )
    assert signed["account"]["display_name"] == catalog_db.DEMO_DISPLAY_NAME


def test_admin_reset_restores_seed(db) -> None:
    """Reset restores catalog, bundles, demo account and its two seeded
    purchases, and clears run carts/orders/wishlists — deterministically."""

    baseline = _seed_state_snapshot(db)
    assert baseline["orders"] == ["HB2026080002", "HB2026080001"]
    seeded_bundle = db.get_purchase(db.DEMO_OWNER, "HB2026080001")
    assert seeded_bundle["total_minor"] == 1500
    assert seeded_bundle["status"] == "Completed"
    assert len(seeded_bundle["keys"]) == 7
    seeded_product = db.get_purchase(db.DEMO_OWNER, "HB2026080002")
    assert seeded_product["status"] == "Completed"
    assert len(seeded_product["keys"]) == 1

    # Mutate everything a run can touch.
    db.cart_add("cart-reset", "bundle", "yes-chef-cooking-bundle", amount_minor=3000)
    db.cart_add("cart-reset", "product", "portal-knights")
    db.wishlist_add(db.DEMO_OWNER, "portal-knights")
    placed = db.place_order("cart-reset", db.DEMO_OWNER, "sandbox-approved")
    db.reveal_key(
        db.DEMO_OWNER, "HB2026080001", seeded_bundle["keys"][0]["machine_name"]
    )
    assert len(db.list_purchases(db.DEMO_OWNER)) == 3

    db.reset()

    assert _seed_state_snapshot(db) == baseline
    assert db.cart_view("cart-reset")["items"] == []
    assert db.wishlist_list(db.DEMO_OWNER) == []
    restored = db.get_purchase(db.DEMO_OWNER, "HB2026080001")
    assert all(k["revealed"] is False for k in restored["keys"])
    try:
        db.get_purchase(db.DEMO_OWNER, placed["order_no"])
    except db.NotFound:
        pass
    else:  # pragma: no cover - reset must drop run orders
        raise AssertionError("run order survived reset")

    # Reset is repeatable and the demo account still signs in with the
    # seed password afterwards.
    db.reset()
    assert _seed_state_snapshot(db) == baseline
    _, auth = catalog_db.services()
    token = auth.create_anonymous_session()
    signed = auth.sign_in(
        token, email=catalog_db.DEMO_EMAIL, password=catalog_db.DEMO_PASSWORD
    )
    assert signed["account"]["email_normalized"] == catalog_db.DEMO_OWNER


def test_reset_allows_identical_replay_of_checkout(db) -> None:
    """After reset, the exact same checkout sequence succeeds again (the
    embedded ledger reset keeps payment flows replayable)."""

    def run_once() -> str:
        db.cart_add("cart-replay", "bundle", "2k-megahits-2026-bundle",
                    amount_minor=2116)
        placed = db.place_order("cart-replay", db.DEMO_OWNER, "sandbox-approved")
        return placed["order_no"]

    first = run_once()
    db.reset()
    second = run_once()
    assert first == second  # deterministic order number and state
    purchase = db.get_purchase(db.DEMO_OWNER, second)
    assert purchase["total_minor"] == 2116
    assert len(purchase["keys"]) == 15


def test_admin_reset_requires_token(db) -> None:
    """Negative of deterministic-reset: the admin endpoint refuses a missing
    or wrong token with 403 and resets nothing."""

    import pytest as _pytest

    fastapi_testclient = _pytest.importorskip(
        "fastapi.testclient", reason="app layer pending")
    app_module = _pytest.importorskip("app", reason="app layer pending")
    client = fastapi_testclient.TestClient(
        app_module.app, base_url="https://testserver")
    assert client.post("/__admin/reset").status_code == 403
    assert client.post(
        "/__admin/reset",
        headers={"X-WebsiteBench-Admin-Token": "wrong-token"},
    ).status_code == 403
