import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import SeasonStatsTable from "./SeasonStatsTable";
import type { SeasonStatsRow } from "../../api-client/player-detail";

function season(seasonYear: number, stats: Record<string, { count: number; points: number }>): SeasonStatsRow {
  return {
    seasonYear,
    matchesPlayed: 30,
    totalPoints: 200,
    averagePoints: 6.7,
    marketValue: 1_000_000,
    idealFormationCount: null,
    stats,
  };
}

describe("SeasonStatsTable", () => {
  it("labels every season column, never a bare year", () => {
    render(<SeasonStatsTable seasons={[season(2025, { goals: { count: 18, points: 72 } })]} />);
    expect(screen.getByRole("columnheader", { name: /2025\/26/ })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: /^2025$/ })).not.toBeInTheDocument();
  });

  it("shows each counter with the points it contributed", () => {
    render(<SeasonStatsTable seasons={[season(2025, { goals: { count: 18, points: 72 } })]} />);
    const row = screen.getByRole("row", { name: /goals/i });
    expect(within(row).getByText("18")).toBeInTheDocument();
    expect(within(row).getByText("+72")).toBeInTheDocument();
  });

  it("renders both seasons side by side when both exist", () => {
    render(
      <SeasonStatsTable
        seasons={[
          season(2025, { goals: { count: 18, points: 72 } }),
          season(2026, { goals: { count: 2, points: 8 } }),
        ]}
      />,
    );
    expect(screen.getByRole("columnheader", { name: /2025\/26/ })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /2026\/27/ })).toBeInTheDocument();
  });

  it("renders one column, not an error, when last season is missing", () => {
    render(<SeasonStatsTable seasons={[season(2026, { goals: { count: 2, points: 8 } })]} />);
    expect(screen.getByRole("columnheader", { name: /2026\/27/ })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: /2025\/26/ })).not.toBeInTheDocument();
  });

  it("states the absence when there are no season statistics at all", () => {
    render(<SeasonStatsTable seasons={[]} />);
    expect(screen.getByText(/no season statistics/i)).toBeInTheDocument();
  });

  it("shows a negative contribution with its sign", () => {
    render(
      <SeasonStatsTable seasons={[season(2025, { yellowCard: { count: 6, points: -6 } })]} />,
    );
    const row = screen.getByRole("row", { name: /yellow/i });
    expect(within(row).getByText("−6")).toBeInTheDocument();
  });

  it("shows an em dash when a stat is present in one season but not the other", () => {
    render(
      <SeasonStatsTable
        seasons={[
          season(2025, { goals: { count: 18, points: 72 }, penaltySave: { count: 0, points: 0 } }),
          season(2026, { goals: { count: 2, points: 8 } }),
        ]}
      />,
    );
    const penaltySaveRow = screen.getByRole("row", { name: /penalties saved/i });
    const cells = within(penaltySaveRow).getAllByText("—");
    expect(cells).toHaveLength(2); // Two em dashes in the 2026/27 season (count and pts)
  });
});
