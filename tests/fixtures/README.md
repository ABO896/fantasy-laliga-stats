# Test fixtures

The parser and pipeline tests run against pages captured from the live sources, so they never
touch the network. Those captures are third-party content and are **not committed** — a fresh
clone has only this file and `challenge-page.html` (a hand-written stand-in for a bot
challenge).

Tests that need a missing capture are **skipped with the file name in the reason**, not failed,
so `make test` stays green on a fresh clone. To run them, capture the pages yourself (one polite
request each, following `docs/SCRAPING-POLICY.md`) and save them under these names:

| File | Source |
|---|---|
| `puja-ideal-page1.html` | analiticafantasy.com `/fantasy-la-liga/puja-ideal` |
| `calendario-predictor.html` | analiticafantasy.com fixture calendar (`calendar_target_url` in `core/config.py`) |
| `phase7/jornada-*.html` | analiticafantasy.com per-jornada points (see the test names for season and week) |
| `phase7/estadisticas-2025.html` | analiticafantasy.com season statistics, 2025/26 |
| `phase7/predicciones.html` | analiticafantasy.com points predictions |
| `phase7/prediccion-de-mercado.html` | analiticafantasy.com market prediction |
| `external/football-data-SP1-*.csv` | football-data.co.uk LaLiga season CSV (`SP1.csv`) for 2025/26 and 2026/27 |
| `external/football-data-fixtures-*.csv` | football-data.co.uk `fixtures.csv`, with and without LaLiga rows |

Some assertions pin values from the specific captures used during development (player counts,
named players), so a fresh capture can fail a handful of them for data reasons, not code reasons.
