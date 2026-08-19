def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json() == {"ok": True, "site_id": "home-depot"}


def test_home_renders_offline(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "The Home Depot" in r.text


def test_page_family_routes(client):
    for path in ["/", "/b/Tools/N-5yc1vZc1xy",
                 "/b/Tools-Power-Tools-Drills/N-5yc1vZc27f",
                 "/p/Milwaukee-M18-FUEL/320326787",
                 "/s/milwaukee%2018v%20cordless%20drill",
                 "/s/zzzz-no-match-websitebench", "/cart", "/checkout",
                 "/auth/view/signin", "/c/customer-service"]:
        assert client.get(path).status_code == 200, path


def test_unknown_route_is_branded_404(client):
    r = client.get("/this-page-does-not-exist-xyz")
    assert r.status_code == 404


def test_hd_app_injected(client):
    assert "/static/site/hd-app.js" in client.get("/").text
