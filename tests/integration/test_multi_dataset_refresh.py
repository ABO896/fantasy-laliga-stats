from datetime import UTC, datetime
from pathlib import Path

from scraper.errors import ScrapeBlocked
from scraper.run import (
    ingest_jornada_points,
    ingest_market_predictions,
    ingest_points_predictions,
    ingest_season_stats,
)
from storage.models import Player, PlayerGameweekPoints, ScrapeRun
from storage.repository import get_dataset_runs

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "phase7"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _run(session) -> ScrapeRun:
    r = ScrapeRun(started_at=datetime.now(UTC), status="running")
    session.add(r)
    session.commit()
    session.refresh(r)
    return r


def _jornada_fetcher():
    """Answer each requested week with the fixture that really is that week.

    A stub returning the same page for every week would make the parser
    reject each earlier week as a fallback — which is correct behaviour
    against a wrong stub, and tests nothing.
    """
    pages = {None: "jornada-2026-latest.html", 1: "jornada-2026-w1.html"}

    def fetch(season_year, week, settings=None):
        return _read(pages[week])

    return fetch


def test_one_dataset_failing_does_not_stop_the_others(session, monkeypatch):
    run = _run(session)
    monkeypatch.setattr(
        "scraper.run.fetch_jornada", lambda *a, **k: (_ for _ in ()).throw(ScrapeBlocked("429"))
    )
    monkeypatch.setattr(
        "scraper.run.fetch_season_stats", lambda *a, **k: _read("estadisticas-2025.html")
    )

    ingest_jornada_points(session, run, None)
    ingest_season_stats(session, run, None)

    runs = {d.dataset: d for d in get_dataset_runs(session, run.id)}
    assert runs["jornada_points"].status == "failed"
    assert runs["season_stats"].status == "success"
    assert "ScrapeBlocked" in runs["jornada_points"].errors


def test_season_stats_records_the_season_it_actually_stored(session, monkeypatch):
    run = _run(session)
    monkeypatch.setattr(
        "scraper.run.fetch_season_stats", lambda *a, **k: _read("estadisticas-2025.html")
    )
    ingest_season_stats(session, run, None)
    runs = {d.dataset: d for d in get_dataset_runs(session, run.id)}
    assert runs["season_stats"].season_year == 2025


def test_the_active_jornada_is_stored_provisional(session, monkeypatch):
    now = datetime.now(UTC)
    session.add(
        Player(
            external_id="oso-341453",
            name="Oso",
            team="Sevilla FC",
            position="DEF",
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    run = _run(session)
    monkeypatch.setattr("scraper.run.fetch_jornada", _jornada_fetcher())

    ingest_jornada_points(session, run, None)

    from sqlmodel import select

    rows = session.exec(select(PlayerGameweekPoints)).all()
    active = [r for r in rows if r.week == 2]
    assert active and all(r.is_provisional for r in active)
    assert all(r.season_year == 2026 for r in rows)


def test_an_unfetchable_earlier_week_is_a_gap_not_a_dataset_failure(session, monkeypatch):
    """Success criterion 5: a missed jornada is a week in `rounds` with no
    stored row. One bad week is that gap — it must not abort the dataset
    and lose the current jornada too."""
    now = datetime.now(UTC)
    session.add(
        Player(
            external_id="oso-341453",
            name="Oso",
            team="Sevilla FC",
            position="DEF",
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    run = _run(session)

    def fetch(season_year, week, settings=None):
        if week == 1:
            raise ScrapeBlocked("429 on week 1")
        return _read("jornada-2026-latest.html")

    monkeypatch.setattr("scraper.run.fetch_jornada", fetch)

    ingest_jornada_points(session, run, None)

    runs = {d.dataset: d for d in get_dataset_runs(session, run.id)}
    assert runs["jornada_points"].status == "success"
    assert "week 1" in (runs["jornada_points"].errors or "")

    from sqlmodel import select

    rows = session.exec(select(PlayerGameweekPoints)).all()
    assert rows and all(r.week == 2 for r in rows), "the active jornada must still be stored"


def test_prediction_ingests_write_rows_end_to_end(session, monkeypatch):
    """Neither prediction ingest was covered here before — that gap is
    exactly why the duplicate-club-registration row in the real
    points-predictions payload surfaced four commits downstream, in the
    pre-existing pipeline tests, instead of in this task's own suite.
    Covers both end to end against the real committed fixtures."""
    now = datetime.now(UTC)
    session.add_all(
        [
            Player(
                external_id="marc-aguado-187318",
                name="Marc Aguado",
                team="Barcelona",
                position="MED",
                created_at=now,
                updated_at=now,
            ),
            Player(
                external_id="j-bellingham-129718",
                name="Jude Bellingham",
                team="Real Madrid",
                position="MED",
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    session.commit()
    run = _run(session)
    monkeypatch.setattr(
        "scraper.run.fetch_points_predictions", lambda *a, **k: _read("predicciones.html")
    )
    monkeypatch.setattr(
        "scraper.run.fetch_market_predictions",
        lambda *a, **k: _read("prediccion-de-mercado.html"),
    )

    ingest_points_predictions(session, run, None)
    ingest_market_predictions(session, run, None)

    runs = {d.dataset: d for d in get_dataset_runs(session, run.id)}
    assert runs["points_predictions"].status == "success"
    assert runs["points_predictions"].row_count > 0
    assert runs["market_predictions"].status == "success"
    assert runs["market_predictions"].row_count > 0
