import { apiFetch } from "./client";
import type { VerdictLabel } from "./verdict";

/** Phase 11 — /api/transfers/*. Everything is computed server-side; the page
 * renders what it is given and never re-derives a score, a bid or a rule. */

export type PriceBasis = "marketValue" | "idealBid" | "maxBid" | "ourIdealBid" | "ourMaxBid";
export type Position = "POR" | "DEF" | "MED" | "DEL";
export type ConfidenceLabel = "high" | "medium" | "low";

export interface TransferFixture {
  matchday: number;
  kickoffUtc: string;
  kickoffConfirmed: boolean;
  opponent: string;
  isHome: boolean;
  difficulty: number;
  label: string;
}

export interface BidNumbers {
  ourIdeal: number;
  ourMax: number;
  sourceIdeal: number | null;
  sourceMax: number | null;
  inputs: Record<string, number | string | null>;
}

export interface TransferPlayer {
  playerId: number;
  name: string;
  team: string;
  position: Position;
  owned: boolean | null;
  marketValue: number;
  availability: string;
  starterProbability: number | null;
  recentJornadas: number;
  powerScore: number | null;
  economyScore: number | null;
  fairValue: number | null;
  valuationGapPct: number | null;
  predictedPct: number | null;
  predictionConfidence: string | null;
  expectedReturn: number | null;
  expectedPoints: number | null;
  expectedPointsUsed: boolean;
  backwardPpg: number | null;
  minutesFactor: number;
  fixtureMultiplier: number;
  fixtureDataAvailable: boolean;
  fixtures: TransferFixture[];
  fixtureDriver: TransferFixture | null;
  efficiency: number | null;
  holdValue: number | null;
  evidence: number;
  bids: BidNumbers;
  /** Plan C Task 5/6 — null only when this player has no live verdict
   * (no snapshot/inputs yet), same condition as a null `powerScore`. */
  verdict: { label: VerdictLabel; reason: string } | null;
}

export interface DatasetFreshness {
  dataset: string;
  lastSuccessAt: string | null;
  ageDays: number | null;
  factor: number;
  note: string | null;
}

export interface Freshness {
  confidence: number;
  label: ConfidenceLabel;
  reasons: string[];
  datasets: DatasetFreshness[];
}

export interface Envelope {
  serverTime: string;
  asOf: string | null;
  jornadas: { requested: number; window: number[]; spreadOver: number };
  ceiling: { max: number; basis: PriceBasis } | null;
  expectedPointsUsed: boolean;
  freshness: Freshness;
}

export interface Signal {
  name: "points" | "value" | "efficiency" | "fixtures" | "valuation" | "availability";
  text: string;
  contribution: number | null;
}

export interface Move {
  kind: "swap" | "add";
  sell: TransferPlayer | null;
  buy: TransferPlayer;
  gain: number;
  signals: Signal[];
  confidence: number;
  confidenceLabel: ConfidenceLabel;
  confidenceReasons: string[];
  feasibleFormations: string[];
  /** Plan C Task 6 — the server's own "Sell X (label) → buy Y (label)" /
   * "Add Y (label)" sentence; the card's heading leads with this rather
   * than recomposing it from `sell`/`buy` names and labels client-side. */
  phrase: string;
}

export interface SuggestionsResponse extends Envelope {
  squadSize: number;
  maxSquadSize: number;
  unassessedMembers: string[];
  moves: Move[];
}

export interface BargainPlayer extends TransferPlayer {
  forwardFairValue: number;
  forwardGapPct: number;
}

export interface BargainsResponse extends Envelope {
  affordableOnly: boolean;
  players: BargainPlayer[];
}

export interface BestResponse extends Envelope {
  position: Position;
  affordableOnly: boolean;
  ceilingMissing: boolean;
  players: TransferPlayer[];
}

export interface BidRow {
  playerId: number;
  name: string;
  team: string;
  position: Position;
  marketValue: number;
  availability: string;
  ourIdeal: number;
  ourMax: number;
  sourceIdeal: number | null;
  sourceMax: number | null;
  inputs: Record<string, number | string | null>;
}

export interface BidsResponse {
  serverTime: string;
  asOf: string | null;
  freshness: Freshness;
  players: BidRow[];
}

export interface PlayerBidResponse extends BidRow {
  asOf: string | null;
  freshness: Freshness;
}

/** The owner's price ceiling — BROWSE-05's `max` and `basis`, never a
 * derived budget. `max === null` means no ceiling. */
export interface TransferQuery {
  n: number;
  max: number | null;
  basis: PriceBasis;
}

export function transferParams(
  q: TransferQuery,
  extra: Record<string, string | number | boolean | null | undefined> = {},
): string {
  const params = new URLSearchParams();
  params.set("n", String(q.n));
  if (q.max !== null) {
    params.set("max", String(q.max));
    params.set("basis", q.basis);
  }
  for (const [key, value] of Object.entries(extra)) {
    if (value !== null && value !== undefined) params.set(key, String(value));
  }
  return params.toString();
}

export function fetchSuggestions(q: TransferQuery): Promise<SuggestionsResponse> {
  return apiFetch<SuggestionsResponse>(`/transfers/suggestions?${transferParams(q)}`);
}

export function fetchBargains(q: TransferQuery, affordableOnly: boolean): Promise<BargainsResponse> {
  return apiFetch<BargainsResponse>(`/transfers/bargains?${transferParams(q, { affordableOnly })}`);
}

export function fetchBest(
  q: TransferQuery,
  position: Position,
  affordableOnly: boolean,
): Promise<BestResponse> {
  return apiFetch<BestResponse>(
    `/transfers/best?${transferParams(q, { position, affordableOnly })}`,
  );
}

export function fetchBids(position: Position | null): Promise<BidsResponse> {
  const query = position ? `?position=${position}` : "";
  return apiFetch<BidsResponse>(`/transfers/bids${query}`);
}

export function fetchPlayerBid(playerId: number): Promise<PlayerBidResponse> {
  return apiFetch<PlayerBidResponse>(`/transfers/bids/${playerId}`);
}
