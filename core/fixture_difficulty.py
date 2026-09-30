"""Fixture difficulty per team over the next N jornadas (TRANSFER-03).

Pure: no database, no clock (the caller passes `now`), no scraper import.
The storage layer feeds it `Fixture` rows and per-team jornada totals.

**This project's own measure, not the source's.** The calendar payload
carries the source's per-side `difficulty` label; that is a derived score
of theirs and is kept as a reference field only (SCRAPING-POLICY, Data
handling). The number here is computed from data this project already
holds.

The formula, in three steps:

1. **Team strength** — how good an opponent is. For each team, its mean
   total fantasy points per *final* jornada this season (the sum over its
   players in `PlayerGameweekPoints`, grouped on `Player.team`). Fantasy
   points reward goals, assists, clean sheets and wins, so a team's total is
   an honest single-number proxy for its overall level — the data holds no
   match results, so no goals-for/against model is possible yet. Expressed
   relative to the league mean (1.0 = average).

   Early in a season a handful of jornadas is noise, so the rating is
   shrunk toward a prior worth `PRIOR_WEIGHT_WEEKS` jornadas:

       rating = (n * current_rel + k * prior) / (n + k)

   The prior is the team's relative rating last season when it has one,
   else 1.0 (a promoted side, or no history) — which flatters promoted
   sides slightly; accepted rather than guessed at.

2. **Venue** — a fixed `HOME_ADVANTAGE` of 10%: at home a fixture is
   `rating * 0.9`, away `rating * 1.1`. An assumption, not a fit: the data
   holds no venue-split history to estimate it from. The accumulating
   `fixture` table is what will eventually let it be fitted.

3. **Window** — the next N jornadas *in kickoff order*, each jornada placed
   at its earliest upcoming kickoff. Jornada numbers are not chronological
   (a postponed match keeps its number), so a postponed fixture that falls
   inside the window counts as an extra fixture for both sides; a team can
   therefore have 0, 1 or 2+ fixtures. `average_difficulty` is the mean over
   the team's fixtures in the window (1.0 = an average opponent at a
   neutral venue; lower is easier); `fixture_count` is reported separately
   because more matches is its own advantage and a sum would punish it.

Known weakness: `Player.team` is each player's *current* club, so a
mid-season transfer carries his earlier points with him.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

#: Fractional difficulty discount at home / surcharge away. Assumed, not
#: fitted — see the module docstring.
HOME_ADVANTAGE = 0.10

#: How many jornadas' worth of weight the prior carries in the shrinkage.
PRIOR_WEIGHT_WEEKS = 4

#: How long after kickoff a fixture not yet marked final still counts as
#: upcoming (in play). Beyond it an unfinished fixture is stale, not live.
IN_PLAY_GRACE = timedelta(hours=3)


@dataclass(frozen=True)
class FixtureView:
    """The fields of a stored fixture this module reads."""

    fixture_id: int
    matchday: int
    kickoff_utc: datetime
    kickoff_confirmed: bool
    is_final: bool
    home_team: str
    away_team: str


@dataclass(frozen=True)
class TeamFixture:
    fixture_id: int
    matchday: int
    kickoff_utc: datetime
    kickoff_confirmed: bool
    opponent: str
    is_home: bool
    opponent_strength: float
    difficulty: float


@dataclass(frozen=True)
class TeamDifficulty:
    team: str
    average_difficulty: float | None
    fixture_count: int
    fixtures: list[TeamFixture] = field(default_factory=list)


def upcoming_fixtures(
    fixtures: Iterable[FixtureView], now: datetime, grace: timedelta = IN_PLAY_GRACE
) -> list[FixtureView]:
    """Fixtures not yet final whose kickoff is ahead of `now` (or within
    `grace` behind it — in play), in kickoff order."""
    cutoff = now - grace
    return sorted(
        (f for f in fixtures if not f.is_final and f.kickoff_utc >= cutoff),
        key=lambda f: (f.kickoff_utc, f.fixture_id),
    )


def _relative(team_weeks: Mapping[str, Sequence[float]]) -> tuple[dict[str, float], dict[str, int]]:
    means = {team: sum(weeks) / len(weeks) for team, weeks in team_weeks.items() if weeks}
    if not means:
        return {}, {}
    league_mean = sum(means.values()) / len(means)
    if league_mean <= 0:
        return {team: 1.0 for team in means}, {t: len(team_weeks[t]) for t in means}
    return (
        {team: mean / league_mean for team, mean in means.items()},
        {team: len(team_weeks[team]) for team in means},
    )


def team_strength(
    current: Mapping[str, Sequence[float]],
    previous: Mapping[str, Sequence[float]] | None = None,
    teams: Iterable[str] = (),
) -> dict[str, float]:
    """Relative rating per team (1.0 = league average), shrunk toward last
    season's relative rating (or 1.0) by `PRIOR_WEIGHT_WEEKS`.

    `current` / `previous` map team -> total fantasy points per final
    jornada. `teams` adds teams to rate that may have no data at all.
    """
    current_rel, current_n = _relative(current)
    previous_rel, _ = _relative(previous or {})

    ratings: dict[str, float] = {}
    for team in set(current) | set(previous or {}) | set(teams):
        prior = previous_rel.get(team, 1.0)
        n = current_n.get(team, 0)
        if n == 0:
            ratings[team] = prior
        else:
            ratings[team] = (n * current_rel[team] + PRIOR_WEIGHT_WEEKS * prior) / (
                n + PRIOR_WEIGHT_WEEKS
            )
    return ratings


def window_jornadas(fixtures: Sequence[FixtureView], n: int) -> list[int]:
    """The next `n` jornadas in kickoff order, each placed at its earliest
    kickoff among `fixtures`."""
    if n < 1:
        raise ValueError("n must be at least 1")
    earliest: dict[int, datetime] = {}
    for f in fixtures:
        if f.matchday not in earliest or f.kickoff_utc < earliest[f.matchday]:
            earliest[f.matchday] = f.kickoff_utc
    return sorted(earliest, key=lambda m: (earliest[m], m))[:n]


def fixture_difficulty(
    fixtures: Sequence[FixtureView], strength: Mapping[str, float], n: int
) -> list[TeamDifficulty]:
    """Per-team difficulty over the next `n` jornadas of `fixtures` (pass
    `upcoming_fixtures(...)`). Every team appearing anywhere in `fixtures`
    is listed; easiest first, teams with no fixture in the window last.
    A team missing from `strength` rates 1.0."""
    jornadas = set(window_jornadas(fixtures, n))
    in_window = sorted(
        (f for f in fixtures if f.matchday in jornadas),
        key=lambda f: (f.kickoff_utc, f.fixture_id),
    )

    per_team: dict[str, list[TeamFixture]] = {}
    for f in fixtures:
        per_team.setdefault(f.home_team, [])
        per_team.setdefault(f.away_team, [])

    for f in in_window:
        for team, opponent, is_home in (
            (f.home_team, f.away_team, True),
            (f.away_team, f.home_team, False),
        ):
            opp = strength.get(opponent, 1.0)
            venue = 1 - HOME_ADVANTAGE if is_home else 1 + HOME_ADVANTAGE
            per_team[team].append(
                TeamFixture(
                    fixture_id=f.fixture_id,
                    matchday=f.matchday,
                    kickoff_utc=f.kickoff_utc,
                    kickoff_confirmed=f.kickoff_confirmed,
                    opponent=opponent,
                    is_home=is_home,
                    opponent_strength=opp,
                    difficulty=opp * venue,
                )
            )

    result = [
        TeamDifficulty(
            team=team,
            average_difficulty=(
                sum(tf.difficulty for tf in tfs) / len(tfs) if tfs else None
            ),
            fixture_count=len(tfs),
            fixtures=tfs,
        )
        for team, tfs in per_team.items()
    ]
    return sorted(
        result,
        key=lambda t: (
            t.average_difficulty is None,
            t.average_difficulty if t.average_difficulty is not None else 0.0,
            t.team,
        ),
    )
