import csv
from pathlib import Path

from core.external_teams import FOOTBALL_DATA_TEAMS, canonical_team

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "external"

#: `Player.team` values in `data/fantasy.db`, 2026-09-27.
ROSTER_2026 = {
    "Alaves", "Athletic Club", "Atletico Madrid", "Barcelona", "Celta Vigo",
    "Deportivo La Coruna", "Elche", "Espanyol", "Getafe", "Levante", "Malaga",
    "Osasuna", "Racing Santander", "Rayo Vallecano", "Real Betis", "Real Madrid",
    "Real Sociedad", "Sevilla", "Valencia", "Villarreal",
}  # fmt: skip


def _teams(name: str) -> set[str]:
    with (FIXTURES / name).open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return {r["HomeTeam"] for r in rows} | {r["AwayTeam"] for r in rows}


def test_every_2026_club_maps_onto_the_roster_exactly():
    mapped = {canonical_team(t) for t in _teams("football-data-SP1-2627.csv")}
    assert mapped == ROSTER_2026


def test_every_2025_club_is_mapped():
    assert all(canonical_team(t) for t in _teams("football-data-SP1-2526.csv"))


def test_lookup_ignores_case_accents_and_spacing():
    assert canonical_team("  alavés ") == "Alaves"
    assert canonical_team("ATH  MADRID") == "Atletico Madrid"


def test_unknown_names_are_unmapped_not_guessed():
    assert canonical_team("Real") is None
    assert canonical_team("Madrid") is None
    assert canonical_team("Sociedad B") is None
    assert canonical_team("") is None
    assert canonical_team(None) is None


def test_the_table_never_maps_two_source_names_onto_one_club():
    values = list(FOOTBALL_DATA_TEAMS.values())
    assert len(values) == len(set(values))
