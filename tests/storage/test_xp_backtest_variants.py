"""The opponent-model gate's context builder: each week's model is fitted
only on matches played before that week (no look-ahead)."""

from datetime import date
from pathlib import Path

from core import team_strength as ts
from scraper.sources.football_data import parse_matches
from storage.xp_backtest import model_contexts

CSV = Path(__file__).resolve().parents[1] / "fixtures" / "external" / "football-data-SP1-2627.csv"


def test_model_contexts_never_see_their_own_week():
    records = parse_matches(CSV.read_text(), expected_season=2026).records
    first = min(r["match_date"] for r in records)
    week_one = [r for r in records if (r["match_date"] - first).days <= 3]
    alignment = {}
    for r in week_one:
        alignment[(r["home_team"], 1)] = r
        alignment[(r["away_team"], 1)] = r
    data = {"matches": {2026: records}}
    ctx = model_contexts(data, 2026, {"alignment": alignment, "trusted": [1]})

    # Week 1 has nothing before it: every team reads as the league prior.
    home = week_one[0]["home_team"]
    goals = ctx[(home, 1)].team_goals
    prior = ts.team_view(ts.fit([]), "x", "y", "x")[0]
    assert goals == prior
    assert ctx[(home, 1)].odds_source == "model"
    assert all(d < date(2026, 12, 31) for d in (first,))
