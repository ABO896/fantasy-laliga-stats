import type { PlayerDetailResponse, SeasonStatsRow } from "../api-client/player-detail";
import { formatEuroAbbreviated, formatNullable, formatProbability } from "./format";
import { seasonLabel } from "./seasons";

/** Which side a row favours, or `null` when it is a tie, when either side is
 * absent, or when the statistic has no unambiguous "better" at all. */
export type CompareSide = "a" | "b" | null;

export interface CompareRow {
  label: string;
  a: string;
  b: string;
  better: CompareSide;
}

type Direction = "higher" | "lower" | null;

/** Ranks only when both values exist. An absent value is an unknown, not a
 * zero — treating a missing price-per-point as worst (or best) would claim
 * something the data does not say. */
function pickBetter(a: number | null, b: number | null, direction: Direction): CompareSide {
  if (direction === null || a === null || b === null || a === b) return null;
  const aWins = direction === "higher" ? a > b : a < b;
  return aWins ? "a" : "b";
}

interface Metric {
  label: string;
  value: (p: PlayerDetailResponse) => number | string | null;
  format?: (v: number) => string;
  direction: Direction;
}

function seasonFor(p: PlayerDetailResponse, seasonYear: number): SeasonStatsRow | null {
  return p.seasonStats.find((s) => s.seasonYear === seasonYear) ?? null;
}

function latestSeasonYear(players: (PlayerDetailResponse | null)[]): number | null {
  const years = players.flatMap((p) => p?.seasonStats.map((s) => s.seasonYear) ?? []);
  return years.length > 0 ? Math.max(...years) : null;
}

function signedEuro(v: number): string {
  return `${v > 0 ? "+" : ""}${formatEuroAbbreviated(v)}`;
}

/**
 * DETAIL-06. The side-by-side table's rows, as plain strings plus which side
 * each favours — kept out of the component so the ranking rules are tested
 * directly. Market value, price change, availability and next opponent are
 * shown but never ranked: whether cheaper or rising is "better" depends on
 * whether the owner is buying or holding, and this table does not know.
 */
export function buildCompareRows(
  a: PlayerDetailResponse | null,
  b: PlayerDetailResponse | null,
): CompareRow[] {
  const metrics: Metric[] = [
    {
      label: "Market value",
      value: (p) => p.latest?.marketValue ?? null,
      format: formatEuroAbbreviated,
      direction: null,
    },
    {
      label: "Price change",
      value: (p) => p.latest?.priceChangeAbs ?? null,
      format: signedEuro,
      direction: null,
    },
    { label: "Points", value: (p) => p.latest?.points ?? null, direction: "higher" },
    {
      label: "€ / point",
      value: (p) => p.latest?.pricePerPoint ?? null,
      format: formatEuroAbbreviated,
      direction: "lower",
    },
    {
      label: "Starter %",
      value: (p) => p.latest?.starterProbability ?? null,
      format: (v) => formatProbability(v),
      direction: "higher",
    },
    { label: "Availability", value: (p) => p.latest?.availabilityStatus ?? null, direction: null },
    { label: "Next opponent", value: (p) => p.latest?.nextOpponent ?? null, direction: null },
  ];

  if (a?.predictions.points !== undefined || b?.predictions.points !== undefined) {
    metrics.push({
      label: "Predicted points (source)",
      value: (p) => p.predictions.points ?? null,
      format: (v) => v.toFixed(1).replace(/\.0$/, ""),
      direction: "higher",
    });
  }

  // One season for both columns, the most recent either player has, so the
  // two cells in a row always describe the same period.
  const season = latestSeasonYear([a, b]);
  if (season !== null) {
    const label = seasonLabel(season);
    metrics.push(
      {
        label: `Matches played (${label})`,
        value: (p) => seasonFor(p, season)?.matchesPlayed ?? null,
        direction: "higher",
      },
      {
        label: `Total points (${label})`,
        value: (p) => seasonFor(p, season)?.totalPoints ?? null,
        direction: "higher",
      },
      {
        label: `Average points (${label})`,
        value: (p) => seasonFor(p, season)?.averagePoints ?? null,
        format: (v) => v.toFixed(2),
        direction: "higher",
      },
    );
  }

  return metrics.map((metric) => {
    const raw = (p: PlayerDetailResponse | null) => (p ? metric.value(p) : null);
    const render = (v: number | string | null) =>
      formatNullable(v, (x) =>
        typeof x === "number" && metric.format ? metric.format(x) : String(x),
      );
    const va = raw(a);
    const vb = raw(b);
    return {
      label: metric.label,
      a: render(va),
      b: render(vb),
      better: pickBetter(
        typeof va === "number" ? va : null,
        typeof vb === "number" ? vb : null,
        metric.direction,
      ),
    };
  });
}
