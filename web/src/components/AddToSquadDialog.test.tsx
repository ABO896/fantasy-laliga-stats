import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import AddToSquadDialog from "./AddToSquadDialog";
import type { PlayerRow } from "../api-client/players";

const player = {
  playerId: 7,
  externalId: "ext-7",
  name: "Test Player",
  team: "Team",
  position: "DEL",
  marketValue: 12_500_000,
  idealBid: null,
  maxBid: null,
  priceChangeAbs: null,
  priceChangePct: null,
  points: 40,
  pricePerPoint: null,
  starterProbability: null,
  availabilityStatus: "available",
  nextOpponent: null,
} satisfies PlayerRow;

describe("AddToSquadDialog", () => {
  it("pre-fills the purchase price with today's market value", () => {
    render(<AddToSquadDialog player={player} onConfirm={vi.fn()} onCancel={vi.fn()} />);
    // The field is type="text" (see the component for why), so its DOM value
    // is a string — jest-dom's toHaveValue does a strict comparison and
    // would never match a bare number literal against it.
    expect(screen.getByLabelText(/purchase price/i)).toHaveValue("12500000");
  });

  it("confirms with an edited price, because a bid is rarely the market value", () => {
    const onConfirm = vi.fn();
    render(<AddToSquadDialog player={player} onConfirm={onConfirm} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/purchase price/i), {
      target: { value: "14000000" },
    });
    fireEvent.click(screen.getByRole("button", { name: /add to squad/i }));
    expect(onConfirm).toHaveBeenCalledWith(14_000_000);
  });

  it("shows the server's refusal message verbatim", () => {
    render(
      <AddToSquadDialog
        player={player}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        error="€2.1M short — sell a player worth at least €2.1M."
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("€2.1M short");
  });

  it("cancels without confirming", () => {
    const onCancel = vi.fn();
    const onConfirm = vi.fn();
    render(<AddToSquadDialog player={player} onConfirm={onConfirm} onCancel={onCancel} />);
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onCancel).toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
