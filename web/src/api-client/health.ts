import { apiFetch } from "./client";

const API_BASE_URL = "http://127.0.0.1:8000/api";

export interface ScrapeRunDto {
  id: number;
  startedAt: string;
  finishedAt: string | null;
  status: "running" | "success" | "rejected" | "failed";
  rowCount: number;
  validationErrors: string[];
}

export interface HealthResponse {
  lastSuccessfulRun: ScrapeRunDto | null;
  isStale: boolean;
  hoursSinceLastSuccess: number | null;
  /** The market update the server judged staleness against — ISO-8601, in
   * Madrid time. Sent rather than recomputed here so the browser's clock and
   * timezone can never disagree with the verdict beside it. */
  marketUpdatedAt: string;
  recentRuns: ScrapeRunDto[];
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
 * its own handling distinct from a generic failed request. */
export async function triggerScrape(): Promise<{ scrapeRunId: number }> {
  const response = await fetch(`${API_BASE_URL}/scrape/trigger`, { method: "POST" });

  if (response.status === 409) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new ScrapeAlreadyRunningError(body.detail ?? "A scrape is already running");
  }
  if (!response.ok) {
    throw new Error(`Request to /scrape/trigger failed with status ${response.status}`);
  }
  return (await response.json()) as { scrapeRunId: number };
}
