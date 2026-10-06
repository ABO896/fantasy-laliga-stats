"""SQLModel table definitions.

The schema is created exclusively by Alembic revisions (see
`migrations/versions/`) — nothing in application or test code calls a
direct table-creation helper against this metadata.
"""

from datetime import date, datetime

from sqlmodel import Field, SQLModel


class Player(SQLModel, table=True):
    """Slowly-changing player identity — upserted, never historized here.
    History lives exclusively in `PlayerSnapshot`."""

    id: int | None = Field(default=None, primary_key=True)
    external_id: str = Field(index=True, unique=True)
    name: str
    team: str
    position: str  # normalized: POR | DEF | MED | DEL
    created_at: datetime
    updated_at: datetime


class PlayerSnapshot(SQLModel, table=True):
    """Append-only, one row per player per scrape day.

    The composite primary key leads with `as_of`, not `player_id` — SQLite
    builds the PK's implicit index in declared column order, and this
    phase's dominant query ("every player as of the latest date") becomes
    an index range scan instead of a full-table scan. Never updated or
    deleted once written (see `storage/repository.py::append_snapshots`).
    """

    as_of: date = Field(primary_key=True)
    player_id: int = Field(foreign_key="player.id", primary_key=True)
    market_value: int
    ideal_bid: int | None = None
    max_bid: int | None = None
    price_change_abs: int | None = None
    price_change_pct: float | None = None
    points: int
    price_per_point: float | None = None
    starter_probability: float | None = None
    availability_status: str  # available | injured | doubtful | suspended
    next_opponent: str | None = None
    is_starter: bool | None = None
    market_updates_to_next_match: int | None = None  # the source's mercadosProximoPartido
    next_fixture_id: int | None = None
    raw_fields: str  # JSON of every cell the parser produced, verbatim
    scrape_run_id: int = Field(foreign_key="scraperun.id")


class ScrapeRun(SQLModel, table=True):
    """One row per scrape attempt — always written, success or not."""

    id: int | None = Field(default=None, primary_key=True)
    started_at: datetime
    finished_at: datetime | None = None
    status: str = "running"  # running | success | rejected | failed
    row_count: int = 0
    validation_errors: str | None = None  # JSON-encoded list
    raw_snapshot_dir: str | None = None
    mode: str = Field(
        default="quick", sa_column_kwargs={"server_default": "quick"}
    )  # quick | mine | complete


class RawScrape(SQLModel, table=True):
    """Raw HTML per fetched page, retained for a configurable window
    (`Settings.raw_retention_days`) to make debugging a format drift fast
    without waiting for the bug to recur."""

    id: int | None = Field(default=None, primary_key=True)
    scrape_run_id: int = Field(foreign_key="scraperun.id")
    page_number: int
    fetched_at: datetime
    html: str


class SquadMember(SQLModel, table=True):
    """One player the owner holds, or once held.

    Removal is a soft delete — `sold_at` is stamped and the row stays. Two
    reasons: the later trends work needs realized profit and loss, which a
    hard delete destroys; and adding those columns now avoids a second
    migration over data that would by then be unrecoverable.

    "Current squad" is therefore *always* `sold_at IS NULL`. Any query that
    forgets that filter silently counts sold players.

    `purchase_price` is what the owner actually paid, not the market value at
    the time (spec D-02) — in the real game you bid, so the two routinely
    differ, and a builder that assumes market price computes a wrong budget.

    `role` is where the player is standing right now — one column per
    player, so appearing on both the pitch and the bench is unrepresentable
    rather than merely refused. Removal resets it to `'reserve'` alongside
    stamping `sold_at`, so a re-added player never returns holding a slot in
    a formation that may no longer exist.
    """

    id: int | None = Field(default=None, primary_key=True)
    player_id: int = Field(foreign_key="player.id", index=True)
    purchase_price: int
    acquired_on: date
    sale_price: int | None = None
    sold_at: datetime | None = None
    role: str = Field(
        default="reserve", sa_column_kwargs={"server_default": "reserve"}
    )  # starter | bench | reserve


class SquadSetup(SQLModel, table=True):
    """The shape the squad is arranged in. Exactly one row, `id=1`, created
    and seeded by migration 0007 — the same singleton pattern as
    `LeagueSettings`, and read the same way.

    The formation is stored rather than derived from who is assigned,
    because an empty slot is the whole point of a squad still being built:
    three defenders in a 4-4-2 with one slot open must stay distinguishable
    from a 3-x-x shape. The formation defines the slot grid; `SquadMember.role`
    says who is standing in it.
    """

    id: int = Field(default=1, primary_key=True)
    formation: str


