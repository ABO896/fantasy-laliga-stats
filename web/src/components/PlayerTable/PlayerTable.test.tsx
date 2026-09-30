import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import PlayerTable from "./PlayerTable";
import type { PlayerRow } from "../../api-client/players";

function buildPlayer(overrides: Partial<PlayerRow> & { playerId: number }): PlayerRow {
  return {
    externalId: `player-${overrides.playerId}`,
    name: `Player ${overrides.playerId}`,
    team: `Team ${overrides.playerId}`,
    position: "DEF",
    marketValue: 10_000_000,
    idealBid: null,
    maxBid: null,
    priceChangeAbs: null,
    priceChangePct: null,
    points: 0,
    pricePerPoint: null,
    starterProbability: null,
    availabilityStatus: "available",
    nextOpponent: null,
    ...overrides,
  };
}

// PlayerBrowser is the only place that renders PlayerTable — and since Task
// 10 it always passes `sorting`/`onSortingChange`, so nothing else in the
// suite exercises the uncontrolled path any more. `PlayerTable` must stay
// usable with neither prop (its own tests render it that way), so this
// pins the invariant directly rather than leaving it to inspection: render
// with no sorting props and confirm the documented default — price/point
// efficiency, ascending, nulls last — still applies.
describe("PlayerTable (uncontrolled)", () => {
  it("applies its own default sort when no sorting/onSortingChange props are passed", () => {
    const players = [
      buildPlayer({ playerId: 1, name: "Low Value", points: 10, pricePerPoint: 5 }),
      buildPlayer({ playerId: 2, name: "Best Value", points: 10, pricePerPoint: 1 }),
      buildPlayer({ playerId: 3, name: "No Points", points: 0, pricePerPoint: null }),
    ];

    render(
      <MemoryRouter>
        <PlayerTable players={players} columnFilters={[]} />
      </MemoryRouter>,
    );

    const table = screen.getByRole("table");
    const names = within(table)
      .getAllByRole("row")
      .slice(1)
      .map((row) => within(row).getAllByRole("cell")[0]!.textContent);
    expect(names).toEqual(["Best Value", "Low Value", "No Points"]);
  });

  it("still lets a header click resort the table when uncontrolled", () => {
    const players = [
      buildPlayer({ playerId: 1, name: "Forward One", marketValue: 1_000_000 }),
      buildPlayer({ playerId: 2, name: "Midfield One", marketValue: 2_000_000 }),
    ];

    render(
      <MemoryRouter>
        <PlayerTable players={players} columnFilters={[]} />
      </MemoryRouter>,
    );

    const table = screen.getByRole("table");
    fireEvent.click(within(table).getByText("Market value"));

    // A resort happened — some direction arrow now decorates the header —
    // and the rows actually reordered by market value, proving the click
    // reached `setInternalSorting` (the uncontrolled fallback), not a no-op.
    const sortIndicator = within(table)
      .getAllByRole("columnheader")
      .find((header) => header.textContent?.includes("Market value"));
    expect(sortIndicator?.textContent).toMatch(/[▲▼]/);

    const names = within(table)
      .getAllByRole("row")
      .slice(1)
      .map((row) => within(row).getAllByRole("cell")[0]!.textContent);
    expect(names).toEqual(["Midfield One", "Forward One"]);
  });
});

describe("PlayerTable — Power and Economy columns (ANALYTICS-06/07)", () => {
  it("renders both scores rounded and sorts by Power with nulls last", () => {
    const players = [
      buildPlayer({ playerId: 1, name: "Middling", powerScore: 41.6, economyScore: 12.2 }),
      buildPlayer({ playerId: 2, name: "No Data", powerScore: null, economyScore: null }),
      buildPlayer({ playerId: 3, name: "Star", powerScore: 88.4, economyScore: 97 }),
    ];

    render(
      <MemoryRouter>
        <PlayerTable
          players={players}
          columnFilters={[]}
          sorting={[{ id: "powerScore", desc: true }]}
          onSortingChange={() => {}}
        />
      </MemoryRouter>,
    );

    const table = screen.getByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((row) => within(row).getAllByRole("cell")[0]!.textContent)).toEqual([
      "Star",
      "Middling",
      "No Data",
    ]);
    expect(within(rows[0]!).getByText("88")).toBeInTheDocument();
    expect(within(rows[0]!).getByText("97")).toBeInTheDocument();
    expect(within(table).getByText("Power")).toBeInTheDocument();
    expect(within(table).getByText("Economy")).toBeInTheDocument();
  });
});

describe("PlayerTable — xP column (MODEL-02)", () => {
  it("renders xP to one decimal and sorts by it with nulls last", () => {
    const players = [
      buildPlayer({ playerId: 1, name: "Bench", expectedPoints: 1.24, expectedPointsBasis: "form+starter" }),
      buildPlayer({ playerId: 2, name: "Unknown", expectedPoints: null }),
      buildPlayer({ playerId: 3, name: "Starter", expectedPoints: 6.51, expectedPointsBasis: "form+starter+odds" }),
    ];

    render(
      <MemoryRouter>
        <PlayerTable
          players={players}
          columnFilters={[]}
          sorting={[{ id: "expectedPoints", desc: true }]}
          onSortingChange={() => {}}
        />
      </MemoryRouter>,
    );

    const table = screen.getByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((row) => within(row).getAllByRole("cell")[0]!.textContent)).toEqual([
      "Starter",
      "Bench",
      "Unknown",
    ]);
    expect(within(rows[0]!).getByText("6.5")).toHaveAttribute(
      "title",
      "Expected points next jornada — basis: form+starter+odds",
    );
    expect(within(table).getByText("xP")).toBeInTheDocument();
  });
});
