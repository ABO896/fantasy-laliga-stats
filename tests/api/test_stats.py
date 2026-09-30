"""GET /api/stats/* — league-wide read-models over PlayerGameweekPoints and
PlayerSeasonStats (STATS-01…04). No new scraping, no new table."""

from datetime import UTC, date, datetime

from storage.models import Player, PlayerGameweekPoints, PlayerSnapshot, ScrapeRun


def _player(session, slug, name, team="Team A", position="DEL"):
    now = datetime.now(UTC)
    p = Player(
        external_id=slug, name=name, team=team, position=position, created_at=now, updated_at=now
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def _run(session):
    r = ScrapeRun(started_at=datetime.now(UTC), status="success")
    session.add(r)
    session.commit()
    session.refresh(r)
    return r


def _gw(season_year, week, player_id, points, run_id, is_provisional=False):
    return PlayerGameweekPoints(
        season_year=season_year, week=week, player_id=player_id, points=points,
        is_provisional=is_provisional, scrape_run_id=run_id,
    )


def test_seasons_lists_distinct_seasons_and_week_ranges(session, client):
    p = _player(session, "p1", "Player One")
    run = _run(session)
    session.add_all([_gw(2025, 10, p.id, 5, run.id), _gw(2026, 3, p.id, 7, run.id)])
    session.commit()

    body = client.get("/api/stats/seasons").json()

    assert body["seasons"] == [2026, 2025]
    assert body["seasonWeekRanges"] == {"2025": 10, "2026": 3}


def test_seasons_is_empty_with_no_data(session, client):
    body = client.get("/api/stats/seasons").json()
    assert body == {"seasons": [], "seasonWeekRanges": {}}


def test_scores_404s_for_a_season_with_no_data_at_all(client):
    assert client.get("/api/stats/scores?season=2099&week=1").status_code == 404


def test_scores_200s_with_empty_lists_for_an_unplayed_week(session, client):
    p = _player(session, "p1", "Player One")
    run = _run(session)
    session.add(_gw(2026, 1, p.id, 5, run.id))
    session.commit()

    resp = client.get("/api/stats/scores?season=2026&week=99")

    assert resp.status_code == 200
    body = resp.json()
    assert body["scores"] == []
    assert body["teams"] == []
    assert len(body["tiers"]) == 5
    assert all(t["count"] == 0 for t in body["tiers"])


def test_scores_buckets_tiers_at_every_boundary(session, client):
    run = _run(session)
    points_by_slug = {
        "neg": -3, "zero": 0, "one": 1, "three": 3, "four": 4,
        "six": 6, "seven": 7, "nine": 9, "ten": 10, "eleven": 11,
    }
    for slug, points in points_by_slug.items():
        p = _player(session, slug, slug)
        session.add(_gw(2026, 1, p.id, points, run.id))
    session.commit()

    resp = client.get("/api/stats/scores?season=2026&week=1")
    tiers = {t["label"]: t["count"] for t in resp.json()["tiers"]}

    assert tiers == {"≤0": 2, "1–3": 2, "4–6": 2, "7–9": 2, "10+": 2}


def test_scores_is_provisional_reflects_the_stored_flag(session, client):
    p = _player(session, "p1", "Player One")
    run = _run(session)
    session.add(_gw(2026, 1, p.id, 5, run.id, is_provisional=True))
    session.commit()

    assert client.get("/api/stats/scores?season=2026&week=1").json()["isProvisional"] is True


def test_scores_is_provisional_is_true_if_any_row_is_provisional_even_the_top_scorer_not(
    session, client
):
    """Provisionality is a property of the whole jornada, not of whichever
    player happens to score the most points that week. A non-provisional
    top scorer must not mask a still-provisional row further down."""
    p_top = _player(session, "top", "Top Scorer")
    p_provisional = _player(session, "prov", "Provisional Player")
    run = _run(session)
    session.add(_gw(2026, 1, p_top.id, 10, run.id, is_provisional=False))
    session.add(_gw(2026, 1, p_provisional.id, 1, run.id, is_provisional=True))
    session.commit()

    assert client.get("/api/stats/scores?season=2026&week=1").json()["isProvisional"] is True


def test_scores_carries_the_per_player_rows_and_team_table(session, client):
    p = _player(session, "p1", "Player One", team="Team A", position="DEL")
    run = _run(session)
    session.add(_gw(2026, 1, p.id, 8, run.id))
    session.commit()

    body = client.get("/api/stats/scores?season=2026&week=1").json()

    assert body["scores"] == [
        {
            "playerId": p.id,
            "name": "Player One",
            "team": "Team A",
            "position": "DEL",
            "points": 8,
            "marketValue": None,
            "pricePerPoint": None,
        }
    ]
    assert body["teams"] == [
        {"team": "Team A", "totalPoints": 8, "playerCount": 1, "averagePoints": 8.0}
    ]


def test_scores_carries_market_value_and_price_per_point_from_the_latest_snapshot(session, client):
    p = _player(session, "p1", "Player One")
    run = _run(session)
    session.add(_gw(2026, 1, p.id, 8, run.id))
    session.add(
        PlayerSnapshot(
            as_of=date(2026, 9, 1),
            player_id=p.id,
            market_value=2_000_000,
            points=10,
            price_per_point=200_000.0,
            availability_status="available",
            raw_fields="{}",
            scrape_run_id=run.id,
        )
    )
    session.commit()

    score = client.get("/api/stats/scores?season=2026&week=1").json()["scores"][0]

    assert (score["marketValue"], score["pricePerPoint"]) == (2_000_000, 200_000.0)


def test_streaks_404s_for_an_unknown_season(client):
    assert client.get("/api/stats/streaks?season=2099").status_code == 404


def test_streaks_defaults_end_week_to_the_latest_and_window_to_5(session, client):
    p = _player(session, "p1", "Player One")
    run = _run(session)
    session.add_all([_gw(2026, w, p.id, 1, run.id) for w in range(1, 4)])
    session.commit()

    body = client.get("/api/stats/streaks?season=2026").json()

    assert body["endWeek"] == 3
    assert body["window"] == 3  # clamped: only 3 weeks exist


def test_streaks_clamps_window_to_the_seasons_available_weeks(session, client):
    p = _player(session, "p1", "Player One")
    run = _run(session)
    session.add(_gw(2026, 1, p.id, 5, run.id))
    session.commit()

    body = client.get("/api/stats/streaks?season=2026&window=99").json()

    assert body["window"] == 1


def test_streaks_carries_weeks_counted_per_player(session, client):
    p = _player(session, "p1", "Player One", team="Team A", position="DEL")
    run = _run(session)
    session.add(_gw(2026, 1, p.id, 5, run.id))
    session.commit()

    body = client.get("/api/stats/streaks?season=2026&end_week=1&window=5").json()

    assert body["players"] == [
        {
            "playerId": p.id,
            "name": "Player One",
            "team": "Team A",
            "position": "DEL",
            "totalPoints": 5,
            "weeksCounted": 1,
        }
    ]


def test_records_404s_for_an_unknown_season(client):
    assert client.get("/api/stats/records?season=2099").status_code == 404


def test_records_carries_jornada_and_season_records(session, client, season_stats_row):
    p = _player(session, "p1", "Player One", team="Team A")
    run = _run(session)
    session.add(_gw(2026, 3, p.id, 14, run.id))
    session.add(season_stats_row(season_year=2026, player_id=p.id, scrape_run_id=run.id, goals=3))
    session.commit()

    body = client.get("/api/stats/records?season=2026").json()

    assert body["jornadaRecords"] == [
        {"playerId": p.id, "name": "Player One", "team": "Team A", "week": 3, "points": 14}
    ]
    goals_record = next(r for r in body["seasonRecords"] if r["field"] == "goals")
    assert goals_record == {
        "field": "goals",
        "playerId": p.id,
        "name": "Player One",
        "team": "Team A",
        "value": 3,
    }


def test_leaderboard_400s_for_an_unknown_stat(session, client):
    assert client.get("/api/stats/leaderboard?season=2026&stat=notAField").status_code == 400


def test_leaderboard_404s_for_an_unknown_season(client):
    assert client.get("/api/stats/leaderboard?season=2099&stat=goals").status_code == 404


def test_leaderboard_returns_players_ordered_by_stat(session, client, season_stats_row):
    p1 = _player(session, "p1", "Player One", team="Team A", position="DEL")
    run = _run(session)
    session.add(_gw(2026, 1, p1.id, 5, run.id))
    session.add(
        season_stats_row(
            season_year=2026, player_id=p1.id, scrape_run_id=run.id, goals=7, total_points=10
        )
    )
    session.commit()

    body = client.get("/api/stats/leaderboard?season=2026&stat=goals").json()

    assert body["stat"] == "goals"
    assert body["players"] == [
        {
            "playerId": p1.id,
            "name": "Player One",
            "team": "Team A",
            "position": "DEL",
            "value": 7,
            "totalPoints": 10,
        }
    ]


def test_leaderboard_applies_position_and_team_filters(session, client, season_stats_row):
    p_match = _player(session, "p-match", "Match", team="Team A", position="DEL")
    p_wrong_pos = _player(session, "p-wrong", "Wrong Position", team="Team A", position="MED")
    run = _run(session)
    session.add_all([_gw(2026, 1, p_match.id, 1, run.id), _gw(2026, 1, p_wrong_pos.id, 1, run.id)])
    for p in (p_match, p_wrong_pos):
        session.add(
            season_stats_row(season_year=2026, player_id=p.id, scrape_run_id=run.id, goals=1)
        )
    session.commit()

    body = client.get(
        "/api/stats/leaderboard?season=2026&stat=goals&position=DEL&team=Team%20A"
    ).json()

    assert [p["name"] for p in body["players"]] == ["Match"]
