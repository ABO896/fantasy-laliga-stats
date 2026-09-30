"""Reads and writes for external football data (INGEST-09/10).

Kept apart from `storage/repository.py` because it shares nothing with the
fantasy-source tables except `ScrapeRun` provenance — the same "only place
the app talks SQL" rule, one module per data family.
"""

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlmodel import Session, distinct, select

from storage.models import ExternalMatch, Player

#: Every column a match record carries besides the key and provenance.
_VALUE_FIELDS = (
    "match_date",
    "kickoff_at",
    "status",
    "source_home_team",
    "source_away_team",
    "home_goals",
    "away_goals",
    "home_xg",
    "away_xg",
    "home_shots",
    "away_shots",
    "home_shots_on_target",
    "away_shots_on_target",
    "odds_home",
    "odds_draw",
    "odds_away",
    "odds_over25",
    "odds_under25",
    "closing_odds_home",
    "closing_odds_draw",
    "closing_odds_away",
    "closing_odds_over25",
    "closing_odds_under25",
)


@dataclass
class ExternalUpsert:
    written: int = 0
    #: Scheduled rows refused because the match is already stored as played.
    kept_played: int = 0


def upsert_external_matches(
    session: Session, records: list[dict], run_id: int, source: str = "football-data"
) -> ExternalUpsert:
    """Insert or update matches by (source, season, home, away).

    An update replaces every value column — odds move until kickoff, and a
    postponed match moves date — with one exception: a `scheduled` record
    never overwrites a `played` row. The coming-round file can lag the
    season file, and a result must not regress to a fixture.
    """
    result = ExternalUpsert()
    now = datetime.now(UTC)
    for record in records:
        key = (source, record["season_year"], record["home_team"], record["away_team"])
        row = session.get(ExternalMatch, key)
        if row is not None and row.status == "played" and record["status"] != "played":
            result.kept_played += 1
            continue
        if row is None:
            row = ExternalMatch(
                source=source,
                season_year=record["season_year"],
                home_team=record["home_team"],
                away_team=record["away_team"],
                status=record["status"],
                match_date=record["match_date"],
                source_home_team=record["source_home_team"],
                source_away_team=record["source_away_team"],
                raw_fields="{}",
                scrape_run_id=run_id,
                updated_at=now,
            )
        for name in _VALUE_FIELDS:
            setattr(row, name, record.get(name))
        row.raw_fields = json.dumps(
            record.get("raw_fields", {}), ensure_ascii=False, sort_keys=True
        )
        row.scrape_run_id = run_id
        row.updated_at = now
        session.add(row)
        result.written += 1
    session.commit()
    return result


def get_external_matches(
    session: Session,
    season_year: int | None = None,
    status: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    source: str = "football-data",
) -> list[ExternalMatch]:
    """Matches in date order (then kickoff, then home team, for stability)."""
    query = select(ExternalMatch).where(ExternalMatch.source == source)
    if season_year is not None:
        query = query.where(ExternalMatch.season_year == season_year)
    if status is not None:
        query = query.where(ExternalMatch.status == status)
    if from_date is not None:
        query = query.where(ExternalMatch.match_date >= from_date)
    if to_date is not None:
        query = query.where(ExternalMatch.match_date <= to_date)
    query = query.order_by(
        ExternalMatch.match_date, ExternalMatch.kickoff_at, ExternalMatch.home_team
    )
    return list(session.exec(query).all())


def get_roster_teams(session: Session) -> set[str]:
    """Every distinct `Player.team` — the names an external club must map
    onto to join the fantasy side."""
    return set(session.exec(select(distinct(Player.team))).all())
