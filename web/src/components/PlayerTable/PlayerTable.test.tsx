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

describe("PlayerTable — Power column and position rank (ANALYTICS-06, Task 7)", () => {
  it("renders the score and rank, and sorts by Power with nulls last", () => {
    const players = [
      buildPlayer({ playerId: 1, name: "Middling", powerScore: 41.6, powerRank: { rank: 30, of: 61 } }),
      buildPlayer({ playerId: 2, name: "No Data", powerScore: null, powerRank: null }),
      buildPlayer({
        playerId: 3, name: "Star", powerScore: 88.4,
        powerRank: { rank: 2, of: 61 }, position: "DEF",
      }),
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
    const powerCell = within(rows[0]!).getByTitle("#2 of 61 DEF by Power");
    expect(powerCell.textContent).toBe("88 · #2");
    expect(within(table).getByText("Power")).toBeInTheDocument();
  });

  it("has no Economy column any more — it moved to the transfers page only", () => {
    const players = [buildPlayer({ playerId: 1, name: "Any", economyScore: 50 })];

    render(
      <MemoryRouter>
        <PlayerTable players={players} columnFilters={[]} />
      </MemoryRouter>,
    );

    expect(screen.queryByText("Economy")).not.toBeInTheDocument();
  });
});

describe("PlayerTable — Value column (Task 7, points value percentile)", () => {
  it("renders the percentile and sorts with nulls last", () => {
    const players = [
      buildPlayer({ playerId: 1, name: "Mid Value", pointsValuePct: 40 }),
      buildPlayer({ playerId: 2, name: "No Value", pointsValuePct: null }),
      buildPlayer({ playerId: 3, name: "Best Value", pointsValuePct: 92 }),
    ];

    render(
      <MemoryRouter>
        <PlayerTable
          players={players}
          columnFilters={[]}
          sorting={[{ id: "pointsValuePct", desc: true }]}
          onSortingChange={() => {}}
        />
      </MemoryRouter>,
    );

    const table = screen.getByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((row) => within(row).getAllByRole("cell")[0]!.textContent)).toEqual([
      "Best Value",
      "Mid Value",
      "No Value",
    ]);
    expect(within(rows[0]!).getByText("92")).toBeInTheDocument();
    expect(within(table).getByText("Value")).toBeInTheDocument();
  });
});

describe("PlayerTable — Plays column (Task 7, reliability class sorted by pStart)", () => {
  it("renders the reliability class and sorts by pStart with nulls last", () => {
    const players = [
      buildPlayer({ playerId: 1, name: "Rotation Guy", reliabilityClass: "Rotation", pStart: 0.3 }),
      buildPlayer({ playerId: 2, name: "Unknown", reliabilityClass: null, pStart: null }),
      buildPlayer({ playerId: 3, name: "Nailed On", reliabilityClass: "Nailed", pStart: 0.95 }),
    ];

    render(
      <MemoryRouter>
        <PlayerTable
          players={players}
          columnFilters={[]}
          sorting={[{ id: "reliabilityClass", desc: true }]}
          onSortingChange={() => {}}
        />
      </MemoryRouter>,
    );

    const table = screen.getByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((row) => within(row).getAllByRole("cell")[0]!.textContent)).toEqual([
      "Nailed On",
      "Rotation Guy",
      "Unknown",
    ]);
    expect(within(rows[0]!).getByText("Nailed")).toBeInTheDocument();
    expect(within(table).getByText("Plays")).toBeInTheDocument();
  });
});

describe("PlayerTable — 7d outlook column (Task 7)", () => {
  it("renders a signed percentage and marks drop risk in red", () => {
    const players = [
      buildPlayer({ playerId: 1, name: "Safe", outlookPct: 2.1, dropRisk: false }),
      buildPlayer({ playerId: 2, name: "At Risk", outlookPct: -4.5, dropRisk: true,
                    outlookDirection: "fall" }),
      // Final review #10: drop risk on a predicted rise is a marker, not red.
      buildPlayer({ playerId: 3, name: "Rise With Risk", outlookPct: 3.3, dropRisk: true,
                    outlookDirection: "rise" }),
    ];

    render(
      <MemoryRouter>
        <PlayerTable players={players} columnFilters={[]} />
      </MemoryRouter>,
    );

    const table = screen.getByRole("table");
    expect(within(table).getByText("7d outlook")).toBeInTheDocument();
    const riskyCell = within(table).getByText("-4.50%");
    expect(riskyCell.className).toContain("destructive");
    const safeCell = within(table).getByText("+2.10%");
    expect(safeCell.className).not.toContain("destructive");
    const risingWithRisk = within(table).getByText(/\+3\.30%/);
    expect(risingWithRisk.className).not.toContain("destructive");
    expect(risingWithRisk.getAttribute("title")).toMatch(/drop risk/i);
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

describe("PlayerTable — Verdict column (Plan C Task 6)", () => {
  it("renders the chip and sorts by LABELS priority order, nulls last", () => {
    const players = [
      buildPlayer({ playerId: 1, name: "Fair", verdict: { label: "Fair price", tags: [], confidence: "medium" } }),
      buildPlayer({ playerId: 2, name: "No Verdict", verdict: null }),
      buildPlayer({ playerId: 3, name: "Top", verdict: { label: "Elite", tags: [], confidence: "high" } }),
    ];

    render(
      <MemoryRouter>
        <PlayerTable
          players={players}
          columnFilters={[]}
          sorting={[{ id: "verdict", desc: false }]}
          onSortingChange={() => {}}
        />
      </MemoryRouter>,
    );

    const table = screen.getByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((row) => within(row).getAllByRole("cell")[0]!.textContent)).toEqual([
      "Top",
      "Fair",
      "No Verdict",
    ]);
    expect(within(rows[0]!).getByText("Elite")).toBeInTheDocument();
    expect(within(table).getByText("Verdict")).toBeInTheDocument();
  });

  it("keeps only rows matching the selected verdict labels", () => {
    const players = [
      buildPlayer({ playerId: 1, name: "Keep", verdict: { label: "Elite", tags: [], confidence: "high" } }),
      buildPlayer({ playerId: 2, name: "Drop", verdict: { label: "Avoid", tags: [], confidence: "low" } }),
      buildPlayer({ playerId: 3, name: "Also Drop", verdict: null }),
    ];

    render(
      <MemoryRouter>
        <PlayerTable players={players} columnFilters={[{ id: "verdict", value: ["Elite"] }]} />
      </MemoryRouter>,
    );

    const table = screen.getByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(1);
    expect(within(rows[0]!).getByText("Keep")).toBeInTheDocument();
  });
});
