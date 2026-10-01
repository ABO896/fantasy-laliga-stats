import { apiFetch } from "./client";
import type { MarketPrediction } from "./market-model";

/** ANALYTICS-01…07 for one player. Every block carries its inputs and its
 * window (ANALYTICS-05); a null block means there is not enough data. */
export interface FormBlock {
  value: number | null;
  formAvg: number | null;
  baselineAvg: number | null;
  window: number;
  baselineWindow: number;
  formJornadas: number;
  baselineJornadas: number;
  recentPoints: number[];
}

export interface ConsistencyBlock {
  value: number | null;
  mean: number | null;
  sd: number | null;
  window: number;
  jornadas: number;
  points: number[];
}

export interface MomentumBlock {
  windowDays: number;
  fromDate: string | null;
  toDate: string | null;
  fromValue: number | null;
  toValue: number | null;
  days: number | null;
  pct: number | null;
  ratePerDay: number | null;
  direction: "up" | "down" | "flat" | null;
}

export interface PowerBlock {
  score: number;
  powerPpg: number;
  qualityPpg: number;
  rate: number;
  rateMatches: number;
  prior: number;
  priorSource: "last_season" | "position";
  calibration: { a: number; c: number };
  availability: string | null;
  availabilityFactor: number;
  recentJornadas: number;
  referencePpg: number;
}

export interface ValuationBlock {
  marketValue: number | null;
  fairValue: number | null;
  gapPct: number | null;
  reason: string | null;
  fit: {
    intercept: number;
    slope: number;
    n: number;
    rSquared: number | null;
    pooled: boolean;
  } | null;
}

export interface PlayerAnalytics {
  playerId: number;
  form: FormBlock | null;
  consistency: ConsistencyBlock | null;
  momentum: MomentumBlock[];
  power: PowerBlock | null;
  valuation: ValuationBlock | null;
  economy: { score: number | null; basis: string } | null;
  marketPrediction: MarketPrediction | null;
}

export const DEFAULT_WINDOWS = [1, 7, 14, 30];

export function fetchPlayerAnalytics(
  playerId: number,
  windows: number[] = DEFAULT_WINDOWS,
): Promise<PlayerAnalytics> {
  return apiFetch<PlayerAnalytics>(`/players/${playerId}/analytics?windows=${windows.join(",")}`);
}
