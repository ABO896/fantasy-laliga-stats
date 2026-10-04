import { apiFetch } from "./client";

const API_BASE_URL = "http://127.0.0.1:8000/api";

export type ScrapeMode = "quick" | "mine" | "complete";

export interface ScrapeRunDto {
  id: number;
  startedAt: string;
  finishedAt: string | null;
  status: "running" | "success" | "rejected" | "failed";
  rowCount: number;
  validationErrors: string[];
  mode: ScrapeMode;
}

/** Coverage of the `player_pages` dataset (Task 5/T-05): how many tracked
 * players have a complete page, how many have gaps, and the oldest
 * `lastDay` among them — ISO-8601 date, or `null` with zero tracked
 * players. */
export interface PlayerPagesCoverage {
  players: number;
  complete: number;
  withGaps: number;
  /** Never fetched, or missing a finished week's match row — the gaps a
   * complete refresh exists to fix (unlike the one-day price lag). */
  withMatchGaps: number;
  oldestLastDay: string | null;
}

export interface HealthResponse {
  lastSuccessfulRun: ScrapeRunDto | null;
  /** The last run that completed in `complete` mode — `null` when none
   * ever has. Distinct from `lastSuccessfulRun`, which can be a `quick`
   * or `mine` run. */
  lastCompleteRun: ScrapeRunDto | null;
  isStale: boolean;
  hoursSinceLastSuccess: number | null;
  /** The market update the server judged staleness against — ISO-8601, in
   * Madrid time. Sent rather than recomputed here so the browser's clock and
   * timezone can never disagree with the verdict beside it. */
  marketUpdatedAt: string;
  recentRuns: ScrapeRunDto[];
  playerPages: PlayerPagesCoverage;
  /** Server-computed judgement call: a `complete` refresh is worth
   * running — the last one is stale, missing entirely, or some player
   * has match gaps (`playerPages.withMatchGaps`). */
  suggestComplete: boolean;
}

export function fetchHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health");
}

/** Thrown when `POST /scrape/trigger` returns 409 — a run is already in
 * the `running` state (the single-flight guard, T-05-01). Callers use
 * `instanceof` to show "already in progress" rather than a generic
 * failure. */
export class ScrapeAlreadyRunningError extends Error {}

/** Not routed through `apiFetch` — the 409 single-flight response needs
 * its own handling distinct from a generic failed request. `mode`
 * defaults to `quick`, matching today's refresh exactly — no player-page
 * request, no new dataset run row. */
export async function triggerScrape(mode: ScrapeMode = "quick"): Promise<{ scrapeRunId: number }> {
  const response = await fetch(`${API_BASE_URL}/scrape/trigger?mode=${mode}`, { method: "POST" });

  if (response.status === 409) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new ScrapeAlreadyRunningError(body.detail ?? "A scrape is already running");
  }
  if (!response.ok) {
    throw new Error(`Request to /scrape/trigger failed with status ${response.status}`);
  }
  return (await response.json()) as { scrapeRunId: number };
}
