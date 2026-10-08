"""Within-position ranks (spec §6). Goalkeepers really do top raw Power, but
only one plays, so every rank, percentile and comparison here is computed
inside a position and never across them."""

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Rank:
    rank: int  # 1 = best; ties share the better rank
    of: int  # players ranked at this position
    percentile: float  # 0–100, 100 = best; ties share the average


def position_ranks(
    values: Mapping[int, float | None],
    positions: Mapping[int, str],
    higher_is_better: bool = True,
) -> dict[int, Rank]:
    groups: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for pid, v in values.items():
        if v is not None and pid in positions:
            groups[positions[pid]].append((pid, v if higher_is_better else -v))
    out: dict[int, Rank] = {}
    for members in groups.values():
        n = len(members)
        ordered = sorted(v for _, v in members)
        for pid, v in members:
            below = sum(1 for x in ordered if x < v)
            equal = sum(1 for x in ordered if x == v) - 1
            above = n - below - equal - 1
            pct = 50.0 if n == 1 else 100 * (below + equal / 2) / (n - 1)
            out[pid] = Rank(above + 1, n, pct)
    return out
