"""FastAPI application entrypoint.

Binds to loopback only by default (`Settings.api_host`, default
`127.0.0.1`) — this is a single-user local tool per PROJECT.md constraints,
and a wildcard bind would expose the dataset to anyone on the same network.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import (
    analytics,
    expected_points,
    fixture_odds,
    fixtures,
    health,
    league_settings,
    market_model,
    meta,
    player_detail,
    players,
    squad,
    stats,
    transfers,
    verdict,
    watchlist,
)
from core.config import get_settings

app = FastAPI(title="Fantasy LaLiga Stats")

# Both spellings of the loopback address, because they are the same server
# but *different origins* to a browser, and the owner opens this app by
# typing a URL. Allowing only one produces the most confusing failure the
# app can have: the page loads perfectly, every request inside it is blocked,
# and the UI reports the API as unreachable while the API is running fine.
# Vite is bound to 127.0.0.1, but nothing stops a bookmark or a typed
# `localhost:5173` from resolving there anyway.
DEV_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=DEV_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta.router, prefix="/api")
app.include_router(players.router, prefix="/api")
app.include_router(player_detail.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(squad.router, prefix="/api")
app.include_router(league_settings.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(watchlist.router, prefix="/api")
app.include_router(fixtures.router, prefix="/api")
app.include_router(fixture_odds.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(market_model.router, prefix="/api")
app.include_router(expected_points.router, prefix="/api")
app.include_router(transfers.router, prefix="/api")
app.include_router(verdict.router, prefix="/api")


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
