import { apiFetch } from "./client";

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
}

export interface PlayersResponse {
  as_of: string | null;
  players: PlayerRow[];
}

export function fetchPlayers(): Promise<PlayersResponse> {
  return apiFetch<PlayersResponse>("/players");
}