class LeagueSettings(SQLModel, table=True):
    """Which Premium features the owner's league has switched on.

    Exactly one row, `id=1`, created and seeded by migration 0005 from the
    `core/config.py` defaults. From then on **this row is the only thing
    read at runtime** — those config fields are the seed and nothing more.

    The alternative, nullable overrides falling back to config, puts two
    sources behind one question and makes "which one won?" a real support
    question in a single-user app that should never have one.
    """

    id: int = Field(default=1, primary_key=True)
    premium_formations_enabled: bool
    premium_bench_enabled: bool


class PlayerGameweekPoints(SQLModel, table=True):
    """One player's points for one jornada, from the source's own
    per-jornada page rather than inferred as the difference between two
    cumulative daily snapshots.

    `is_provisional` marks the jornada currently being played — its points
    still move. It is set only for the *current* season's active week; a
    completed season's highest week is final, not in progress.
    """

    season_year: int = Field(primary_key=True)
    week: int = Field(primary_key=True)
    player_id: int = Field(foreign_key="player.id", primary_key=True)
    points: int
    is_provisional: bool = False
    scrape_run_id: int = Field(foreign_key="scraperun.id")


class PlayerSeasonStats(SQLModel, table=True):
    """Deep per-player season statistics. `raw_fields` keeps the verbatim
    payload so the parser's interpretation is never the only copy."""

    season_year: int = Field(primary_key=True)
    player_id: int = Field(foreign_key="player.id", primary_key=True)

    matches_played: int
    total_points: int
    average_points: float
    market_value: int
    ideal_formation_count: int | None = None

    goals: int | None = None
    goals_pts: int
    goal_assist: int | None = None
    goal_assist_pts: int
    offtarget_att_assist: int | None = None
    offtarget_att_assist_pts: int
    total_scoring_att: int | None = None
    total_scoring_att_pts: int
    pen_area_entries: int | None = None
    pen_area_entries_pts: int
    penalty_won: int | None = None
    penalty_won_pts: int
    penalty_save: int | None = None
    penalty_save_pts: int
    penalty_failed: int | None = None
    penalty_failed_pts: int
    penalty_conceded: int | None = None
    penalty_conceded_pts: int
    saves: int | None = None
    saves_pts: int
    effective_clearance: int | None = None
    effective_clearance_pts: int
    own_goals: int | None = None
    own_goals_pts: int
    goals_conceded: int | None = None
    goals_conceded_pts: int
    won_contest: int | None = None
    won_contest_pts: int
    ball_recovery: int | None = None
    ball_recovery_pts: int
    poss_lost_all: int | None = None
    poss_lost_all_pts: int
    yellow_card: int | None = None
    yellow_card_pts: int
    second_yellow_card: int | None = None
    second_yellow_card_pts: int
    red_card: int | None = None
    red_card_pts: int
    mins_played: int | None = None
    mins_played_pts: int
    marca_points: int | None = None
    marca_points_pts: int

    raw_fields: str
    scrape_run_id: int = Field(foreign_key="scraperun.id")


class SourcePrediction(SQLModel, table=True):
    """The source site's own model outputs, stored as reference fields
    only — never presented as this app's output (docs/SCRAPING-POLICY.md,
    and ANALYTICS-04's commitment to computing our own).

    `source` is one column rather than a kind plus a bucket because the
    market page publishes four distinct lists and a player can appear in
    more than one:
    `points | market_top_risers | market_top_fallers |
     market_possible_risers | market_possible_fallers`
    """

    as_of: date = Field(primary_key=True)
    source: str = Field(primary_key=True)
    player_id: int = Field(foreign_key="player.id", primary_key=True)
    value: float
    raw_fields: str
    scrape_run_id: int = Field(foreign_key="scraperun.id")


