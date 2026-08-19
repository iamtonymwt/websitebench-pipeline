def test_search_returns_milwaukee_results(client):
    d = client.get("/api/search?q=milwaukee+18v+cordless+drill").json()
    assert d["total"] > 10
    assert all("milwaukee" in (p["brand"] or "").lower() for p in d["products"][:5])


def test_search_top_rated_sort(client):
    # Top Rated is review-volume weighted (Bayesian, m=50, c=4.6) — raw-rating
    # order would let a 8-review 4.8x item outrank the frozen 3981-review anchor.
    d = client.get("/api/search?q=milwaukee+18v+cordless+drill&sort=top_rated").json()
    m, c = 50.0, 4.6
    scores = [((p["rating"] or 0) * (p["reviews"] or 0) + c * m)
              / ((p["reviews"] or 0) + m) for p in d["products"]]
    assert scores == sorted(scores, reverse=True)


def test_anchor_product_detail(client):
    p = client.get("/api/products/320326787").json()
    assert p["model"] == "3697-22" and p["price"] == 399.0
    assert p["rating"] == 4.7664 and p["reviews"] == 3981


def test_no_results_route(client):
    assert client.get("/s/zzzz-no-match-websitebench").status_code == 200


def test_535_add_to_cart_and_totals(client):
    r = client.post("/api/cart/add", json={"itemId": "320326787", "qty": 1}).json()
    assert r["ok"] and r["cart"]["count"] == 1
    assert r["cart"]["subtotal"] == 399.0
    assert r["cart"]["tax"] == 31.92
    assert r["cart"]["total"] == 430.92
    assert r["cart"]["store"]["name"] == "Niagara Falls"


def test_cart_qty_limit_three(client):
    client.post("/api/cart/add", json={"itemId": "320326787", "qty": 5})
    c = client.get("/api/cart").json()
    assert c["items"][0]["qty"] == 3  # source "Limit 3 per order"


def test_535_checkout_approved_creates_order(client):
    client.post("/api/cart/add", json={"itemId": "320326787", "qty": 1})
    r = client.post("/api/checkout", json={
        "first_name": "Alex", "last_name": "Winters", "phone": "7165550142",
        "scenario_id": "sandbox-approved"}).json()
    assert r["placed"] is True
    o = r["order"]
    assert o["total"] == 430.92
    assert o["items"][0]["model"] == "3697-22"
    assert o["pickup_person"]["first_name"] == "Alex"
    assert o["store"]["name"] == "Niagara Falls"


def test_checkout_declined_then_retry(client):
    client.post("/api/cart/add", json={"itemId": "320326787", "qty": 1})
    d = client.post("/api/checkout", json={
        "first_name": "A", "last_name": "B", "phone": "7160000000",
        "scenario_id": "sandbox-declined"}).json()
    assert d["placed"] is False
    r = client.post("/api/checkout", json={
        "first_name": "A", "last_name": "B", "phone": "7160000000",
        "scenario_id": "sandbox-approved"}).json()
    assert r["placed"] is True


def test_checkout_requires_pickup_person(client):
    client.post("/api/cart/add", json={"itemId": "320326787", "qty": 1})
    r = client.post("/api/checkout", json={
        "first_name": "", "last_name": "", "phone": "",
        "scenario_id": "sandbox-approved"})
    assert r.status_code == 400


def test_checkout_rejects_payment_fields(client):
    client.post("/api/cart/add", json={"itemId": "320326787", "qty": 1})
    r = client.post("/api/checkout", json={
        "first_name": "A", "last_name": "B", "phone": "1",
        "card_number": "4111111111111111", "scenario_id": "sandbox-approved"})
    assert r.status_code == 400


def test_empty_cart_checkout_fails(client):
    r = client.post("/api/checkout", json={
        "first_name": "A", "last_name": "B", "phone": "1",
        "scenario_id": "sandbox-approved"})
    assert r.status_code == 400


def test_add_to_cart_respects_quantity(client):
    r = client.post("/api/cart/add", json={"itemId": "320326787", "qty": 2}).json()
    assert r["ok"] and r["cart"]["items"][0]["qty"] == 2


def test_save_to_list_creates_and_is_idempotent(client):
    r1 = client.post("/api/lists/add", json={"itemId": "320326787"}).json()
    assert r1["ok"] and r1["added"] is True and r1["list"] == "My List"
    r2 = client.post("/api/lists/add", json={"itemId": "320326787"}).json()
    assert r2["added"] is False and r2["count"] == 1  # UNIQUE(list,item)
    lists = client.get("/api/lists").json()["lists"]
    assert any(x["name"] == "My List" for x in lists)


def test_save_to_list_unknown_item_400(client):
    assert client.post("/api/lists/add", json={"itemId": "000000"}).status_code == 400


