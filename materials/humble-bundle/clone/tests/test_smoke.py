from fastapi.testclient import TestClient

from app import app


client = TestClient(app)


def test_healthz() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "site_id": "humble-bundle"}


def test_home() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "websitebench-frozen" in response.text
    assert "Humble Bundle" in response.text
    assert "Content-Security-Policy" in response.headers


def test_all_frozen_routes() -> None:
    routes = [
        "/", "/bundles", "/games", "/books", "/software",
        "/games/yes-chef-cooking-bundle", "/games/2k-megahits-2026-bundle",
        "/store", "/store/search", "/store/satisfactory", "/membership",
        "/login", "/signup", "/about", "/charities", "/terms", "/privacy",
        "/legal", "/cookie-policy", "/accessibility", "/support",
        "/support/categories/200166394", "/support/articles/52764568066971",
    ]
    for route in routes:
        response = client.get(route)
        assert response.status_code == 200, route
        assert "websitebench-frozen" in response.text, route


def test_unknown_route() -> None:
    assert client.get("/not-in-scope").status_code == 404


def test_unknown_route_is_branded_404() -> None:
    response = client.get("/this-page-does-not-exist-websitebench")
    assert response.status_code == 404
    assert "CANNOT BE FOUND" in response.text.upper()


def test_out_of_subset_bundle_slugs_404() -> None:
    # Books/software bundle detail is outside the frozen subset; the source
    # 404s expired bundles, so the branded 404 is the truthful behavior.
    for route in ("/books/some-books-bundle", "/software/some-software-bundle"):
        response = client.get(route)
        assert response.status_code == 404
        assert "CANNOT BE FOUND" in response.text.upper()


def test_seeded_game_bundle_serves_template() -> None:
    listing = client.get("/api/bundles").json()
    games = listing.get("games") or []
    assert games, "seed must carry the games listing"
    slugs = [tile.get("slug") for tile in games]
    for slug in slugs:
        if slug in ("yes-chef-cooking-bundle", "2k-megahits-2026-bundle"):
            continue
        response = client.get(f"/games/{slug}")
        assert response.status_code == 200, slug
        break