class DatasetRun(SQLModel, table=True):
    """One dataset's outcome within a scrape run.

    `ScrapeRun` has a single status, which was right when a run meant one
    page. A refresh now covers five datasets that fail independently, and
    collapsing them into one status is how a partial failure becomes
    invisible — the condition that let the 2026-08-10 outage run eleven
    days.

    `status`: success | failed | rejected | not_published | skipped
    """

    id: int | None = Field(default=None, primary_key=True)
    scrape_run_id: int = Field(foreign_key="scraperun.id", index=True)
    dataset: str
    status: str = "running"
    row_count: int = 0
    skipped_count: int = 0
    season_year: int | None = None
    errors: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class WatchlistEntry(SQLModel, table=True):
    """One player the owner is keeping an eye on (DETAIL-04).

    Membership is a set, so the player id *is* the key — a duplicate entry is
    impossible by schema rather than by check. Removal is a real delete:
    unlike `SquadMember`, whose sold rows carry realized profit and loss, a
    dropped watchlist entry holds nothing worth keeping.
    """

    player_id: int = Field(foreign_key="player.id", primary_key=True)
    added_at: datetime


class Fixture(SQLModel, table=True):
    """One LaLiga match, upserted on every refresh and never discarded
    (INGEST-04, restored 2026-09-27 by migration 0013).

    The source publishes only a rolling five-jornada window, so the full
    season is knowable only by watching it go past — the same property as
    `PlayerSnapshot`. Readers: TRANSFER-03's fixture difficulty
    (`core/fixture_difficulty.py`) and Phase 10's expected-points model.

    `matchday` is the real jornada (parsed from the source's `round`), not
    the window slot the source also calls `matchday`. Team names are the
    market scrape's vocabulary, so they join to `Player.team` directly;
    `*_team_id` are the source's own ids, kept as the stable key.

    `*_difficulty` is the **source's** per-side label, stored as a reference
    field only — this project computes its own difficulty.

    `season_year` — the season the kickoff falls in (`core.seasons.season_of`);
    `matchday` repeats every season, so every reader filters on both.
    """

    fixture_id: int = Field(primary_key=True)  # the source's own id
    matchday: int = Field(index=True)
    season_year: int = Field(index=True)
    kickoff_utc: datetime
    kickoff_confirmed: bool  # derived per jornada at parse time
    is_final: bool = False
    home_team: str
    away_team: str
    home_team_id: int | None = None
    away_team_id: int | None = None
    home_difficulty: str | None = None
    away_difficulty: str | None = None
    scraped_at: datetime


class ExternalMatch(SQLModel, table=True):
    """One LaLiga fixture as an external source reports it — result, team
    match statistics and betting odds (INGEST-09/10). Phase 10's
    expected-points model reads this.

    **Keyed by the ordered pairing within a season**, not by date: in a
    double round-robin each (home, away) pair meets exactly once a season,
    while dates move when a match is postponed. The same row therefore goes
    from `scheduled` (from the coming-round file, pre-match odds only) to
    `played` (from the season file, result + closing odds) in place.

    Team columns hold **canonical** club names (`core/external_teams.py`),
    equal to `Player.team` for clubs in the current roster; the source's own
    spelling is kept beside them. Odds are raw decimal prices, stored
    exactly as published; probabilities are *derived on read* by
    `core/odds.py`, so a better de-margining method never needs a backfill.

    `kickoff_at` is UTC, and naive on read like every datetime here — see
    `storage.db.as_utc`.
    """

    source: str = Field(primary_key=True)  # "football-data"
    season_year: int = Field(primary_key=True)
    home_team: str = Field(primary_key=True)
    away_team: str = Field(primary_key=True)

    match_date: date = Field(index=True)
    kickoff_at: datetime | None = None
    status: str  # scheduled | played
    source_home_team: str
    source_away_team: str

    home_goals: int | None = None
    away_goals: int | None = None
    home_xg: float | None = None
    away_xg: float | None = None
    home_shots: int | None = None
    away_shots: int | None = None
    home_shots_on_target: int | None = None
    away_shots_on_target: int | None = None

    # Market-average decimal odds, pre-match (as last seen before kickoff)…
    odds_home: float | None = None
    odds_draw: float | None = None
    odds_away: float | None = None
    odds_over25: float | None = None
    odds_under25: float | None = None
    # …and at closing, published only once the match is played.
    closing_odds_home: float | None = None
    closing_odds_draw: float | None = None
    closing_odds_away: float | None = None
    closing_odds_over25: float | None = None
    closing_odds_under25: float | None = None

    raw_fields: str
    scrape_run_id: int = Field(foreign_key="scraperun.id")
    updated_at: datetime


