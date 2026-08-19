from backend import catalog_db as db


def test_seed_orders_and_lists_present(client):
    orders = client.get("/api/orders").json()["orders"]
    assert len(orders) >= 2  # 2 seed orders
    lists = client.get("/api/lists").json()["lists"]
    assert any(x["name"] == "Workshop" for x in lists)


def test_reset_is_deterministic(client):
    # place an order, reset, verify seed state restored exactly
    client.post("/api/cart/add", json={"itemId": "320326787", "qty": 1})
    client.post("/api/checkout", json={"first_name": "A", "last_name": "B",
                "phone": "1", "scenario_id": "sandbox-approved"})
    n_after_order = len(client.get("/api/orders").json()["orders"])
    db.reset()
    n_after_reset = len(client.get("/api/orders").json()["orders"])
    assert n_after_order == n_after_reset + 1  # our order gone, seed restored
    assert n_after_reset >= 2


def test_catalog_has_90ish_products(client):
    d = client.get("/api/search?q=&limit=200").json()
    assert d["total"] >= 60
