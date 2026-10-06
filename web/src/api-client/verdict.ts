import { apiFetch } from "./client";

/** Plan C's ten-label vocabulary, in `core.verdict.LABELS` priority order —
 * the order every verdict-sorted surface (the player table's column) must
 * follow, never alphabetical. */
export const VERDICT_LABELS = [
  "Unavailable",
  "Unproven",
  "Sell high",
  "Elite",
  "Bargain",
  "Rising",
  "Rotation risk",
  "Overpriced",
  "Avoid",
  "Fair price",
] as const;

export type VerdictLabel = (typeof VERDICT_LABELS)[number];

/** The compact shape `/api/players` and `/api/squad` rows carry. */
export interface VerdictSummary {
  label: VerdictLabel;
  tags: string[];
  confidence: "high" | "medium" | "low";
}

/** `core.personal.PersonalLine`, read against the owner's current squad. */
export interface PersonalLine {
  kind: "keep" | "sell" | "upgrade" | "replace" | "no_improvement";
  text: string;
  gain: number | null;
  cost: number | null;
  otherPlayerId: number | null;
  otherName: string | null;
  overCeilingBy: number | null;
}

/** What the walk-forward harness found for this player's label, if a
 * report has been stored (`storage/verdict_backtest.py --write`). */
export interface ValidationSummary {
  label: VerdictLabel;
  beatsChance: boolean;
  hitRate: number | null;
  n: number;
}

export interface PlayerVerdict {
  playerId: number;
  label: VerdictLabel;
  tags: string[];
  reason: string;
  confidence: "high" | "medium" | "low";
  deciding: Record<string, number | string | null>;
  disabledLabels: string[];
  personal: PersonalLine | null;
  validation: ValidationSummary | null;
}

/** GET /players/{id}/verdict. `max` is BROWSE-05's price ceiling (euros),
 * carried through to the personal line the same way the rest of the app
 * carries it — omitted or `null` means no ceiling. */
export function fetchPlayerVerdict(playerId: number, max?: number | null): Promise<PlayerVerdict> {
  const query = max !== null && max !== undefined ? `?max=${max}` : "";
  return apiFetch<PlayerVerdict>(`/players/${playerId}/verdict${query}`);
}

/** One label's row in the stored walk-forward report. */
export interface ValidationLabelRow {
  label: VerdictLabel;
  /** The forward claim this label is scored against: "points",
   * "points_per_m", "price_pct", "minutes" — or "" for a label with no
   * forward claim (Unavailable/Unproven/Fair price), reported by count only. */
  metric: string;
  n: number;
  players: number;
  hitRate: number | null;
  baseRate: number | null;
  meanDiff: number | null;
  ciLow: number | null;
  ciHigh: number | null;
  beatsChance: boolean;
}

/** GET /models/verdict/validation. `generatedAt: null` with an empty
 * `labels` array is the documented shape before the harness has ever been
 * run with `--write` — every other field is only present once it has. */
export interface ValidationReport {
  generatedAt: string | null;
  season?: number;
  dates?: string[];
  thresholds?: Record<string, number>;
  disabled?: string[];
  labels: ValidationLabelRow[];
  notes?: string[];
}

export function fetchVerdictValidation(): Promise<ValidationReport> {
  return apiFetch<ValidationReport>("/models/verdict/validation");
}
