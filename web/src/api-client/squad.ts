import { API_BASE_URL, apiFetch } from "./client";
import type { GameweekPointsRow } from "./player-detail";
import type { PowerRank } from "./players";

export type SquadRole = "starter" | "bench" | "reserve";

export interface SquadMemberRow {
  playerId: number;
  name: string;
  position: string;
  purchasePrice: number;
  marketValue: number | null;
  effectiveValue: number;
  /** Where this player is standing right now. */
  role: SquadRole;
  /** available | injured | doubtful | suspended — a badge, never a refusal. */
  availability: string;
  /** ANALYTICS-06/07 — see `PlayerRow`. Comparing same-position members'
   * Power is how the squad page answers "who should I start". */
  powerScore?: number | null;
  economyScore?: number | null;
  /** MODEL-02 — see `PlayerRow`. Same-position xP side by side answers
   * "who do I start" for the next jornada. */
  expectedPoints?: number | null;
  expectedPointsBasis?: string | null;
  /** Plan B Task 7 — see `PlayerRow`. Comparing same-position members' Power
   * rank and points value is "who should I start". */
  powerRank?: PowerRank | null;
  reliabilityClass?: string | null;
  pStart?: number | null;
  pointsValuePct?: number | null;
  outlookPct?: number | null;
  outlookDirection?: "rise" | "flat" | "fall" | null;
  dropRisk?: boolean | null;
  xptsWindow?: number | null;
}

export interface SquadViolation {
  rule: string;
  actual: number;
  limit: number;
  message: string;
}

export interface SquadSummary {
  squadSize: number;
  maxSquadSize: number;
  squadValue: number;
  isLegal: boolean;
  canFieldXi: boolean;
  positionCounts: Record<string, number>;
  feasibleFormations: string[];
  missingForXi: Record<string, number>;
  /** Which formation `missingForXi` counts towards; null once an XI is reachable. */
  nearestFormation: string | null;
  memberPlayerIds: number[];
  violations: SquadViolation[];
  /** The stored shape. Not derivable from who is assigned: an empty slot in a
   * 4-4-2 must stay distinguishable from a 3-x-x formation. */
  formation: string;
  /** Its per-position counts, looked up in the *full* rule set — a shape
   * stored while premium formations were on still draws after they go off.
   * Null only if the rules file no longer knows the stored name at all. */
  formationShape: Record<string, number> | null;
  /** Whether the league still allows that shape. False means the pitch draws
   * it, says so, and refuses to move anything until a legal shape is chosen. */
  formationAvailable: boolean;
  allowedFormations: string[];
  /** Every allowed formation's per-position counts, served rather than parsed:
   * a name is not a rule, and a mis-parse would demote the wrong players into
   * an under-filled XI the server would then accept. */
  formationShapes: Record<string, Record<string, number>>;
  benchEnabled: boolean;
}

export interface SquadResponse {
  members: SquadMemberRow[];
  summary: SquadSummary;
}

/** Every squad mutation answers with the whole payload, so a caller never
 * has to refetch to learn the new arrangement. */
export type SquadMutationResponse = SquadResponse;

/**
 * Carries the server's structured refusal (spec D-05) instead of flattening it
 * to a status code. The UI renders `violation.message` — it never composes its
 * own explanation, because the rules live server-side only.
 */
export class SquadRuleError extends Error {
  violation: SquadViolation;

  constructor(violation: SquadViolation) {
    super(violation.message);
    this.name = "SquadRuleError";
    this.violation = violation;
  }
}

async function mutate<T>(path: string, init: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });

  if (response.status === 409) {
    const body = (await response.json()) as { detail: SquadViolation };
    throw new SquadRuleError(body.detail);
  }

  if (!response.ok) {
    throw new Error(`Request to ${path} failed with status ${response.status}`);
  }

  return (await response.json()) as T;
}

export function fetchSquad(): Promise<SquadResponse> {
  return apiFetch<SquadResponse>("/squad");
}

export interface SquadValuePoint {
  asOf: string;
  squadValue: number;
}

/** SQUAD-04. Kept off `SquadResponse` deliberately — that payload is
 * refetched on every pitch rearrangement, and this aggregation has no
 * reason to run that often. */
export interface SquadHistoryResponse {
  valueHistory: SquadValuePoint[];
  pointsHistory: GameweekPointsRow[];
  seasonWeekRanges: Record<string, number>;
}

export function fetchSquadHistory(): Promise<SquadHistoryResponse> {
  return apiFetch<SquadHistoryResponse>("/squad/history");
}

export function addSquadPlayer(
  playerId: number,
  purchasePrice: number,
): Promise<SquadMutationResponse> {
  return mutate<SquadMutationResponse>("/squad/players", {
    method: "POST",
    body: JSON.stringify({ playerId, purchasePrice }),
  });
}

export function removeSquadPlayer(
  playerId: number,
  salePrice?: number,
): Promise<SquadMutationResponse> {
  const query = salePrice === undefined ? "" : `?salePrice=${salePrice}`;
  return mutate<SquadMutationResponse>(`/squad/players/${playerId}${query}`, {
    method: "DELETE",
  });
}

/** Saves the whole arrangement. A 409 arrives as `SquadRuleError` carrying
 * the server's own sentence, which the pitch renders verbatim. */
export function saveXi(
  formation: string,
  starterIds: number[],
  benchIds: number[],
): Promise<SquadResponse> {
  return mutate<SquadResponse>("/squad/lineup", {
    method: "PUT",
    body: JSON.stringify({ formation, starterIds, benchIds }),
  });
}
