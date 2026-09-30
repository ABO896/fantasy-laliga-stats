# Fantasy LaLiga Stats

A personal, locally-run web app for LaLiga Fantasy (DAZN). It holds more about every player
than any single public source shows and turns that into concrete moves, so your squad is always
the strongest and best-value one available to you. The ambition is a better analiticafantasy,
built for one person.

What it does:

- **Player browser** — every LaLiga Fantasy player with market data, points, starter probability,
  our own Power Score, Economy Score and expected points (xP), sortable and filterable, with a
  watchlist and a two-player compare view.
- **Player pages** — market-value history, points per jornada, form, value momentum, consistency
  and valuation, each showing its inputs and window.
- **League stats** — per-jornada scores, streaks, records, leaderboards, and a market-model tab
  with predicted risers and fallers, their live track record, and where our prediction and the
  source's disagree.
- **Squad** — your squad on a pitch, with squad value and points over time.
- **Transfers** — ranked sell → buy suggestions that are always legal under the game's rules,
  bargains, the best players per position, and our own ideal and maximum bids. Confidence drops
  visibly when the data is stale.

Every model scores itself against what actually happened, and the app shows the track record.

Design notes, plans and session history are kept locally and are not part of this repository.
[`docs/RULES-LALIGA-FANTASY.md`](docs/RULES-LALIGA-FANTASY.md) (the game's rules, from the
operator) and [`docs/SCRAPING-POLICY.md`](docs/SCRAPING-POLICY.md) are.

## Stack

- **Backend / scraper:** Python 3.12+, FastAPI, SQLModel, Alembic, SQLite, Playwright + BeautifulSoup4
- **Frontend:** React 19, Vite, TypeScript, TanStack Query/Table, Tailwind CSS v4
- **Package managers:** `uv` (Python), `npm` (frontend)

## First-time setup

```bash
# Install uv (Python package/venv manager) if you don't have it
brew install uv

# Install Python dependencies (creates .venv/)
uv sync

# Install Playwright's Chromium browser (required for the scraper)
uv run playwright install chromium

# Install frontend dependencies
npm --prefix web install

# Copy the example env file and adjust if needed (defaults work out of the box)
cp .env.example .env

# Apply the database schema (SQLite file created at ./data/fantasy.db)
uv run alembic upgrade head
```

## Running locally

```bash
make dev     # starts both the FastAPI backend (127.0.0.1:8000) and the Vite dev server (127.0.0.1:5173)
```

Then open http://127.0.0.1:5173/ (http://localhost:5173/ works too).

If a page says it can't reach the API, the backend isn't running — check that
`make dev` is still up, or start the backend alone with `make api`. The two
halves are independent: the frontend serves and renders fine on its own, and
only the data is missing.

Other commands:

```bash
make api      # backend only
make web      # frontend only
make test     # backend (pytest) + frontend (vitest) test suites
make scrape   # run a manual scrape (python -m scraper.run)
```

## Scraping policy

This app reads `analiticafantasy.com` (players, market, jornada points, season stats,
predictions, fixture calendar) and `football-data.co.uk` (LaLiga results, team stats and odds),
on demand only. The self-imposed access limits (identifying User-Agent, sequential jittered
requests, capped backoff, a 403/429 is terminal, no proxy rotation) are documented in
`docs/SCRAPING-POLICY.md` — read it before changing anything in `scraper/`. Scraped data stays on
the machine that fetched it; none of it is committed here.

## Refreshing data

There is no schedule. Open the app, and if the data is stale the banner says so and offers a
"Refresh now" button; `make scrape` does the same thing from a terminal. Both call the one
`python -m scraper.run` entrypoint — there is never a second scrape path.

The scheduled `launchd` agent was removed on 2026-08-22. It had run unattended during an
eleven-day absence, failed silently the whole time, and cost five days of snapshots that cannot
be recovered. A scrape that only runs while someone is looking at the app cannot fail unseen.
The trade-off is accepted: history now has gaps where the app went unopened.

## Squad builder

The `/squad` page lets you build and manage your real LaLiga Fantasy squad: add and remove
players at the price you actually paid, see which starting-XI formations your current squad
could field, and get a refusal naming the shortfall and a remedy whenever a change would exceed
the 24-player cap.

The squad also carries one current starting XI on a pitch: eleven slots in your squad's stored
formation, a bench strip (behind the league's premium-bench toggle), and the rest of the squad in
a rail. Click a player, then click a slot — they move onto the pitch or swap with whoever is
there. Every assignment saves immediately; there's no save button and no gameweek to pick. A
slot can sit empty — the header just says the XI is incomplete.

Two things about the official rules are easy to assume wrongly, so they're worth stating
plainly: LaLiga Fantasy has **no fixed budget cap** — spending power is your cash balance plus
20% of your squad's market value, not a fixed ceiling — and there is **no per-club cap and no
squad-level position quota**. Position rules apply only to the starting XI, not to who you're
allowed to own.

The player browser filters by price against a selectable basis — market value (the default),
`Ideal bid (Analítica)`, or `Max bid (Analítica)` — so you can set a price ceiling per session
instead of the app tracking a cash balance. That balance was dropped 2026-08-21 along with the
budget ledger, because the game makes a cash balance underivable from outside the official app. Every rule value the squad builder
enforces — the cap, spending power, formation requirements — comes from
`docs/RULES-LALIGA-FANTASY.md` via `core/rules_data/laliga_fantasy.json`, never hardcoded in
validation code.

## Project structure

```
scraper/    # source adapters (fetch + parse), the daily refresh entrypoint
core/       # pure business logic — parsing, transforms, validation (no I/O)
storage/    # SQLModel models, database engine/session, repository functions
api/        # FastAPI app, routes, dependencies
migrations/ # Alembic revisions — the only thing allowed to create/alter schema
web/        # React + Vite frontend
tests/      # pytest (backend/scraper) — Vitest tests live alongside their components in web/
            # captured source pages are not committed; see tests/fixtures/README.md
```
