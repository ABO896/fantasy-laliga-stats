from core.ranks import Rank, position_ranks


def test_ranks_are_within_position():
    values = {1: 9.0, 2: 5.0, 3: 1.0, 4: 3.0}
    positions = {1: "DEF", 2: "DEF", 3: "DEL", 4: "DEL"}
    r = position_ranks(values, positions)
    assert r[1] == Rank(1, 2, 100.0)
    assert r[2] == Rank(2, 2, 0.0)
    assert r[4] == Rank(1, 2, 100.0)  # 3.0 tops DEL even though DEF has higher numbers
    assert r[3] == Rank(2, 2, 0.0)


def test_none_is_unranked_and_singletons_are_neutral():
    r = position_ranks({1: None, 2: 4.0}, {1: "POR", 2: "POR"})
    assert 1 not in r
    assert r[2] == Rank(1, 1, 50.0)


def test_ties_share_percentile_and_lower_is_better():
    r = position_ranks({1: 2.0, 2: 2.0, 3: 5.0}, dict.fromkeys((1, 2, 3), "MED"),
                       higher_is_better=False)
    assert r[1].percentile == r[2].percentile == 75.0
    assert r[3] == Rank(3, 3, 0.0)
    assert r[1].rank == 1 and r[2].rank == 1
