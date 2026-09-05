"""Smoke tests: the app starts, answers, and reports itself ready."""


def test_health_returns_exactly_status_ok(client):
    """The deployment ABI specifies this body exactly.

    It used to also report site_id, frozen route count and catalogue counts.
    Those are a trace of this particular build: a candidate reconstructing the
    site would not emit them, and this is the one response the harness compares
    literally.
    """
    response = client.get("/__websitebench/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_home_answers(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "<html" in response.text.lower()


def test_unknown_route_is_a_404(client):
    assert client.get("/no-such-page-here").status_code == 404
