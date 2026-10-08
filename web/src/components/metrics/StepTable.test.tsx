import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { signedNumber } from "../../lib/format";
import StepTable from "./StepTable";

describe("StepTable", () => {
  const steps = [
    { step: "Base", value: "4.20", meaning: "Season scoring rate" },
    { step: "Shrink", value: signedNumber(-1.8), meaning: "Toward last season" },
  ];
  const headline = { step: "Power", value: "2.40", meaning: "Final value" };

  it("is collapsed by default", () => {
    render(<StepTable steps={steps} headline={headline} />);
    const details = screen.getByText("How it's calculated").closest("details");
    expect(details).not.toHaveAttribute("open");
  });

  it("renders the headline row last and bold", () => {
    render(<StepTable steps={steps} headline={headline} />);
    const rows = screen.getAllByRole("row");
    // header row + 2 step rows + headline row
    const lastRow = rows[rows.length - 1];
    expect(lastRow).toHaveTextContent("Power");
    expect(lastRow.querySelector("strong")).not.toBeNull();
  });

  it("keeps the real minus sign on a negative step value", () => {
    render(<StepTable steps={steps} headline={headline} />);
    expect(screen.getByText("−1.8")).toBeInTheDocument();
  });
});
