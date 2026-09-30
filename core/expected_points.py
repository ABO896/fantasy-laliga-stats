"""MODEL-02 — expected fantasy points for one player in one jornada.

Pure functions, no I/O: callers (`storage/expected_points.py`, the offline
backtest in `core/xp_backtest.py`) load rows and pass plain values in.

**The model, in one line per term** (full derivation and backtest in
`docs/superpowers/specs/2026-09-27-expected-points-design.md`)::

    rate  = recency-weighted points per team match this season (zeros for
            matches he sat out), shrunk toward last season's per-appearance
            average (or a position default)
    base  = a·rate + b·rate·s + c·s          when a starter probability s is known
          = a·rate + c                       otherwise
    xP    = base
          + α · base · (team_goals − 1.4)    team expected goals, from the odds
          + γ · s' · (clean_sheet − 0.30)    clean-sheet probability, from the odds
    xP    = 0                                when his team has no fixture that jornada

Coefficients are per position and fitted by least squares on stored history
(see the spec for which data fitted which). Every term the prediction was
built from is returned beside the value, because a number the owner cannot
take apart is a number he has to take on trust (ANALYTICS-05).

**Vocabulary, deliberately not the market model's.** MODEL-01 grades its
calls strong/moderate/weak; expected points is a different, better-
conditioned problem and says what it was *built from* instead — its
`basis` — never how sure it is.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

MODEL_VERSION = "xp-1"

#: Half-life, in team matches, of the recency weighting on the points rate.
RATE_HALF_LIFE = 5.0
#: Pseudo-matches of prior the points rate is shrunk toward.
PRIOR_WEIGHT = 5.0
#: Last season's per-appearance average → a per-team-match prior. An
#: appearance row exists only for matchday-squad players, so the raw average
#: overstates what a squad player scores per team match.
PRIOR_SEASON_SCALE = 0.8
#: Per-team-match prior when the player has no last-season rows: 0.75 × the
#: position's average points per appearance, 2025/26.
POSITION_PRIOR = {"POR": 2.4, "DEF": 2.3, "MED": 2.6, "DEL": 2.9}

#: Centring constants for the fixture terms: the mean odds-derived team
#: expected goals and clean-sheet probability across 2025/26 and 2026/27.
LEAGUE_TEAM_GOALS = 1.4
LEAGUE_CLEAN_SHEET = 0.30
#: Mean starter probability (0–1) of the eligible player-weeks the starter
#: coefficients were fitted on — the clean-sheet term is scaled by s / this.
MEAN_STARTER = 0.528

# Fitted coefficients — regenerate with `uv run python -m storage.xp_backtest
# --fit` and paste. Values from the 2026-09-27 fit (see the spec).
#: base = a·rate + c, fitted on every scored 2025/26 week.
RATE_ONLY: dict[str, tuple[float, float]] = {
    "POR": (1.533, -1.173),
    "DEF": (1.083, 0.017),
    "MED": (1.249, -0.522),
    "DEL": (1.328, -0.839),
}
#: base = a·rate + b·rate·s + c·s, fitted on every 2026/27 week with a
#: snapshot before it (weeks 1–5).
WITH_STARTER: dict[str, tuple[float, float, float]] = {
    "POR": (-0.308, 1.15, 3.465),
    "DEF": (0.378, 0.011, 2.973),
    "MED": (0.765, 0.172, 1.532),
    "DEL": (0.445, 0.898, 1.563),
}
#: (α per goal of team expected goals, multiplicative on base;
#:  γ per unit of clean-sheet probability, additive), fitted on the
#: odds-validated 2025/26 weeks.
FIXTURE: dict[str, tuple[float, float]] = {
    "POR": (0.013, 2.682),
    "DEF": (0.033, 5.293),
    "MED": (0.073, 3.212),
    "DEL": (0.09, 4.392),
}


@dataclass(frozen=True)
class Coefficients:
    rate_only: dict[str, tuple[float, float]]
    with_starter: dict[str, tuple[float, float, float]]
    fixture: dict[str, tuple[float, float]]
    #: Scale the clean-sheet term by s / MEAN_STARTER when s is known.
    scale_clean_sheet_by_starter: bool = True


DEFAULT_COEFFICIENTS = Coefficients(RATE_ONLY, WITH_STARTER, FIXTURE)

#: Availability states that mean "will not play" when no starter
#: probability was published.
UNAVAILABLE = frozenset({"injured", "suspended"})


@dataclass(frozen=True)
class FixtureContext:
    """The player's team's side of one fixture, from the odds."""

    opponent: str
    is_home: bool
    team_goals: float | None = None  # odds-derived expected goals for his team
    clean_sheet: float | None = None  # odds-derived P(his team concedes 0)
    odds_source: str | None = None  # e.g. "football-data" — None when no odds


@dataclass(frozen=True)
class XpInputs:
    position: str  # POR | DEF | MED | DEL
    #: Points per team match this season, oldest first — 0 for a match his
    #: team played without him in the matchday squad.
    history: Sequence[int]
    #: Last season's points per appearance (row), or None.
    prior_season_mean: float | None
    #: 0–100 as the source publishes it, or None when unknown.
    starter_probability: float | None = None
    availability: str | None = None
    #: None when his team's fixture is unknown; see `has_fixture`.
    fixture: FixtureContext | None = None
    #: False only when the calendar *says* his team does not play.
    has_fixture: bool = True


@dataclass(frozen=True)
class RateEstimate:
    value: float
    matches: int
    prior: float
    prior_source: str  # "last_season" | "position"
    recent: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class XpResult:
    value: float
    #: What it was built from: "form", "form+starter", "form+odds",
    #: "form+starter+odds", or "no_fixture".
    basis: str
    #: Every input and every term's contribution, JSON-ready.
    inputs: dict


def points_rate(
    history: Sequence[int], prior_season_mean: float | None, position: str
) -> RateEstimate:
    """Recency-weighted points per team match, shrunk toward a prior."""
    if prior_season_mean is not None:
        prior, source = prior_season_mean * PRIOR_SEASON_SCALE, "last_season"
    else:
        prior, source = POSITION_PRIOR.get(position, 2.5), "position"
    n = len(history)
    weights = [0.5 ** ((n - 1 - i) / RATE_HALF_LIFE) for i in range(n)]
    num = sum(w * x for w, x in zip(weights, history, strict=True)) + PRIOR_WEIGHT * prior
    den = sum(weights) + PRIOR_WEIGHT
    return RateEstimate(num / den, n, prior, source, list(history[-5:]))


def _starter_fraction(inputs: XpInputs) -> float | None:
    if inputs.starter_probability is not None:
        return max(0.0, min(1.0, inputs.starter_probability / 100))
    if inputs.availability in UNAVAILABLE:
        return 0.0
    return None


def _round(x: float | None, n: int = 3) -> float | None:
    return None if x is None else round(x, n)


def expected_points(inputs: XpInputs, coefficients: Coefficients | None = None) -> XpResult:
    """xP for one player in one jornada, with its basis and every input.

    `coefficients` exists for the backtest, which refits per fold; the app
    always uses the fitted module constants."""
    k = coefficients or DEFAULT_COEFFICIENTS
    fixture = inputs.fixture
    fixture_info = fixture and {
        "opponent": fixture.opponent,
        "isHome": fixture.is_home,
        "teamGoals": _round(fixture.team_goals),
        "cleanSheet": _round(fixture.clean_sheet),
        "oddsSource": fixture.odds_source,
    }
    if not inputs.has_fixture:
        return XpResult(0.0, "no_fixture", {"modelVersion": MODEL_VERSION, "fixture": None})

    rate = points_rate(inputs.history, inputs.prior_season_mean, inputs.position)
    s = _starter_fraction(inputs)
    pos = inputs.position

    if s is None:
        a, c = k.rate_only[pos]
        terms = {"rate": a * rate.value, "intercept": c}
        coefficients = {"a": a, "c": c}
    else:
        a, b, c = k.with_starter[pos]
        terms = {"rate": a * rate.value, "rateXStarter": b * rate.value * s, "starter": c * s}
        coefficients = {"a": a, "b": b, "c": c}
    base = sum(terms.values())

    have_odds = (
        fixture is not None and fixture.team_goals is not None and fixture.clean_sheet is not None
    )
    if have_odds:
        alpha, gamma = k.fixture[pos]
        cs_scale = s / MEAN_STARTER if s is not None and k.scale_clean_sheet_by_starter else 1.0
        terms["attack"] = alpha * base * (fixture.team_goals - LEAGUE_TEAM_GOALS)
        terms["cleanSheet"] = gamma * cs_scale * (fixture.clean_sheet - LEAGUE_CLEAN_SHEET)
        coefficients |= {"alpha": alpha, "gamma": gamma}

    value = max(0.0, sum(terms.values()))
    basis = "form" + ("+starter" if s is not None else "") + ("+odds" if have_odds else "")
    return XpResult(
        value=value,
        basis=basis,
        inputs={
            "modelVersion": MODEL_VERSION,
            "position": pos,
            "rate": {
                "value": _round(rate.value),
                "matches": rate.matches,
                "recentPoints": rate.recent,
                "halfLife": RATE_HALF_LIFE,
                "prior": _round(rate.prior),
                "priorSource": rate.prior_source,
                "priorWeight": PRIOR_WEIGHT,
            },
            "starterProbability": inputs.starter_probability,
            "availability": inputs.availability,
            "fixture": fixture_info,
            "coefficients": coefficients,
            "terms": {k: _round(v) for k, v in terms.items()},
        },
    )


# --- scoring (MODEL-03 for xP) --------------------------------------------------------


@dataclass(frozen=True)
class ScoredPair:
    predicted: float
    actual: float
    basis: str


@dataclass(frozen=True)
class ErrorSummary:
    n: int
    mae: float | None
    rmse: float | None
    #: Mean of predicted − actual: positive means we over-predict.
    bias: float | None


def summarize_errors(pairs: Sequence[ScoredPair]) -> ErrorSummary:
    if not pairs:
        return ErrorSummary(0, None, None, None)
    errors = [p.predicted - p.actual for p in pairs]
    n = len(errors)
    return ErrorSummary(
        n=n,
        mae=sum(abs(e) for e in errors) / n,
        rmse=math.sqrt(sum(e * e for e in errors) / n),
        bias=sum(errors) / n,
    )
