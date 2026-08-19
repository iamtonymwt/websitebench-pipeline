"""Account / session auth wiring (library LocalAuthStore seam).

The session cookie is ``__Host-...`` (Secure), so these use an https test
client to let the cookie round-trip; the cart tests stay on http because the
cart cookie is not Secure.
"""
import pytest
from fastapi.testclient import TestClient

import app as app_module
from backend import catalog_db

DEMO_EMAIL = "demo.shopper@example.test"
DEMO_PW = "HomeDepotDemo!2026"


@pytest.fixture()
def sclient():
    catalog_db.reset()
    with TestClient(app_module.app, base_url="https://testserver") as c:
        yield c
    catalog_db.reset()


def test_anonymous_session(sclient):
    d = sclient.get("/api/account").json()
    assert d["authenticated"] is False and d["account"] is None


def test_login_demo_account(sclient):
    d = sclient.post("/api/account/login",
                     json={"email": DEMO_EMAIL, "password": DEMO_PW}).json()
    assert d["authenticated"] is True
    assert d["account"]["display_name"] == "Jordan Reyes"
    assert d["account"]["email_normalized"] == DEMO_EMAIL


def test_session_persists_after_login(sclient):
    sclient.post("/api/account/login", json={"email": DEMO_EMAIL, "password": DEMO_PW})
    d = sclient.get("/api/account").json()
    assert d["authenticated"] is True
    assert d["account"]["display_name"] == "Jordan Reyes"


def test_wrong_password_rejected(sclient):
    r = sclient.post("/api/account/login",
                     json={"email": DEMO_EMAIL, "password": "WrongPass!2026"})
    assert r.status_code == 401
    assert sclient.get("/api/account").json()["authenticated"] is False


def test_unknown_email_rejected(sclient):
    r = sclient.post("/api/account/login",
                     json={"email": "nobody@example.test", "password": DEMO_PW})
    assert r.status_code == 401


def test_missing_fields_return_422(sclient):
    r = sclient.post("/api/account/login", json={"email": "", "password": ""})
    assert r.status_code == 422
    assert set(r.json()["errors"]) == {"email", "password"}


def test_logout_revokes_session(sclient):
    sclient.post("/api/account/login", json={"email": DEMO_EMAIL, "password": DEMO_PW})
    sclient.post("/api/account/logout")
    assert sclient.get("/api/account").json()["authenticated"] is False


def test_account_pages_serve_home_shell(sclient):
    for route in ("/myaccount/dashboard", "/myaccount/purchase-history",
                  "/list/view/summary"):
        resp = sclient.get(route)
        assert resp.status_code == 200
        assert "hd-app.js" in resp.text


def test_login_deterministic_after_reset(sclient):
    catalog_db.reset()  # account is reseeded deterministically, never dropped
    d = sclient.post("/api/account/login",
                     json={"email": DEMO_EMAIL, "password": DEMO_PW}).json()
    assert d["authenticated"] is True


def test_no_password_echoed_in_response(sclient):
    r = sclient.post("/api/account/login",
                     json={"email": DEMO_EMAIL, "password": DEMO_PW})
    assert DEMO_PW not in r.text  # never reflect the credential back


# --- registration (OTP via local outbox) ---------------------------------
def test_registration_flow_creates_account(sclient):
    start = sclient.post("/api/account/register/start", json={
        "email": "brand.new@example.test", "first_name": "Robin",
        "last_name": "Park", "password": "BrandNew!2026"})
    assert start.status_code == 200
    code = start.json()["sandbox_code"]
    assert code and len(code) == 6
    done = sclient.post("/api/account/register/complete", json={"code": code})
    assert done.status_code == 200 and done.json()["authenticated"] is True
    assert done.json()["account"]["display_name"] == "Robin Park"
    assert sclient.get("/api/account").json()["account"]["email_normalized"] == "brand.new@example.test"


def test_registration_duplicate_email_conflict(sclient):
    r = sclient.post("/api/account/register/start", json={
        "email": "demo.shopper@example.test", "first_name": "Dup",
        "last_name": "Licate", "password": "Another!2026"})
    assert r.status_code == 409 and r.json()["code"] == "conflict"


def test_registration_bad_code_rejected(sclient):
    sclient.post("/api/account/register/start", json={
        "email": "codey@example.test", "first_name": "Code", "last_name": "Y",
        "password": "GoodPass!2026"})
    r = sclient.post("/api/account/register/complete", json={"code": "000000"})
    assert r.status_code == 400 and r.json()["code"] == "bad_code"
    assert sclient.get("/api/account").json()["authenticated"] is False


def test_registration_missing_fields_422(sclient):
    r = sclient.post("/api/account/register/start", json={"email": "", "password": ""})
    assert r.status_code == 422 and "email" in r.json()["errors"]


# --- password reset (OTP via local outbox) -------------------------------
def test_password_reset_rotates_credentials(sclient):
    start = sclient.post("/api/account/password-reset/start",
                         json={"email": "demo.shopper@example.test"})
    assert start.status_code == 200
    code = start.json()["sandbox_code"]
    assert code and len(code) == 6
    done = sclient.post("/api/account/password-reset/complete",
                        json={"code": code, "new_password": "Rotated!2026"})
    assert done.status_code == 200 and done.json()["authenticated"] is True
    # old password no longer works, new one does (fresh client)
    with TestClient(app_module.app, base_url="https://testserver") as c2:
        assert c2.post("/api/account/login", json={
            "email": "demo.shopper@example.test", "password": DEMO_PW}).status_code == 401
        assert c2.post("/api/account/login", json={
            "email": "demo.shopper@example.test", "password": "Rotated!2026"}).json()["authenticated"] is True


def test_reset_restores_seed_password(sclient):
    # rotate the demo password, then a deterministic reset must restore the seed
    start = sclient.post("/api/account/password-reset/start",
                         json={"email": "demo.shopper@example.test"})
    sclient.post("/api/account/password-reset/complete",
                 json={"code": start.json()["sandbox_code"], "new_password": "Temp!2026"})
    catalog_db.reset()
    with TestClient(app_module.app, base_url="https://testserver") as c2:
        assert c2.post("/api/account/login", json={
            "email": "demo.shopper@example.test", "password": DEMO_PW}).json()["authenticated"] is True
        assert c2.post("/api/account/login", json={
            "email": "demo.shopper@example.test", "password": "Temp!2026"}).status_code == 401
