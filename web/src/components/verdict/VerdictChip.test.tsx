import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import VerdictChip from "./VerdictChip";

describe("VerdictChip", () => {
  it.each([
    ["Elite", "positive"],
    ["Bargain", "positive"],
    ["Rising", "positive"],
    ["Sell high", "negative"],
    ["Overpriced", "negative"],
    ["Avoid", "negative"],
    ["Rotation risk", "caution"],
    ["Unavailable", "caution"],
    ["Unproven", "neutral"],
    ["Fair price", "neutral"],
  ])("renders %s with the label text and the %s tone", (label, tone) => {
    render(<VerdictChip label={label} />);
    const chip = screen.getByText(label);
    expect(chip).toHaveAttribute("data-tone", tone);
  });

  it("defaults to the md size", () => {
    render(<VerdictChip label="Elite" />);
    expect(screen.getByText("Elite")).toHaveClass("verdict-chip-md");
  });

  it("accepts an sm size", () => {
    render(<VerdictChip label="Elite" size="sm" />);
    expect(screen.getByText("Elite")).toHaveClass("verdict-chip-sm");
  });
});
