"""Team strength from results — a Poisson attack/defence model. Pure.

xP's opponent terms (`core.expected_points`) want, for one fixture, a team's
expected goals and its chance of a clean sheet. Bookmaker odds give both, but
football-data publishes the coming round's odds only shortly before it is
played, so a refresh before then had no opponent term at all (all 558 J8
predictions on 2026-10-08). This model supplies the same two numbers from
results already stored, and is refitted on every refresh — no stored state.

    log λ_home = μ + h + attack[home] − defence[away]
    log λ_away = μ     + attack[away] − defence[home]

fitted by weighted Poisson maximum likelihood (cyclic Newton steps), with a
ridge penalty pulling every attack/defence toward 0 — so a team with few or
no matches reads as average, never as extreme. Each match's target blends
goals with expected goals when the source has them (`target`), and its weight
decays with age (`recency_weight`). The clean-sheet chance is the Poisson
probability that the opponent scores none: `exp(−λ_opponent)`.
"""

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

#: Ridge strength on attack/defence, in pseudo-matches of evidence at λ ≈ 1.
RIDGE = 4.0
#: A match this many days old counts half as much as one played today.
HALF_LIFE_DAYS = 150.0
#: Share of the target taken from expected goals, when present.
XG_SHARE = 0.5
#: Goals per team per match before any result is seen (LaLiga ≈ 1.3).
LEAGUE_GOALS_PRIOR = 1.3
ITERATIONS = 60


@dataclass(frozen=True)
class MatchResult:
    home: str
    away: str
    home_goals: float  # the target: goals, or `target(goals, xg)`
    away_goals: float
    weight: float = 1.0


@dataclass(frozen=True)
class Strengths:
    mu: float
    home_advantage: float
    attack: dict[str, float] = field(default_factory=dict)
    defence: dict[str, float] = field(default_factory=dict)
    matches: int = 0


def target(goals: float, xg: float | None) -> float:
    """What a match says about a side's scoring: goals blended with xG."""
    return goals if xg is None else (1 - XG_SHARE) * goals + XG_SHARE * xg


def recency_weight(age_days: float) -> float:
    return 0.5 ** (max(age_days, 0.0) / HALF_LIFE_DAYS)


def from_records(records, as_of) -> list[MatchResult]:
    """Played matches before `as_of` (a date), as weighted fit rows. Each
    record is a dict with `home_team`, `away_team`, `home_goals`,
    `away_goals`, `home_xg`, `away_xg` and `match_date` — football-data's
    parsed shape and `ExternalMatch`'s columns alike, so the live model and
    the backtest share this one conversion."""
    out = []
    for r in records:
        if r["home_goals"] is None or r["away_goals"] is None or r["match_date"] >= as_of:
            continue
        out.append(MatchResult(
            r["home_team"], r["away_team"],
            target(r["home_goals"], r.get("home_xg")),
            target(r["away_goals"], r.get("away_xg")),
            recency_weight((as_of - r["match_date"]).days),
        ))
    return out


def _rates(s: Strengths, home: str, away: str) -> tuple[float, float]:
    a, d = s.attack, s.defence
    lh = math.exp(s.mu + s.home_advantage + a.get(home, 0.0) - d.get(away, 0.0))
    la = math.exp(s.mu + a.get(away, 0.0) - d.get(home, 0.0))
    return lh, la


def fit(matches: Sequence[MatchResult]) -> Strengths:
    """Weighted Poisson fit; deterministic (teams are updated in sorted order)."""
    ms = [m for m in matches if m.weight > 0]
    total_w = sum(m.weight for m in ms)
    if total_w == 0:
        return Strengths(math.log(LEAGUE_GOALS_PRIOR), 0.0)
    mean = sum(m.weight * (m.home_goals + m.away_goals) for m in ms) / (2 * total_w)
    s = Strengths(math.log(max(mean, 0.1)), 0.0, matches=len(ms))
    teams = sorted({t for m in ms for t in (m.home, m.away)})
    attack = dict.fromkeys(teams, 0.0)
    defence = dict.fromkeys(teams, 0.0)
    by_team: dict[str, list[MatchResult]] = defaultdict(list)
    for m in ms:
        by_team[m.home].append(m)
        by_team[m.away].append(m)

    mu, h = s.mu, 0.0
    for _ in range(ITERATIONS):
        cur = Strengths(mu, h, attack, defence)
        # μ and home advantage: unpenalised Newton steps.
        g = hh = gh = hhh = 0.0
        for m in ms:
            lh, la = _rates(cur, m.home, m.away)
            g += m.weight * (m.home_goals - lh + m.away_goals - la)
            hh += m.weight * (lh + la)
            gh += m.weight * (m.home_goals - lh)
            hhh += m.weight * lh
        mu += g / hh
        h += gh / hhh if hhh else 0.0
        for team in teams:
            cur = Strengths(mu, h, attack, defence)
            ga = ha = gd = hd = 0.0
            for m in by_team[team]:
                lh, la = _rates(cur, m.home, m.away)
                if m.home == team:
                    # attack drives λ_home; defence lowers λ_away
                    ga += m.weight * (m.home_goals - lh)
                    ha += m.weight * lh
                    gd += -m.weight * (m.away_goals - la)
                    hd += m.weight * la
                else:
                    ga += m.weight * (m.away_goals - la)
                    ha += m.weight * la
                    gd += -m.weight * (m.home_goals - lh)
                    hd += m.weight * lh
            attack[team] += (ga - RIDGE * attack[team]) / (ha + RIDGE)
            defence[team] += (gd - RIDGE * defence[team]) / (hd + RIDGE)
        # Centre both at zero (absorbed by μ), so 0 — what an unknown team
        # gets — means "league average".
        ma = sum(attack.values()) / len(teams)
        md = sum(defence.values()) / len(teams)
        for team in teams:
            attack[team] -= ma
            defence[team] -= md
        mu += ma - md
    return Strengths(mu, h, dict(attack), dict(defence), len(ms))


def team_view(s: Strengths, home: str, away: str, team: str) -> tuple[float, float]:
    """`(team_goals, clean_sheet)` for `team`'s side of `home` vs `away`."""
    lh, la = _rates(s, home, away)
    if team == home:
        return lh, math.exp(-la)
    return la, math.exp(-lh)
