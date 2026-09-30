import { STAT_LABELS } from "../components/player-detail/SeasonStatsTable";

/** Mirrors the backend's `core/season_stats_schema.SEASON_RECORD_FIELDS`:
 * the 21 `STAT_PAIRS` counters (in the same order, since `STAT_LABELS` was
 * built by iterating that same list) plus the three summary totals. Kept
 * as a literal list rather than derived at runtime from an API call, the
 * same way the backend's own allowlist is a literal tuple — this is a
 * fixed schema, not live data. */
export const SEASON_RECORD_FIELDS = [
  ...Object.keys(STAT_LABELS),
  "totalPoints",
  "averagePoints",
  "matchesPlayed",
] as const;

const SUMMARY_LABELS: Record<string, string> = {
  totalPoints: "Total points",
  averagePoints: "Average points",
  matchesPlayed: "Matches played",
};

/** A field added to the schema later still resolves — badly labelled
 * rather than missing, the same fallback `SeasonStatsTable` uses. */
export function statLabel(field: string): string {
  return STAT_LABELS[field] ?? SUMMARY_LABELS[field] ?? field;
}

/** Flat alphabetical by label — `SeasonStatsTable` has no category
 * grouping to mirror, so per spec this falls back to alphabetical. */
export const STAT_OPTIONS = SEASON_RECORD_FIELDS.map((field) => ({
  field,
  label: statLabel(field),
})).sort((a, b) => a.label.localeCompare(b.label));
