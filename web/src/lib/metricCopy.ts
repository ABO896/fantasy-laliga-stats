/** Owner-facing copy for every metric on the player page, plus the shared
 * percentile-to-plain-word banding and the rank-line formatter. One module
 * so the nine metrics' titles/meaning/why/bands stay consistent wherever
 * they're rendered (MetricCard and friends). */

export type MetricKey =
  | "verdict"
  | "power"
  | "pointsValue"
  | "outlook"
  | "reliability"
  | "xp"
  | "form"
  | "consistency"
  | "momentum";

export interface Band {
  below: number;
  word: string;
}

export interface MetricCopy {
  /** "Power", "Points value", "7-day price outlook", … */
  title: string;
  /** What high vs low means, one line. */
  meaning: string;
  /** Why it matters for winning, one line. */
  why: string;
  /** Ascending; last band catches the rest. Omit to use DEFAULT_BANDS; set
   * `null` for a metric that has no percentile bands at all because its word
   * comes from its own vocabulary (verdict's label, reliability's class,
   * outlook's direction) rather than from where it sits within its position. */
  bands?: Band[] | null;
}

export const METRIC_COPY: Record<MetricKey, MetricCopy> = {
  verdict: {
    title: "Verdict",
    meaning: "The one-word summary of what to do with him, from the inputs below.",
    why: "It turns every number on this page into a decision.",
    bands: null,
  },
  power: {
    title: "Power",
    meaning:
      "Expected points per match right now, from this season's scoring shrunk toward last " +
      "season and adjusted for availability. High = scores a lot when he plays.",
    why: "Points win the league; Power is the best single predictor of them we have.",
  },
  pointsValue: {
    title: "Points value",
    meaning:
      "Expected points over the next 3 jornadas above a cheap regular starter at his " +
      "position, per € of price. High = lots of points for the money.",
    why: "Budget is the constraint; this is where money buys the most points.",
  },
  outlook: {
    title: "7-day price outlook",
    meaning: "Where his market value is expected to go over the next week, with a range.",
    why: "Rising players grow your budget; falling ones shrink it.",
    bands: null,
  },
  reliability: {
    title: "Reliability",
    meaning: "How likely he is to start and to play next match, from his minutes this season.",
    why: "Only players who play score — a bargain on the bench scores nothing.",
    bands: null,
  },
  xp: {
    title: "Expected points",
    meaning:
      "Our forecast of his points in the next jornada, from his scoring rate, starting " +
      "chance and the fixture.",
    why: "It is the next-jornada number to pick your XI on.",
  },
  form: {
    title: "Form",
    meaning:
      "His last 5 jornadas' average against his longer-run average. Positive = scoring " +
      "above his usual.",
    why: "Hot streaks partly continue — and the market prices them in fast.",
  },
  consistency: {
    title: "Consistency",
    meaning: "How steady his scoring is: 100 = the same every week, low = boom or bust.",
    why: "Steady scorers make safer starters; boom-or-bust ones suit captain gambles.",
  },
  momentum: {
    title: "Momentum",
    meaning: "How his market value has moved over recent windows.",
    why: "Momentum tends to persist for a few updates, so it signals when to buy or sell.",
  },
};

/** The default percentile-to-word bands, used by any metric that doesn't
 * define its own in METRIC_COPY (and hasn't opted out with `bands: null`).
 * Ascending; the last entry catches the rest. */
export const DEFAULT_BANDS: Band[] = [
  { below: 20, word: "Very low" },
  { below: 40, word: "Low" },
  { below: 60, word: "Average" },
  { below: 80, word: "High" },
  { below: Infinity, word: "Very high" },
];

/** The plain word for a within-position percentile.
 *
 * A metric with `bands: null` (verdict, reliability, outlook) has no
 * percentile-based word at all — its word is its own vocabulary (the
 * verdict label, the reliability class, the outlook direction) — so this
 * always returns `null` for it, regardless of percentile or `of`. For a
 * banded metric, `of === 1` (no one else at the position to rank against)
 * wins even over a null percentile; otherwise a null percentile has no word. */
export function bandFor(key: MetricKey, percentile: number | null, of?: number): string | null {
  const bands = METRIC_COPY[key].bands;
  if (bands === null) return null;
  if (of === 1) return "Only one at position";
  if (percentile === null) return null;
  const list = bands ?? DEFAULT_BANDS;
  for (const band of list) {
    if (percentile < band.below) return band.word;
  }
  return list[list.length - 1].word;
}

/** `{ rank: 5, of: 190, position: "DEF" }` -> "#5 of 190 DEF"; null -> null. */
export function rankText(
  rank: { rank: number; of: number; position: string } | null,
): string | null {
  if (rank === null) return null;
  return `#${rank.rank} of ${rank.of} ${rank.position}`;
}
