import { apiFetch } from "./client";

/** The market model's own confidence words (MODEL-01). Deliberately not
 * shared with any expected-points vocabulary — the two problems are
 * differently conditioned and must not borrow each other's words. */
export type MarketConfidence = "strong" | "moderate" | "weak";
export type MarketDirection = "rise" | "fall" | "flat";

export interface PredictionInputs {
  asOf: string;
  lastMovePct: number | null;
  previousSnapshot: string | null;
  previousMovePct: number | null;
  accelerationTerm: number | null;
  starterProbability: number | null;
  previousStarterProbability: number | null;
  starterTerm: number | null;
  availabilityChange: string | null;
  availabilityTerm: number | null;
  freshPoints: number | null;
  freshPointsTerm: number | null;
  baseRateFallback?: boolean;
}

export interface PredictionOutcome {
  asOf: string;
  gapDays: number;
  actualPct: number;
  actualDirection: MarketDirection;
  scoring: "exact" | "interval";
  hit: boolean;
}

export interface MarketPrediction {
  madeOn: string;
  modelVersion: string;
  predictedPct: number;
  direction: MarketDirection;
  confidence: MarketConfidence;
  inputs: PredictionInputs;
  retroactive: boolean;
  outcome: PredictionOutcome | null;
}

export interface MarketPredictionRow extends MarketPrediction {
  playerId: number;
  name: string | null;
  team: string | null;
  position: string | null;
  marketValue: number | null;
}

export interface MarketPredictionsResponse {
  madeOn: string | null;
  modelVersion: string;
  predictions: MarketPredictionRow[];
}

export interface HitBucket {
  scored: number;
  hits: number;
  hitRate: number | null;
}

export interface RecordBucket extends HitBucket {
  pending: number;
  byConfidence: Record<MarketConfidence, HitBucket>;
  byScoring: Record<"exact" | "interval", HitBucket>;
}

export interface TrackRecordDay {
  madeOn: string;
  predictions: number;
  scored: number;
  hits: number;
  hitRate: number | null;
  scoring: "exact" | "interval" | null;
  gapDays: number | null;
  retroactive: boolean;
}

export interface NaiveBaseline {
  rule: string;
  hitRate: number | null;
  mae: number | null;
}

/** market-v1's shape carries `days`/`source`; market-v2's carries
 * `intervalCoverage`/`mae`/`naive` instead — the two track records are not
 * the same report, just fetched through the same endpoint. */
export interface TrackRecordResponse {
  modelVersion: string;
  ours: { live: RecordBucket; retroactive: RecordBucket };
  days?: TrackRecordDay[];
  source?: HitBucket & { oursOnSamePlayers: HitBucket };
  intervalCoverage?: number | null;
  mae?: number | null;
  naive?: NaiveBaseline;
}

/** market-v1's shape, with `days`/`source` always present — what
 * `fetchTrackRecord("market-v1")` actually returns. */
export interface V1TrackRecordResponse extends TrackRecordResponse {
  days: TrackRecordDay[];
  source: HitBucket & { oursOnSamePlayers: HitBucket };
}

export interface DivergenceRow {
  playerId: number;
  name: string | null;
  team: string | null;
  position: string | null;
  sourceList: string;
  sourceDirection: "rise" | "fall";
  status: "agree" | "disagree" | "no-call";
  ours: MarketPrediction | null;
}

export interface DivergenceResponse {
  asOf: string | null;
  rows: DivergenceRow[];
  agree: number;
  disagree: number;
  ourCallMissing: number;
}

export function fetchMarketPredictions(): Promise<MarketPredictionsResponse> {
  return apiFetch<MarketPredictionsResponse>("/models/market/predictions");
}

export type MarketModelVersion = "market-v1" | "market-v2";

export function fetchTrackRecord(
  version: MarketModelVersion = "market-v1",
): Promise<TrackRecordResponse> {
  return apiFetch<TrackRecordResponse>(`/models/market/track-record?version=${version}`);
}

export function fetchDivergence(): Promise<DivergenceResponse> {
  return apiFetch<DivergenceResponse>("/models/market/divergence");
}
