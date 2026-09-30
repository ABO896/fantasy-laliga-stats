# Scraping Policy — analiticafantasy.com

The durable, in-repo record of what was found about this site, what was decided,
who decided it, and how the scraper behaves.

**Revised 2026-08-22** from an allowlist to a denylist. The previous version
named two permitted pages and required a dated amendment for any third. That
made the policy a veto over product scope — it was cited twice as a reason to
cut or not build something, which is not what an access-conduct document is for.
See "Standing decision" below.

## What this document does and does not govern

This document constrains **how the scraper behaves** — its manner, its footprint,
and what it does with what it collects.

It does **not** constrain what the project may build. A feature is never cut,
deferred, or narrowed because of this policy. If a feature needs data from a page
this project does not yet fetch, the answer is to fetch that page, not to drop
the feature. Nothing in here should ever appear in a design document as an
argument against building something.

## Sources

Every page on `analiticafantasy.com` is in scope except what the denylist below
excludes. The pages fetched today are recorded here because their structure
was verified by hand and that finding is worth keeping — not because the list is
exhaustive or closed.

### 1. Player data — `/fantasy-la-liga/puja-ideal`

Verified directly (via `curl` + raw-HTML `grep`, not an AI-summarized fetch) on
2026-08-04: the page is server-rendered (Next.js App Router, `__next_f`
flight-data markers present), but only its first page (10 of ~370 players)
arrives in a plain HTTP GET response. Pagination ("Siguiente" button, "Filas
por página" selector showing "Página 1 de 37") is client-side/JS-driven with
no discoverable URL query parameter — `?page=2`, `?pagina=2`, `?p=2`, and
`?rows=100` were all directly tested and returned byte-identical page-1
content. Full-roster retrieval therefore requires a real browser (Playwright)
driving the page the way a human visitor would, not a raw GET.

### 2. Fixture calendar — `/la-liga/calendario-predictor`

**Added 2026-08-08. ~~Cut 2026-08-22~~ — restored 2026-09-27.** ~~See
`docs/superpowers/specs/2026-08-22-lineups-cut-and-the-pitch-view-design.md`. Its only consumer
was the lineup deadline, which was cut the same day; the parser
(`scraper/sources/analiticafantasy_calendar.py`) and its fixture were deleted with it (commit
`1d9e52f`). The page is unfetched today and out of scope until re-added — which, if it happens,
is a revert of that commit for TRANSFER-03 (fixture-difficulty-adjusted ratings), not new work.~~
Fetched again as the `fixtures` dataset of every refresh, for TRANSFER-03 and MODEL-02 — see
`docs/superpowers/specs/2026-09-27-fixture-calendar-restore-design.md`. One GET per refresh
through the shared `scraper/http.fetch_page`, with the same User-Agent and conduct as every other
page. robots.txt was re-checked on 2026-09-27 before the re-probe: the page is still allowed and
`/api/` is still disallowed and untouched. The source's `difficulty` label is stored as a
reference field only; the app computes its own fixture difficulty, per Data handling below.

**Two findings from the 2026-09-27 re-probe:** the cell's `matchday.matchday` is the *slot* in the
five-jornada window, not the jornada — the jornada is the trailing number of `round` — and the
window is not guaranteed contiguous (it held jornadas 6, 8, 9, 10 and 11). It now also carries the
most recent partly-played jornada, with finished matches marked `isFinal`.

Verified directly on 2026-08-08 (`curl` + raw-HTML `grep`): the fixture data is
present in the raw HTML of a plain GET, inside the page's `__next_f` flight
data. **No browser is required** — unlike `puja-ideal`, this page needs no
hydration and no pagination, so it is fetched with `httpx` alone. Response
headers show `x-nextjs-prerender: 1` and a CDN cache hit.

The page publishes a rolling five-jornada window, and LaLiga confirms kickoff
times roughly four jornadas ahead; beyond that, every fixture in a matchday
carries one identical placeholder timestamp.

## robots.txt review

Fetched: 2026-08-04, via `curl https://www.analiticafantasy.com/robots.txt`.
Re-checked 2026-08-08 — unchanged.

- `User-agent: *` is allowed `/` generally (and the same for `Googlebot-News`).
- Explicit disallow list: `/api/` (with two named exceptions,
  `/api/sitemap-index.xml` and `/api/sitemap/`), plus admin, login, account,
  and payment paths.
- Neither `puja-ideal` nor `calendario-predictor` is disallowed.

The prohibition this project acts on is therefore contractual (Terms and
Conditions), not a robots.txt-level block.

## Terms and Conditions review

Fetched: 2026-08-04, from `https://analiticafantasy.com/terminos-y-condiciones`.

Verbatim scraping prohibition (Spanish, as published on the site):

> "Participar en actividades de extracción, recolección o minería de datos
> (data scraping) sin autorización expresa."

English rendering:

> "Engaging in data extraction, collection, or data mining (data scraping)
> activities without express authorization."

Separately, the same Terms prohibit commercializing and republishing site
material:

> "Vender, sublicenciar o comercializar de cualquier forma el material del
> sitio web." — Selling, sublicensing, or commercializing in any way the
> website's material.

> "Publicar material del sitio web en cualquier otro medio sin autorización."
> — Publishing website material in any other medium without authorization.

This is an explicit, unambiguous prohibition on scraping, distinct from and in
addition to the robots.txt findings above. It is not page-specific, so it was
never the case that adding pages one at a time reduced it.

## Standing decision

**Decision:** Scrape `analiticafantasy.com` as broadly as this project's
features require, accepting the confirmed ToS prohibition as a consciously
accepted risk. No page-by-page approval. No volume ceiling framed as
politeness.

**Decided by:** the repo owner, sole user of this local install.
**Date:** 2026-08-22, superseding the 2026-08-06 decision and its 2026-08-08
amendment, both of which this replaces rather than extends.

**Owner's words on the record:** *"Update the scraping policy to be more
liberal, I dont want it to ever be the limiting factor, i take responsibility
for all the legal side etc… and morally its fine because its only for my
personal use."*

**Prior words, 2026-08-08:** *"Im okay with updating the scraping policy to
allow more, its for personal use. I take responsibility."* Recorded here
because the same decision was made twice under a document that kept
re-narrowing it — which is the defect this revision fixes.

**Rationale on the record:** a private, non-commercial, single-user,
never-redistributed tool. The moral argument the owner makes rests on the
personal-use premise, and that premise is load-bearing: it is what the Data
handling section below protects, and it is the one thing here that is not
liberalized.

**What is honestly against, and is accepted rather than argued away:** the
site's Terms prohibit this, in terms that do not care about volume or page
count. Broadening scope does not change the nature of that risk, but it does
mean the project is no longer able to describe itself as minimal. Access can be
revoked or blocked at any time — the conduct rules below exist so that if it
happens, it happens cleanly and is not fought.

## Conduct rules

These are correctness requirements for the scraper, not optional hardening.
They are deliberately few, and none of them limits what can be collected.

**Non-adversarial access.** These keep the project out of a cat-and-mouse
dynamic it should not enter, and are the limits the owner's grant of authority
does not extend to — they concern the site's access controls rather than the
owner's own risk:

- [ ] A `403`, `429`, or bot-challenge response is a **terminal "blocked"
      outcome** to record and surface — never retried into. Retrying against a
      block escalates it and turns a soft signal into a hard ban.
- [ ] No proxy rotation, no IP cycling, no browser-fingerprint spoofing, and no
      circumvention of bot protection of any kind. If the site decides to block
      this tool, it stays blocked.
- [ ] An honest, identifying User-Agent naming this tool and a contact address
      — never a spoofed string pretending to be a different client. Implemented
      as `Settings.user_agent`.
- [ ] Honour robots.txt's disallow list, including `/api/`, and its two named
      sitemap exceptions. The previous policy was *stricter* than robots here,
      forbidding the sitemap that robots explicitly allows; that extra
      strictness is dropped, and the disallow list itself is not.

**Runaway protection.** Not politeness — these stop a bug in this project from
becoming a flood, which protects the scrape as much as the origin:

- [ ] Requests are issued sequentially, never in parallel, with a jittered
      delay between them.
- [ ] Every scrape run has a bounded request budget and terminates rather than
      looping. A pagination loop that does not converge is a failure to report,
      not a reason to keep fetching.

**Frequency.** The daily-run cap is removed. Scrape as often as a feature needs
— on a schedule, on demand from the UI, or during development — subject to the
two runaway-protection rules above.

## Data handling

**This section is not liberalized, and it is the reason the rest could be.** The
owner's justification is personal use; these clauses are what make that true
rather than merely stated.

- Scraped data, and any derivative computed from it (including this project's
  own price/point efficiency scoring), stays inside this single-user local
  install. It is never published, redistributed, shared, or commercialized.
  This mirrors the Terms' separate prohibitions on selling, sublicensing,
  commercializing, and republishing site material — prohibitions this project
  complies with fully, unlike the scraping clause it knowingly does not.
- The site's own proprietary "Puja ideal" ("ideal bid") column is stored as a
  reference field only. This app computes its own price/point efficiency metric
  independently from raw price and points data, rather than presenting the
  site's derived score as its own.

## Review

Reviewed and recorded: 2026-08-06. Amended 2026-08-08. **Revised 2026-08-22** —
allowlist replaced by denylist, per-page approval removed, daily-run cap
removed, non-veto clause added. **Updated 2026-09-28** — §2 (fixture calendar)
restored; football-data.co.uk added below as a second counterparty.

Re-check this document if the **counterparty** changes — a different source site
introduces a different robots.txt, different Terms, and a decision that has not
been made. Adding pages on `analiticafantasy.com` does not require a re-check,
and does not require an entry here.

---

# Other counterparties

Each external source is its own counterparty with its own robots.txt, terms, decision and rate
limit. Nothing above — including the 2026-08-22 standing decision to accept analiticafantasy's
ToS risk — carries over to any of them. The shared conduct rules (identifying User-Agent,
sequential jittered requests, 403/429/challenge terminal, no circumvention, data never leaves this
install) apply to every one.

## football-data.co.uk — LaLiga odds, results, team match stats

**Added 2026-09-27** (INGEST-09/10; design in
`docs/superpowers/specs/2026-09-27-external-football-data-design.md`).

- **Fetched:** `https://football-data.co.uk/mmz4281/{yyYY}/SP1.csv` (the season so far) and
  `https://football-data.co.uk/fixtures.csv` (the coming round, all leagues; only `Div == SP1`
  rows are kept). Plain CSV, no browser, no key. Note the canonical host has no `www` — the `www`
  host answers 302.
- **robots.txt** (fetched 2026-09-27): `User-agent: *` with an empty `Disallow:` — everything
  allowed — plus named AI-training crawlers (GPTBot, ClaudeBot, Google-Extended, …) disallowed
  entirely. This tool identifies as itself, trains nothing, and is none of those.
- **Terms** (`/data.php`, 2026-09-27), verbatim: *"What's more, it's all FREE, however its use is
  intended for private individuals only, NOT commercial or data training products using automated
  bots/scrapers/AI."* Read as: private, non-commercial use permitted; commercial or AI-training
  products that harvest it are not. This project is the former. `/disclaimer.php` concerns
  betting offers only.
- **Decision (autonomous, 2026-09-27, pending owner review):** in scope. Unlike analiticafantasy
  this is **not** an accepted-risk decision — the published terms permit this use. If the owner
  reads "NOT … using automated bots" as covering any automated download, set
  `FOOTBALL_DATA_ENABLED=false`; the dataset then records `skipped` and nothing else changes.
- **Rate limit (its own):** two requests per refresh, one per season on backfill, each preceded by
  `Settings.football_data_min_delay_seconds` (default 2 s) jittered up to double. The site
  advertises `x-ws-ratelimit-limit: 1000`; we use well under 1 % of it. The files update twice a
  week (Sunday and Wednesday nights), so a more frequent refresh gains nothing.
- **Failure mode:** degrades to absent. Its `DatasetRun` records the failure; the refresh's own
  status is unaffected.
- **Data handling:** as for every source — stays in this install, never redistributed.

## Evaluated and excluded — 2026-09-27

Recorded so the next person does not re-probe them. Each was checked with this tool's own
User-Agent, a handful of requests at most.

| Site | Why excluded |
|---|---|
| FotMob | Terms prohibit use of their data "for any purpose including scraping" without written consent. |
| FBref / Sports Reference | Lost its Opta advanced data (xG, xA) on 2026-01-20, so the reason to use it is gone; and `fbref.com/robots.txt` itself answered a Cloudflare interactive challenge (`sports-reference.com/bot-traffic.html`: 403). A challenge is terminal under the conduct rules. |
| Understat | `robots.txt` is `User-agent: *` / `Disallow: /`. |
| Sofascore | Terms prohibit automated access, scraping and crawling; `robots.txt` answered 403. |
| WhoScored | Terms prohibit scraping; anti-bot protected. |
| Key-based aggregators (Big Balls Data, Bzzoiro) | Upstream provenance undisclosed; player metrics match Understat's exact set, so likely a re-publication of a source that disallows automated access. Not adopted. |

The `soccerdata` Python library (Apache-2.0) was also considered: its licence covers its code,
not the sites it reads, and every site it would reach for us is excluded above except
football-data.co.uk, which needs no library.
