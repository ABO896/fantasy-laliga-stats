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

/** Plan B Task 7 — a within-position rank with its percentile (0–100, 100 =
 * best). The list/squad rows carry the lighter `PowerRank` (see
 * `api-client/players.ts`) instead; this fuller shape is only the analytics
 * payload's. */
export interface RankBlock {
  rank: number;
  of: number;
  percentile: number;
}

export interface ReliabilityBlock {
  class: string; // Nailed | Regular | Rotation | Fringe
  pStart: number;
  pPlay: number;
  startShare: number | null;
  playShare: number | null;
  subShare: number | null;
  minutesShare: number | null;
  shrunkStart: number;
  sourceStarter: number | null;
  sourceBlend: number;
  availability: string | null;
  availabilityFactor: number;
  minutesTrend: number | null;
  matches: number;
  appearances: number;
  halfLife: number;
  priorWeight: number;
  prior: { start: number; play: number };
  confidence: "low" | "medium" | "high";
  basis: string; // "matches" | "source-only"
  rank: RankBlock | null;
}

export interface EvidenceBlock {
  matchesWithMinutes: number;
  lastSeasonApps: number;
  ok: boolean;
  reason: string | null;
}

export interface PointsValueBlock {
  value: number | null;
  xpts: number | null;
  replacement: number | null;
  price: number | null;
  cashPerPoint: number;
  /** Jornadas looked ahead (the copy's "next 3"). */
  horizon: number;
  /** Matches inside those jornadas — fewer after a blank, more after a double. */
  matchCount: number;
  matches: { opponent: string; isHome: boolean; xp: number }[];
  reason: string | null;
  rank: RankBlock | null;
}

export interface PriceOutlookBlock {
  expectedPct: number;
  direction: "rise" | "flat" | "fall";
  lower: number;
  upper: number;
  dropRisk: boolean;
  basis: string;
  confidence: "strong" | "moderate" | "weak";
  terms: Record<string, unknown>;
  madeOn: string | null;
  rank: RankBlock | null;
}

/** Plan D Task 1 — the same within-position rank as `RankBlock`, plus the
 * position code so a metric card can print "#5 of 190 DEF" without a
 * second lookup. */
export interface PositionRankBlock extends RankBlock {
  position: string;
}

/** Plan D Task 1 — one entry per metric card, `null` when the player has
 * no value for that metric. */
export interface MetricRanks {
  power: PositionRankBlock | null;
  pointsValue: PositionRankBlock | null;
  outlook: PositionRankBlock | null;
  reliability: PositionRankBlock | null;
  xp: PositionRankBlock | null;
  form: PositionRankBlock | null;
  consistency: PositionRankBlock | null;
  momentum7: PositionRankBlock | null;
}

/** Plan D Task 1 — the xP card's own block: the latest stored jornada's
 * prediction for this player, straight off `ExpectedPointsPrediction`. */
export interface XpCardBlock {
  value: number;
  basis: string;
  jornada: number;
  opponent: string | null;
  isHome: boolean | null;
  terms: Record<string, number> | null;
  coefficients: Record<string, number> | null;
  rate: {
    value: number | null;
    matches: number;
    recentPoints: number[];
    halfLife: number;
    prior: number | null;
    priorSource: "last_season" | "position";
    priorWeight: number;
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
  /** Plan B Task 7 — reliability, points value, 7-day outlook and Power's
   * position rank. Optional so fixtures predating it still type-check; a
   * `null` block means the player has no live inputs (dataThrough is also
   * then null). */
  powerRank?: RankBlock | null;
  reliability?: ReliabilityBlock | null;
  evidence?: EvidenceBlock | null;
  pointsValue?: PointsValueBlock | null;
  priceOutlook?: PriceOutlookBlock | null;
  expectedReturnEur?: number | null;
  inputsConfidence?: "low" | "medium" | "high" | null;
  dataThrough?: { prices: string | null; matches: number | null } | null;
  /** Plan D Task 1 — a within-position rank for every metric card, and the
   * xP card's own block. Both `null` only when the player has no
   * analytics at all. */
  ranks?: MetricRanks | null;
  xp?: XpCardBlock | null;
}

export const DEFAULT_WINDOWS = [1, 7, 14, 30];

export function fetchPlayerAnalytics(
  playerId: number,
  windows: number[] = DEFAULT_WINDOWS,
): Promise<PlayerAnalytics> {
  return apiFetch<PlayerAnalytics>(`/players/${playerId}/analytics?windows=${windows.join(",")}`);
}
