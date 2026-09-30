import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import RemoveFromSquadDialog from "./RemoveFromSquadDialog";
import type { SquadMemberRow } from "../api-client/squad";

const member: SquadMemberRow = {
  playerId: 1,
  name: "Owned Keeper",
  position: "POR",
  purchasePrice: 4_000_000,
  marketValue: 5_000_000,
  effectiveValue: 5_000_000,
  role: "reserve",
  availability: "available",
};

describe("RemoveFromSquadDialog", () => {
  it("pre-fills the sale price with the member's market value", () => {
    render(<RemoveFromSquadDialog member={member} onConfirm={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByLabelText(/sale price/i)).toHaveValue("5000000");
  });

  it("leaves the sale price blank when the member has no market value snapshot", () => {
    const noSnapshot: SquadMemberRow = { ...member, marketValue: null };
    render(<RemoveFromSquadDialog member={noSnapshot} onConfirm={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByLabelText(/sale price/i)).toHaveValue("");
  });

  it("a blank field confirms with undefined", () => {
    const onConfirm = vi.fn();
    render(<RemoveFromSquadDialog member={member} onConfirm={onConfirm} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/sale price/i), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: /record sale/i }));
    expect(onConfirm).toHaveBeenCalledWith(undefined);
  });

  it("an edited price confirms with that number", () => {
    const onConfirm = vi.fn();
    render(<RemoveFromSquadDialog member={member} onConfirm={onConfirm} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/sale price/i), { target: { value: "6000000" } });
    fireEvent.click(screen.getByRole("button", { name: /record sale/i }));
    expect(onConfirm).toHaveBeenCalledWith(6_000_000);
  });

  it("skip confirms with undefined even when a price was typed", () => {
    const onConfirm = vi.fn();
    render(<RemoveFromSquadDialog member={member} onConfirm={onConfirm} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/sale price/i), { target: { value: "6000000" } });
    fireEvent.click(screen.getByRole("button", { name: /skip/i }));
    expect(onConfirm).toHaveBeenCalledWith(undefined);
  });

  it("cancels without confirming", () => {
    const onCancel = vi.fn();
    const onConfirm = vi.fn();
    render(<RemoveFromSquadDialog member={member} onConfirm={onConfirm} onCancel={onCancel} />);
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onCancel).toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("disables Record sale for an unparseable price, but leaves Skip enabled", () => {
    render(<RemoveFromSquadDialog member={member} onConfirm={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/sale price/i), { target: { value: "not a number" } });
    expect(screen.getByRole("button", { name: /record sale/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /skip/i })).not.toBeDisabled();
  });

  it("shows the server's refusal message verbatim", () => {
    render(
      <RemoveFromSquadDialog
        member={member}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        error="Sale price can't be negative."
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Sale price can't be negative");
  });
});
