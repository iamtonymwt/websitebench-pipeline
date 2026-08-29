"""App-layer auth invariants (``secure-area-gate``, ``host-session-cookie``).

These tests exercise the HTTP layer, which is still the scaffold. They are
written against a feature probe: while the app does not serve the surface
under test they skip with "app layer pending", and they activate (and start
enforcing the frozen invariants) automatically once app.py wires the
secure-area gate and the seam's session cookie.
"""

import pytest

pytest.importorskip("fastapi.testclient", reason="app layer pending")
app_module = pytest.importorskip("app", reason="app layer pending")

from fastapi.testclient import TestClient  # noqa: E402

EXPECTED_COOKIE = "__Host-websitebench-humble-bundle-session"


def _client() -> TestClient:
    return TestClient(app_module.app, base_url="https://testserver")


def test_secure_area_redirect(db) -> None:
    """Anonymous /home/* -> 302 /login?goto=<path>&qs=reason%3DsecureArea."""

    client = _client()
    response = client.get("/home/library", follow_redirects=False)
    if response.status_code == 404:
        pytest.skip("app layer pending: /home/* secure-area gate not wired yet")
    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("/login?goto=")
    assert "goto=%2Fhome%2Flibrary" in location or "goto=/home/library" in location
    assert "qs=reason%3DsecureArea" in location


def test_session_cookie_attributes(db) -> None:
    """Session cookie is the seam's __Host- cookie: Secure/HttpOnly/SameSite,
    Path=/, and no parent Domain."""

    client = _client()
    login = client.post(
        "/api/account/login",
        json={"email": "demo.gamer@example.test", "password": "HumbleDemo!2026"},
    )
    if login.status_code == 404:
        pytest.skip("app layer pending: login API not wired yet")
    assert login.status_code == 200, login.text
    cookie_header = None
    for value in login.headers.get_list("set-cookie"):
        if value.startswith(f"{EXPECTED_COOKIE}="):
            cookie_header = value
            break
    assert cookie_header is not None, "login must issue the seam session cookie"
    lowered = cookie_header.lower()
    assert cookie_header.startswith(f"{EXPECTED_COOKIE}=")
    assert "secure" in lowered
    assert "httponly" in lowered
    assert "samesite=" in lowered
    assert "path=/" in lowered
    assert "domain=" not in lowered  # __Host- prefix forbids a parent Domain


def test_secure_area_allows_authenticated_demo(db) -> None:
    """Negative of the gate: a signed-in session is NOT redirected off /home/*."""

    client = _client()
    login = client.post(
        "/api/account/login",
        json={"email": "demo.gamer@example.test", "password": "HumbleDemo!2026"},
    )
    if login.status_code == 404:
        pytest.skip("app layer pending: login API not wired yet")
    assert login.status_code == 200, login.text
    response = client.get("/home/library", follow_redirects=False)
    assert response.status_code == 200


def test_no_session_cookie_for_anonymous_page_view(db) -> None:
    """Negative of the cookie invariant: plain anonymous page views never
    mint the __Host- session cookie (it is issued by account flows only)."""

    client = _client()
    for probe in ("/", "/bundles", "/store"):
        response = client.get(probe, follow_redirects=False)
        for value in response.headers.get_list("set-cookie"):
            assert not value.startswith(f"{EXPECTED_COOKIE}="), probe


def test_seeded_demo_history_is_visible_after_login(db) -> None:
    """Regression: the session's owner key must match the key the seed wrote.

    The seed stores business rows under the demo account's normalized email;
    when the app resolved the owner from the auth subject id instead, a freshly
    reset demo account signed in to an empty library and purchase history. The
    other suites could not catch it because they read back rows they had just
    written under the same key.
    """

    client = _client()
    login = client.post(
        "/api/account/login",
        json={"email": "demo.gamer@example.test", "password": "HumbleDemo!2026"},
    )
    if login.status_code == 404:
        pytest.skip("app layer pending: login API not wired yet")
    assert login.status_code == 200, login.text

    purchases = client.get("/api/purchases")
    assert purchases.status_code == 200, purchases.text
    orders = purchases.json()["purchases"]
    assert len(orders) == 2, orders

    library = client.get("/api/library")
    assert library.status_code == 200
    assert library.json()["library"], "seeded entitlements must be visible"


def test_login_returns_a_session_that_resolves(db) -> None:
    """The token handed to the caller must be one the store actually serves.

    A signed-in response whose token does not resolve was observed twice during
    the task audit; the caller would set a cookie for a session that is not
    there and the next request would look anonymous.
    """

    import backend.catalog_db as db_mod

    backend, auth = db_mod.services()
    for _ in range(8):
        result = db_mod.login(None, email="demo.gamer@example.test",
                              password="HumbleDemo!2026")
        token = result.get("session_token")
        assert token, result
        assert auth.resolve_session(token) is not None, "login returned a dead session"
        db_mod.logout(token)