class MarketPrediction(SQLModel, table=True):
    """One of *our* next-market-update predictions (MODEL-01), and — once
    the next snapshot is captured — what actually happened (MODEL-03).

    Frozen once its outcome exists: only a date with no later snapshot may
    be regenerated. `retroactive` marks a prediction computed after the
    update it predicts (the first run backfills every past snapshot date);
    the track record never merges those with live calls.

    `scoring` is `exact` when the next snapshot is one day later (its own
    published move *is* the predicted update) and `interval` when the gap is
    longer (cumulative change, direction only, `outcome_gap_days` recorded).
    """

    made_on: date = Field(primary_key=True)
    player_id: int = Field(foreign_key="player.id", primary_key=True)
    model_version: str = Field(primary_key=True)
    predicted_pct: float
    direction: str  # rise | fall | flat
    confidence: str  # strong | moderate | weak
    inputs: str  # JSON: every term the prediction was built from
    generated_at: datetime
    retroactive: bool = False
    outcome_as_of: date | None = None
    outcome_gap_days: int | None = None
    actual_pct: float | None = None
    actual_direction: str | None = None
    scoring: str | None = None  # exact | interval
    hit: bool | None = None


class ExpectedPointsPrediction(SQLModel, table=True):
    """One of *our* expected-points predictions (MODEL-02) for one player in
    one jornada, kept so it can be scored against `PlayerGameweekPoints`
    once the jornada is played (MODEL-03).

    **Frozen at kickoff.** A refresh may rewrite a prediction only while its
    jornada has not started (`locks_at`, the jornada's first kickoff, is in
    the future — or unknown and no points exist yet). After that the row is
    history: a prediction revised once lineups are out would flatter the
    track record.

    `basis` names what the value was built from (`form`, `form+starter`,
    `form+odds`, `form+starter+odds`, `no_fixture`) — deliberately not the
    market model's strong/moderate/weak confidence vocabulary. `inputs` is
    the JSON of every input and term (ANALYTICS-05).
    """

    season_year: int = Field(primary_key=True)
    jornada: int = Field(primary_key=True)
    player_id: int = Field(foreign_key="player.id", primary_key=True)
    model_version: str = Field(primary_key=True)
    predicted: float
    basis: str
    inputs: str
    fixture_id: int | None = None
    opponent: str | None = None
    is_home: bool | None = None
    locks_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PlayerMarketDaily(SQLModel, table=True):
    """The source's own day-by-day market value (player page). `PlayerSnapshot`
    stays 'what our refresh saw'; this is the gap-free series models read."""

    season_year: int = Field(primary_key=True)
    day: date = Field(primary_key=True)
    player_id: int = Field(foreign_key="player.id", primary_key=True)
    market_value: int
    delta: int | None = None
    scrape_run_id: int = Field(foreign_key="scraperun.id")


class PlayerMatchStats(SQLModel, table=True):
    """One player's line for one jornada, from his page. `appearance` is
    inferred from minutes (`core.player_pages.appearance`)."""

    season_year: int = Field(primary_key=True)
    week: int = Field(primary_key=True)
    player_id: int = Field(foreign_key="player.id", primary_key=True)
    minutes: int
    points: int
    appearance: str  # start | sub | dnp
    components: str  # JSON of the source's stats dict, verbatim
    scrape_run_id: int = Field(foreign_key="scraperun.id")


class ModelReport(SQLModel, table=True):
    """A stored JSON report from one of this app's own validation harnesses
    — currently `storage.verdict_backtest`'s walk-forward check that each
    verdict label beats chance (Plan C, spec success criterion 3).

    One row per named report (`name` is the primary key — e.g.
    `"verdict-validation"`); `write_report` upserts in place rather than
    historizing, since only the latest run is ever read.
    """

    name: str = Field(primary_key=True)
    generated_at: datetime
    payload: str  # JSON


class PlayerPageFetch(SQLModel, table=True):
    """Last attempt per player — drives resume order and the weekly sweep."""

    player_id: int = Field(foreign_key="player.id", primary_key=True)
    fetched_at: datetime
    status: str  # ok | gap
    error: str | None = None
    #: The highest finished current-season week when the last *ok* fetch
    #: ran. That page is authoritative for every week up to it: a week it
    #: had no row for (injured, unregistered) is not a gap. A gap fetch
    #: leaves it unchanged.
    weeks_checked_through: int | None = None
