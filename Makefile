.PHONY: dev api web test scrape scrape-mine scrape-full backfill

dev:
	@echo "Starting FastAPI (127.0.0.1:8000) and Vite dev server (127.0.0.1:5173)..."
	@( \
	  trap 'kill 0' EXIT; \
	  uv run uvicorn api.app:app --host 127.0.0.1 --port 8000 --reload & \
	  npm --prefix web run dev & \
	  wait \
	)

api:
	uv run uvicorn api.app:app --host 127.0.0.1 --port 8000 --reload

web:
	npm --prefix web run dev

test:
	uv run pytest tests/ -q
	npm --prefix web run test -- --run

scrape:
	uv run python -m scraper.run

scrape-mine:
	uv run python -m scraper.run --mine

scrape-full:
	uv run python -m scraper.run --full

backfill:
	uv run python -m scraper.backfill --season 2025
