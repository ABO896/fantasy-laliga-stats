import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { SquadMemberRow } from "../../api-client/squad";
import PlayerCard from "./PlayerCard";

function member(overrides: Partial<SquadMemberRow> = {}): SquadMemberRow {
  return {
    playerId: 1,
    name: "Pedri",
    position: "MED",
    purchasePrice: 1,
    marketValue: 90_000_000,
    effectiveValue: 90_000_000,
    role: "starter",
    availability: "available",
    ...overrides,
  };
}

function renderCard(player: SquadMemberRow) {
  render(
    <MemoryRouter>
      <PlayerCard player={player} lifted={false} highlighted={false} onClick={() => {}} />
    </MemoryRouter>,
  );
}

describe("PlayerCard — Power, position rank and Value (ANALYTICS-06, Task 7)", () => {
  it("shows the score, its position rank, and the points-value percentile", () => {
    renderCard(member({ powerScore: 71.6, powerRank: { rank: 2, of: 61 }, pointsValuePct: 84 }));
    expect(screen.getByText("PWR 72 #2 · VAL 84")).toBeInTheDocument();
  });

  it("shows a dash when there is not enough data, never a zero, and no rank", () => {
    renderCard(member({ powerScore: null, powerRank: null, pointsValuePct: null }));
    expect(screen.getByText("PWR — · VAL —")).toBeInTheDocument();
  });
});

describe("PlayerCard — expected points (MODEL-02)", () => {
  it("shows xP to one decimal with its basis", () => {
    renderCard(member({ expectedPoints: 4.26, expectedPointsBasis: "form+starter+odds" }));
    expect(screen.getByText("xP 4.3")).toHaveAttribute(
      "title",
      "Expected points next jornada — basis: form+starter+odds",
    );
  });

  it("shows a dash when no prediction is stored", () => {
    renderCard(member({ expectedPoints: null }));
    expect(screen.getByText("xP —")).toBeInTheDocument();
  });
});
