"""Which browser origins may talk to the API.

The app is opened by hand at a URL the owner types, and `localhost:5173`
and `127.0.0.1:5173` are the same server but *different origins* to a
browser. Allowing only one of them produces the worst kind of failure: the
page loads perfectly and every request inside it is blocked, so the UI
reports the API as unreachable while the API is running and healthy.
"""

import pytest

ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173"]


@pytest.mark.parametrize("origin", ORIGINS)
def test_the_dev_server_origins_are_allowed(client, origin):
    response = client.get("/api/meta", headers={"Origin": origin})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


@pytest.mark.parametrize("origin", ORIGINS)
def test_a_preflight_from_either_origin_is_allowed(client, origin):
    """The squad page sends JSON, so its mutations preflight."""
    response = client.options(
        "/api/squad/players",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_an_unrelated_origin_is_still_refused(client):
    """Widening to both loopback spellings must not widen to the web."""
    response = client.get("/api/meta", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in response.headers