def test_save_to_list_named_list(client):
    r = client.post("/api/lists/add", json={"itemId": "320326787", "list": "Garage Reno"}).json()
    assert r["list"] == "Garage Reno" and r["added"] is True


def test_search_brand_and_price_filters(client):
    d = client.get("/api/search?q=drill&price_max=200").json()
    assert d["total"] >= 1 and all(p["price"] <= 200 for p in d["products"])
    assert "brands" in d["facets"] and d["facets"]["price_max"] >= d["facets"]["price_min"]
    d2 = client.get("/api/search?q=drill&brands=DEWALT").json()
    assert all(p["brand"] == "DEWALT" for p in d2["products"])


def test_related_products_same_category(client):
    d = client.get("/api/products/320326787/related").json()
    assert d["category"] == "Power Tool Combo Kits"
    assert len(d["products"]) >= 2
    assert all(p["itemId"] != "320326787" for p in d["products"])


def test_stores_list_and_change(client):
    stores = client.get("/api/stores").json()["stores"]
    assert {s["id"] for s in stores} >= {"1287", "1201", "3812"}
    r = client.post("/api/cart/store", json={"store_id": "1201"}).json()
    assert r["cart"]["store"]["id"] == "1201"
    assert client.post("/api/cart/store", json={"store_id": "9999"}).status_code == 400


def test_delivery_checkout_sets_fulfillment(client):
    client.post("/api/cart/add", json={"itemId": "320326787", "qty": 1})
    r = client.post("/api/checkout", json={
        "first_name": "Dana", "last_name": "Lee", "phone": "7165550111",
        "scenario_id": "sandbox-approved", "fulfillment": "delivery"}).json()
    assert r["placed"] is True
    assert r["order"]["fulfillment"] == "delivery" and r["order"]["status"] == "Ordered"


def test_order_cancel_return_reorder(client):
    # seed order WD12345678 is Ready for Pickup -> cancellable
    assert client.post("/api/order/WD12345678/cancel").json()["order"]["status"] == "Cancelled"
    assert client.post("/api/order/WD12345678/cancel").status_code == 409  # already cancelled
    # WD12340001 is Completed -> returnable
    assert client.post("/api/order/WD12340001/return").json()["order"]["status"] == "Return Requested"
    assert client.post("/api/order/WD12345678/return").status_code == 409  # not completed
    ro = client.post("/api/order/WD12340001/reorder").json()
    assert ro["ok"] and ro["cart"]["count"] >= 1
    assert client.post("/api/order/NOPE/cancel").status_code == 404


def test_giftcard_check_valid_and_invalid(client):
    g = client.get("/api/giftcard/check", params={"code": "sandbox-gift-25"}).json()
    assert g["valid"] is True and g["code"] == "SANDBOX-GIFT-25" and g["amount"] == 25.0
    bad = client.get("/api/giftcard/check", params={"code": "NOPE-123"}).json()
    assert bad["valid"] is False


def test_checkout_with_gift_card_reduces_charge_not_total(client):
    client.post("/api/cart/add", json={"itemId": "320326787", "qty": 1})
    r = client.post("/api/checkout", json={
        "first_name": "Alex", "last_name": "Winters", "phone": "7165550142",
        "scenario_id": "sandbox-approved", "gift_code": "SANDBOX-GIFT-25"}).json()
    assert r["placed"] is True
    o = r["order"]
    assert o["total"] == 430.92          # order total unchanged (gift = tender)
    assert o["gift"] == 25.0
    assert o["charged"] == 405.92        # amount that went through the sandbox


def test_checkout_invalid_gift_card_is_400(client):
    client.post("/api/cart/add", json={"itemId": "320326787", "qty": 1})
    r = client.post("/api/checkout", json={
        "first_name": "Alex", "last_name": "Winters", "phone": "7165550142",
        "scenario_id": "sandbox-approved", "gift_code": "NOT-A-CARD"})
    assert r.status_code == 400
    assert "gift" in r.json()["error"].lower()


def test_top_rated_puts_frozen_anchor_first(client):
    # Frozen source-walk oracle: for the 535 query the highest-rated SKU is
    # 3697-22 (4.7664 / 3981 reviews). Top Rated must weight by review volume
    # so a low-review 4.8x item cannot displace it.
    r = client.get("/api/search", params={
        "q": "milwaukee 18v cordless drill", "sort": "top_rated", "limit": 5}).json()
    assert r["products"][0]["itemId"] == "320326787"
    assert r["products"][0]["price"] == 399.0


def test_default_sort_matches_official_captured_order(client):
    # Default "Top Sellers" preserves the officially captured DOM order.
    r = client.get("/api/search", params={
        "q": "milwaukee 18v cordless drill", "sort": "default", "limit": 3}).json()
    assert [p["itemId"] for p in r["products"]] == [
        "325479354", "100650378", "204632932"]
