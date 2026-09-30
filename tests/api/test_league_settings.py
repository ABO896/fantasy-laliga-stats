"""The premium toggles' HTTP surface. Two independent flags, written
together because the settings form submits them together.

The captain went on 2026-08-22 with the lineup cut: it doubles a player's
score, nothing in the app computes a score, so the armband recorded an
intention that was never read.
"""


def test_the_flags_start_off(client):
    body = client.get("/api/league-settings").json()
    assert body == {"premiumFormationsEnabled": False, "premiumBenchEnabled": False}


def test_the_captain_flag_is_gone(client):
    assert "premiumCaptainEnabled" not in client.get("/api/league-settings").json()


def test_turning_a_flag_on_persists_across_requests(client):
    client.put(
        "/api/league-settings",
        json={"premiumFormationsEnabled": False, "premiumBenchEnabled": True},
    )
    body = client.get("/api/league-settings").json()
    assert body["premiumBenchEnabled"] is True
    assert body["premiumFormationsEnabled"] is False


def test_the_put_returns_the_new_state_so_the_client_need_not_refetch(client):
    body = client.put(
        "/api/league-settings",
        json={"premiumFormationsEnabled": True, "premiumBenchEnabled": True},
    ).json()
    assert body == {"premiumFormationsEnabled": True, "premiumBenchEnabled": True}


def test_a_missing_flag_is_rejected_rather_than_defaulted(client):
    """Defaulting an absent flag to False would let a client that knows about
    one feature silently switch off another it has never heard of."""
    response = client.put("/api/league-settings", json={"premiumBenchEnabled": True})
    assert response.status_code == 422
