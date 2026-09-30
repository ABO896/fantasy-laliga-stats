"""Betting odds -> the probabilities a points model needs (INGEST-10).

Pure functions, no I/O. Everything takes **decimal** odds (2.50, not 6/4 or
+150), which is the only format football-data.co.uk publishes.

Three steps, each usable on its own:

1. **Remove the overround.** A bookmaker's implied probabilities (1/odds)
   sum to more than 1 — the margin. `remove_overround` rescales them to a
   proper distribution. `proportional` divides by the sum (the textbook
   method); `power` raises each to one shared exponent `k` so they sum to 1,
   which takes proportionally more margin off longshots and so corrects
   part of the favourite-longshot bias. Proportional is the default because
   it is the transparent one; a model can ask for `power`.

2. **Fit expected goals.** A points model needs *rates*, not outcomes: a
   clean sheet is P(opponent scores 0), which 1X2 alone does not state.
   `fit_poisson_goals` finds home/away Poisson rates (independent goals — the
   standard, simple model; it slightly under-predicts draws) reproducing the
   market's view:
   - total goals `T` from the over/under 2.5 line (the sum of independent
     Poissons is Poisson, so this is exact and one-dimensional), then
   - the home share of `T` from P(home) - P(away), the market's *supremacy*.
   Without an over/under price, `T` is chosen to reproduce the draw
   probability instead — weaker, since the draw is where the independent
   Poisson model is known to be worst, and flagged as `goals_fit="1x2"`.

3. **Derive what a points model reads.** `match_probabilities` bundles it:
   de-margined 1X2 and over/under, fitted rates, and clean-sheet
   probabilities `P(CS home) = exp(-rate_away)`.

Both solvers are bisection over monotone functions: deterministic, no
dependency, and exact to well under the precision odds are quoted at.
"""

import math
from dataclasses import dataclass

_MAX_GOALS = 25
_BISECT_ITERATIONS = 80


def _validate(odds: list[float]) -> None:
    if len(odds) < 2:
        raise ValueError(f"A book needs at least two outcomes, got {len(odds)}")
    for o in odds:
        if o is None or not math.isfinite(o) or o <= 1.0:
            raise ValueError(f"Decimal odds must be finite and > 1.0, got {o!r}")


def overround(odds: list[float]) -> float:
    """The bookmaker's margin: sum of implied probabilities minus 1."""
    _validate(odds)
    return sum(1 / o for o in odds) - 1


def remove_overround(odds: list[float], method: str = "proportional") -> list[float]:
    """Implied probabilities with the margin removed; they sum to 1."""
    _validate(odds)
    implied = [1 / o for o in odds]
    if method == "proportional":
        total = sum(implied)
        return [p / total for p in implied]
    if method == "power":
        # sum(p_i ** k) is decreasing in k for p_i < 1; find k where it is 1.
        lo, hi = 0.01, 10.0
        for _ in range(_BISECT_ITERATIONS):
            mid = (lo + hi) / 2
            if sum(p**mid for p in implied) > 1:
                lo = mid
            else:
                hi = mid
        k = (lo + hi) / 2
        probs = [p**k for p in implied]
        total = sum(probs)  # ~1 already; removes the last bisection residue
        return [p / total for p in probs]
    raise ValueError(f"Unknown overround method {method!r}")


@dataclass(frozen=True)
class ScoreProbabilities:
    home: float
    draw: float
    away: float
    over25: float


def _poisson_pmf(rate: float) -> list[float]:
    pmf = [math.exp(-rate)]
    for k in range(1, _MAX_GOALS + 1):
        pmf.append(pmf[-1] * rate / k)
    return pmf


def score_matrix_probabilities(rate_home: float, rate_away: float) -> ScoreProbabilities:
    """1X2 and over-2.5 under independent Poisson goals."""
    ph, pa = _poisson_pmf(rate_home), _poisson_pmf(rate_away)
    home = draw = away = under = 0.0
    for i, pi in enumerate(ph):
        for j, pj in enumerate(pa):
            p = pi * pj
            if i > j:
                home += p
            elif i == j:
                draw += p
            else:
                away += p
            if i + j <= 2:
                under += p
    return ScoreProbabilities(home=home, draw=draw, away=away, over25=1 - under)


