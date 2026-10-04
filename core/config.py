"""Application configuration, loaded from environment variables / .env.

Every key here is mirrored into `.env.example` with its default value so a
fresh checkout documents exactly what can be tuned without reading code.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Scraper ---
    scrape_target_url: str = "https://www.analiticafantasy.com/fantasy-la-liga/puja-ideal"
    jornada_base_url: str = (
        "https://www.analiticafantasy.com/puntuaciones-fantasy-jornada/la-liga-fantasy"
    )
    season_stats_url: str = "https://www.analiticafantasy.com/fantasy-la-liga/estadisticas"
    points_prediction_url: str = "https://www.analiticafantasy.com/fantasy-la-liga/predicciones"
    market_prediction_url: str = (
        "https://www.analiticafantasy.com/fantasy-la-liga/prediccion-de-mercado"
    )
    #: The fixture calendar (INGEST-04). CDN-prerendered, so a plain httpx
    #: GET carries the whole payload — no browser. Restored 2026-09-27 for
    #: TRANSFER-03's fixture difficulty.
    calendar_target_url: str = "https://www.analiticafantasy.com/la-liga/calendario-predictor"
    #: One player's whole season (daily market values + per-jornada match
    #: rows). `{slug}` is `Player.external_id`.
    player_page_url_template: str = (
        "https://www.analiticafantasy.com/jugadores/{slug}/fantasy/la-liga-fantasy"
    )
    #: Hard ceiling on player-page requests in one refresh — see
    #: `backfill_request_budget` for the analogous jornada-side cap.
    player_pages_max_requests: int = 700
    #: This source's own pacing for player pages, independent of the
    #: market/jornada scrapers' delay — see `fetch_page`'s own docstring on
    #: why a per-source pace, not a shared one.
    player_pages_min_delay_seconds: float = 1.0
    player_pages_max_delay_seconds: float = 2.0
    #: Re-fetch a player who looks fully up to date after this many days
    #: anyway — a periodic sweep catches a gap `needs_fetch`'s other
    #: conditions miss (e.g. a corrected historical row).
    player_pages_sweep_days: int = 7
    #: The hour (Europe/Madrid) the source's daily market update has
    #: typically landed by, used to compute `expected_last_day`.
    market_update_hour: int = 8
    #: Age in days of the last successful Complete refresh after which
    #: Health suggests running another.
    complete_refresh_stale_days: int = 3
    #: Below this many fixtures the calendar parse is rejected. The window
    #: normally holds 50 (five jornadas of ten).
    min_fixture_count: int = 30
    #: The season the market scrape runs against. Only this season's active
    #: week is ever provisional; every earlier season is closed.
    current_season_year: int = 2026
    #: Hard ceiling on requests in one backfill, per the policy's
    #: runaway-protection rule. 2025/26 has 36 jornadas.
    backfill_request_budget: int = 60
    min_row_count: int = 300
    max_null_rate: float = 0.05
    price_min_eur: int = 0
    price_max_eur: int = 200_000_000
    rows_per_page: int = 100
    raw_retention_days: int = 7
    raw_snapshot_root: str = "./data/raw_scrapes"
    user_agent: str = (
        "FantasyLaLigaStats/0.1 "
        "(personal, non-commercial, single-user tool; +https://github.com/ABO896/fantasy-laliga-stats)"
    )

    # --- External football data (INGEST-09/10) ---
    # football-data.co.uk: keyless CSVs, LaLiga odds + team match stats.
    # See docs/SCRAPING-POLICY.md. Off switch rather than a key: the source
    # needs none, and turning it off makes the dataset `skipped`, not failed.
    football_data_enabled: bool = True
    football_data_base_url: str = "https://football-data.co.uk"
    #: This source's own pacing — at least this many seconds (jittered up
    #: to double) before each of its requests. A refresh makes two.
    football_data_min_delay_seconds: float = 2.0

    # --- Storage ---
    db_path: str = "./data/fantasy.db"

    # --- League ---
    # Premium-league formations (3-3-4, 3-6-1, 4-2-4, 4-6-0, 5-2-3) exist only
    # in a Premium league whose admin has the feature on. Default off is the
    # conservative direction: wrongly on would call a forward-less squad
    # fieldable when the league scores it zero.
    premium_formations_enabled: bool = False
    # The bench is a Premium feature the league admin toggles, so this is
    # not folded into `premium_formations_enabled`.
    #
    # These two fields are the **seed only**. Migration 0005 copies them into
    # the single-row `leaguesettings` table, which is what every runtime
    # reader consults from then on — changing a default here does nothing to
    # an already-migrated database. Toggle them at /settings.
    premium_bench_enabled: bool = False

    # --- Budget ---
    # How long a confirmed balance stays trustworthy before the UI starts
    # saying so. Two weeks is roughly two gameweeks of unrecorded points
    # income, which is when drift becomes big enough to change a decision.
    balance_stale_after_days: int = 14

    # --- API ---
    # Loopback only, by design — this is a single-user local tool (PROJECT.md
    # constraints). Never change the default to a wildcard bind (0.0.0.0).
    api_host: str = "127.0.0.1"
    api_port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
