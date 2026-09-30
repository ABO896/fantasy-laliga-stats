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

export interface TrackRecordResponse {
  modelVersion: string;
  ours: { live: RecordBucket; retroactive: RecordBucket };
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

export function fetchTrackRecord(): Promise<TrackRecordResponse> {
  return apiFetch<TrackRecordResponse>("/models/market/track-record");
}

export function fetchDivergence(): Promise<DivergenceResponse> {
  return apiFetch<DivergenceResponse>("/models/market/divergence");
}
