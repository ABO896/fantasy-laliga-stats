import { API_BASE_URL } from "./client";

export interface PlayerIdentity {
  playerId: number;
  externalId: string;
  name: string;
  team: string;
  position: string;
}

export interface LatestSnapshot {
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
}

export interface ValuePoint {
  asOf: string;
  marketValue: number;
}

export interface GameweekPointsRow {
  seasonYear: number;
  week: number;
  points: number;
  isProvisional: boolean;
}

export interface StatPair {
  count: number;
  points: number;
}

export interface SeasonStatsRow {
  seasonYear: number;
  matchesPlayed: number;
  totalPoints: number;
  averagePoints: number;
  marketValue: number;
  idealFormationCount: number | null;
  stats: Record<string, StatPair>;
}

export interface SquadHolding {
  purchasePrice: number;
  acquiredOn: string;
}

export interface PlayerDetailResponse {
  asOf: string | null;
  player: PlayerIdentity;
  latest: LatestSnapshot | null;
  valueHistory: ValuePoint[];
  gameweekPoints: GameweekPointsRow[];
  /** Highest stored jornada per season, league-wide (plan P-03). Keys arrive
   * as strings because they are JSON object keys. */
  seasonWeekRanges: Record<string, number>;
  seasonStats: SeasonStatsRow[];
  squad: SquadHolding | null;
  predictions: Record<string, number>;
}

/** A player id that does not exist is a routing mistake, not a failure — the
 * page says so plainly instead of offering a retry that cannot work. */
export class PlayerNotFoundError extends Error {
  constructor() {
    super("Player not found");
    this.name = "PlayerNotFoundError";
  }
}

/** Bypasses `apiFetch` deliberately, the same way `squad.ts`'s `mutate` does
 * for its 409 case: `apiFetch`'s thrown message embeds the request path
 * (`Request to ${path} failed with status ${response.status}`), and a
 * player id of 404 is entirely plausible among ~642 players — a substring
 * match on "404" would misreport an unrelated 500 as "not found". Checking
 * `response.status` directly is unambiguous. */
export async function fetchPlayerDetail(playerId: number): Promise<PlayerDetailResponse> {
  const path = `/players/${playerId}`;
  const response = await fetch(`${API_BASE_URL}${path}`);

  if (response.status === 404) {
    throw new PlayerNotFoundError();
  }

  if (!response.ok) {
    throw new Error(`Request to ${path} failed with status ${response.status}`);
  }

  return (await response.json()) as PlayerDetailResponse;
}
