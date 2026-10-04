import { apiFetch } from "./client";

/** Plan B Task 7 — the compact shape `powerRank` takes on list/squad rows:
 * just enough to render "#2", never the percentile (that's the analytics
 * payload's fuller `RankBlock`, see `api-client/analytics.ts`). */
export interface PowerRank {
  rank: number;
  of: number;
}

export interface PlayerRow {
  playerId: number;
  externalId: string;
  name: string;
  team: string;
  position: string;
  marketValue: number;
  idealBid: number | null;
  maxBid: number | null;
  priceChangeAbs: number | null;
  priceChangePct: number | null;
  points: number;
  pricePerPoint: number | null;
  starterProbability: number | null;
  availabilityStatus: string;
  nextOpponent: string | null;
  /** ANALYTICS-06 — 0–100, our holistic fantasy-quality score. Optional so
   * fixtures predating it still type-check; null means not enough data. */
  powerScore?: number | null;
  /** ANALYTICS-07 — 0–100 percentile of Power priced (value for money). */
  economyScore?: number | null;
  /** MODEL-02 — expected points next jornada (0 on a blank jornada); null
   * when no prediction is stored yet. */
  expectedPoints?: number | null;
  /** What xP was built from: form, form+starter, form+odds,
   * form+starter+odds, or no_fixture. */
  expectedPointsBasis?: string | null;
  /** Plan B Task 7 — reliability, points value, 7-day outlook and Power's
   * position rank, computed live for today. Optional so fixtures predating
   * it still type-check; null means the player has no live inputs yet
   * (no snapshot and no price at all). */
  powerRank?: PowerRank | null;
  reliabilityClass?: string | null;
  /** Reliability's shrunk starter probability next match, 0–1. */
  pStart?: number | null;
  /** Percentile (0–100) within position of points value per €. */
  pointsValuePct?: number | null;
  /** Expected 7-day price move, signed %. */
  outlookPct?: number | null;
  outlookDirection?: "rise" | "flat" | "fall" | null;
  dropRisk?: boolean | null;
  /** Expected points over the look-ahead window (spec's `horizon`). */
  xptsWindow?: number | null;
}

export interface PlayersResponse {
  as_of: string | null;
  players: PlayerRow[];
}

export function fetchPlayers(): Promise<PlayersResponse> {
  return apiFetch<PlayersResponse>("/players");
}
