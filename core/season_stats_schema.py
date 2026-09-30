"""The canonical list of the statistics the source publishes per player
per season, and the camelCase -> snake_case mapping to our columns.

One source of truth, consumed by the parser, the table, and (in Plan 2)
the browser's column registry. `tests/storage/test_ingestion_schema.py`
asserts it has not drifted from the table — a name in one and not the
other yields a column that silently never sorts.

Verified against the live payload on 2026-08-23: 702 rows, 58 distinct
keys, of which these are the statistics. The remainder are identity
(`playerId`, `playerName`, `nickname`, `positionId`, `teamId`,
`teamName`, `teamShortName`, `id`, `masterPlayerId`, `slug`) and
`coachId`, which marks a club coach rather than a player.
"""

import re

#: (counter, points-contributed) — the pairing is what makes a stats view
#: answer "where do this player's points come from" rather than only "how
#: many". Every one of these 21 carries both halves in the payload.
STAT_PAIRS: tuple[tuple[str, str], ...] = (
    ("goals", "goalsPts"),
    ("goalAssist", "goalAssistPts"),
    ("offtargetAttAssist", "offtargetAttAssistPts"),
    ("totalScoringAtt", "totalScoringAttPts"),
    ("penAreaEntries", "penAreaEntriesPts"),
    ("penaltyWon", "penaltyWonPts"),
    ("penaltySave", "penaltySavePts"),
    ("penaltyFailed", "penaltyFailedPts"),
    ("penaltyConceded", "penaltyConcededPts"),
    ("saves", "savesPts"),
    ("effectiveClearance", "effectiveClearancePts"),
    ("ownGoals", "ownGoalsPts"),
    ("goalsConceded", "goalsConcededPts"),
    ("wonContest", "wonContestPts"),
    ("ballRecovery", "ballRecoveryPts"),
    ("possLostAll", "possLostAllPts"),
    ("yellowCard", "yellowCardPts"),
    ("secondYellowCard", "secondYellowCardPts"),
    ("redCard", "redCardPts"),
    ("minsPlayed", "minsPlayedPts"),
    ("marcaPoints", "marcaPointsPts"),
)

#: Season totals that stand alone rather than pairing with a points value.
SUMMARY_FIELDS: tuple[str, ...] = (
    "matchesPlayed",
    "totalPoints",
    "averagePoints",
    "marketValue",
    "idealFormationCount",
)

#: The allowlist for STATS-03 (season records) and STATS-04 (leaderboards):
#: every `STAT_PAIRS` counter plus the three summary totals that stand for
#: "who's best", never the points-contributed half of a pair. `marketValue`
#: and `idealFormationCount` are excluded — market value already has a
#: dedicated filter on the player browser (BROWSE-05), and ideal-formation
#: count isn't a "who's best" statistic.
SEASON_RECORD_FIELDS: tuple[str, ...] = tuple(counter for counter, _ in STAT_PAIRS) + (
    "totalPoints",
    "averagePoints",
    "matchesPlayed",
)

_CAMEL_BOUNDARY_RE = re.compile(r"(?<!^)(?=[A-Z])")


def column_name(camel: str) -> str:
    """`goalAssistPts` -> `goal_assist_pts`."""
    return _CAMEL_BOUNDARY_RE.sub("_", camel).lower()
