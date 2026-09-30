"""GET/PUT/DELETE /api/watchlist — DETAIL-04. Writes are idempotent and
return the whole list so the client can drop it straight into its cache."""

from datetime import UTC, datetime

from storage.models import Player


def _seed(session, player_id: int) -> None:
    now = datetime.now(UTC)
    session.add(
        Player(
            id=player_id,
            external_id=f"ext-{player_id}",
            name=f"Player {player_id}",
            team="Team",
            position="MED",
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()


def test_the_watchlist_starts_empty(client):
    response = client.get("/api/watchlist")
    assert response.status_code == 200
    assert response.json() == {"playerIds": []}


def test_put_adds_and_returns_the_list(session, client):
    _seed(session, 7)
    _seed(session, 9)
    assert client.put("/api/watchlist/9").json() == {"playerIds": [9]}
    assert client.put("/api/watchlist/7").json() == {"playerIds": [9, 7]}
    assert client.get("/api/watchlist").json() == {"playerIds": [9, 7]}


def test_put_is_idempotent(session, client):
    _seed(session, 7)
    client.put("/api/watchlist/7")
    response = client.put("/api/watchlist/7")
    assert response.status_code == 200
    assert response.json() == {"playerIds": [7]}


def test_put_for_an_unknown_player_is_a_404(client):
    assert client.put("/api/watchlist/999").status_code == 404
    assert client.get("/api/watchlist").json() == {"playerIds": []}


def test_delete_removes_and_is_idempotent(session, client):
    _seed(session, 7)
    client.put("/api/watchlist/7")
    assert client.delete("/api/watchlist/7").json() == {"playerIds": []}
    second = client.delete("/api/watchlist/7")
    assert second.status_code == 200
    assert second.json() == {"playerIds": []}
