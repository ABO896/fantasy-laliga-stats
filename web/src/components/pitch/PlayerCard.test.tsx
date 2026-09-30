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

describe("PlayerCard — Power and Economy (ANALYTICS-06/07)", () => {
  it("shows both scores rounded", () => {
    renderCard(member({ powerScore: 71.6, economyScore: 40.2 }));
    expect(screen.getByText("PWR 72 · ECO 40")).toBeInTheDocument();
  });

  it("shows a dash when there is not enough data, never a zero", () => {
    renderCard(member({ powerScore: null }));
    expect(screen.getByText("PWR — · ECO —")).toBeInTheDocument();
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