@dataclass(frozen=True)
class GoalRates:
    home: float
    away: float


def _bisect(f, lo: float, hi: float, target: float, increasing: bool) -> float:
    for _ in range(_BISECT_ITERATIONS):
        mid = (lo + hi) / 2
        above = f(mid) > target
        if above == increasing:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def _split_for_supremacy(total: float, supremacy: float) -> GoalRates:
    """Home share `s` of `total` such that P(home) - P(away) == supremacy."""

    def sup(s: float) -> float:
        p = score_matrix_probabilities(s * total, (1 - s) * total)
        return p.home - p.away

    s = _bisect(sup, 1e-6, 1 - 1e-6, supremacy, increasing=True)
    return GoalRates(home=s * total, away=(1 - s) * total)


def fit_poisson_goals(
    p_home: float, p_draw: float, p_away: float, p_over25: float | None
) -> GoalRates:
    """Home and away Poisson rates reproducing the market's probabilities.

    Inputs must already be margin-free (see `remove_overround`).
    """
    supremacy = p_home - p_away
    if p_over25 is not None:

        def over(total: float) -> float:
            under = sum(math.exp(-total) * total**k / math.factorial(k) for k in range(3))
            return 1 - under

        total = _bisect(over, 0.05, 10.0, p_over25, increasing=True)
        return _split_for_supremacy(total, supremacy)

    def draw_at(total: float) -> float:
        rates = _split_for_supremacy(total, supremacy)
        return score_matrix_probabilities(rates.home, rates.away).draw

    total = _bisect(draw_at, 0.05, 10.0, p_draw, increasing=False)
    return _split_for_supremacy(total, supremacy)


@dataclass(frozen=True)
class MatchProbabilities:
    p_home: float
    p_draw: float
    p_away: float
    p_over25: float
    p_under25: float
    exp_goals_home: float
    exp_goals_away: float
    p_clean_sheet_home: float
    p_clean_sheet_away: float
    overround_1x2: float
    overround_ou: float | None
    #: "1x2+ou" when total goals came from the over/under line, "1x2" when
    #: only the draw was available to pin it (weaker — see module docstring).
    goals_fit: str
    method: str


def match_probabilities(
    odds_home: float | None,
    odds_draw: float | None,
    odds_away: float | None,
    odds_over25: float | None,
    odds_under25: float | None,
    method: str = "proportional",
) -> MatchProbabilities | None:
    """Everything a points model needs from one fixture's prices, or `None`
    when the 1X2 book is incomplete — absent, never guessed."""
    if odds_home is None or odds_draw is None or odds_away is None:
        return None
    one_x_two = [odds_home, odds_draw, odds_away]
    p_home, p_draw, p_away = remove_overround(one_x_two, method)

    have_ou = odds_over25 is not None and odds_under25 is not None
    p_over_market = None
    if have_ou:
        p_over_market, _ = remove_overround([odds_over25, odds_under25], method)

    rates = fit_poisson_goals(p_home, p_draw, p_away, p_over_market)
    if p_over_market is None:
        p_over = score_matrix_probabilities(rates.home, rates.away).over25
    else:
        p_over = p_over_market

    return MatchProbabilities(
        p_home=p_home,
        p_draw=p_draw,
        p_away=p_away,
        p_over25=p_over,
        p_under25=1 - p_over,
        exp_goals_home=rates.home,
        exp_goals_away=rates.away,
        p_clean_sheet_home=math.exp(-rates.away),
        p_clean_sheet_away=math.exp(-rates.home),
        overround_1x2=overround(one_x_two),
        overround_ou=overround([odds_over25, odds_under25]) if have_ou else None,
        goals_fit="1x2+ou" if have_ou else "1x2",
        method=method,
    )
