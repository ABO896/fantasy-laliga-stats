import { describe, expect, it } from "vitest";
import type { PlayerDetailResponse, SeasonStatsRow } from "../api-client/player-detail";
import { buildCompareRows } from "./compare";

function season(seasonYear: number, overrides: Partial<SeasonStatsRow> = {}): SeasonStatsRow {
  return {
    seasonYear,
    matchesPlayed: 5,
    totalPoints: 30,
    averagePoints: 6,
    marketValue: 0,
    idealFormationCount: null,
    stats: {},
    ...overrides,
  };
}

function player(
  id: number,
  latest: Partial<NonNullable<PlayerDetailResponse["latest"]>> | null = {},
  extra: Partial<PlayerDetailResponse> = {},
): PlayerDetailResponse {
  return {
    asOf: "2026-09-27",
    player: { playerId: id, externalId: `p-${id}`, name: `P${id}`, team: "T", position: "MED" },
    latest:
      latest === null
        ? null
        : {
            marketValue: 10_000_000,
            idealBid: null,
            maxBid: null,
            priceChangeAbs: 0,
            priceChangePct: 0,
            points: 10,
            pricePerPoint: 1_000_000,
            starterProbability: 80,
            availabilityStatus: "available",
            nextOpponent: "RMA",
            ...latest,
          },
    valueHistory: [],
    gameweekPoints: [],
    seasonWeekRanges: {},
    seasonStats: [],
    squad: null,
    predictions: {},
    ...extra,
  };
}

function row(rows: ReturnType<typeof buildCompareRows>, label: string) {
  const found = rows.find((r) => r.label === label);
  if (!found) throw new Error(`no row ${label}: ${rows.map((r) => r.label).join(", ")}`);
  return found;
}

describe("buildCompareRows", () => {
  it("marks the higher points and the lower price per point as better", () => {
    const rows = buildCompareRows(
      player(1, { points: 20, pricePerPoint: 2_000_000 }),
      player(2, { points: 10, pricePerPoint: 1_000_000 }),
    );
    expect(row(rows, "Points").better).toBe("a");
    expect(row(rows, "€ / point").better).toBe("b");
  });

  it("does not rank market value or availability — cheaper is not better per se", () => {
    const rows = buildCompareRows(
      player(1, { marketValue: 5_000_000 }),
      player(2, { marketValue: 50_000_000 }),
    );
    expect(row(rows, "Market value").better).toBeNull();
    expect(row(rows, "Market value").a).toBe("€5M");
    expect(row(rows, "Availability").better).toBeNull();
  });

  it("does not rank a tie", () => {
    const rows = buildCompareRows(player(1), player(2));
    expect(row(rows, "Points").better).toBeNull();
  });

  it("does not rank against an absent value, and renders the absence as a dash", () => {
    const rows = buildCompareRows(player(1, { pricePerPoint: null }), player(2));
    expect(row(rows, "€ / point").a).toBe("—");
    expect(row(rows, "€ / point").better).toBeNull();
  });

  it("renders an empty side as dashes without ranking anything", () => {
    const rows = buildCompareRows(player(1), null);
    expect(row(rows, "Points").b).toBe("—");
    expect(rows.every((r) => r.better === null)).toBe(true);
  });

  it("compares the latest season either player has, labelled with that season", () => {
    const rows = buildCompareRows(
      player(1, {}, { seasonStats: [season(2025, { totalPoints: 200 }), season(2026, { totalPoints: 12 })] }),
      player(2, {}, { seasonStats: [season(2025, { totalPoints: 150 })] }),
    );
    const total = row(rows, "Total points (2026/27)");
    expect(total.a).toBe("12");
    expect(total.b).toBe("—");
    expect(total.better).toBeNull();
  });

  it("only shows the source's prediction when one side has it", () => {
    expect(buildCompareRows(player(1), player(2)).some((r) => r.label.startsWith("Predicted"))).toBe(
      false,
    );
    const rows = buildCompareRows(
      player(1, {}, { predictions: { points: 6.5 } }),
      player(2, {}, { predictions: { points: 4 } }),
    );
    expect(row(rows, "Predicted points (source)").a).toBe("6.5");
    expect(row(rows, "Predicted points (source)").better).toBe("a");
  });
});
