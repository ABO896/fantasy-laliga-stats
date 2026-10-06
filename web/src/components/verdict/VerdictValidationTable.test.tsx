import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ValidationReport } from "../../api-client/verdict";
import VerdictValidationTable from "./VerdictValidationTable";

describe("VerdictValidationTable", () => {
  it("shows the refresh instruction when no report has ever been generated", () => {
    render(<VerdictValidationTable report={{ generatedAt: null, labels: [] }} />);
    expect(
      screen.getByText(/uv run python -m storage\.verdict_backtest --write/),
    ).toBeInTheDocument();
  });

  it("renders a label row that hasn't beaten chance with a cross", () => {
    const report: ValidationReport = {
      generatedAt: "2026-10-01T00:00:00Z",
      season: 2026,
      dates: ["2026-09-01"],
      thresholds: {},
      disabled: [],
      notes: [],
      labels: [
        {
          label: "Sell high",
          metric: "price_pct",
          n: 40,
          players: 12,
          hitRate: 0.5,
          baseRate: 0.52,
          meanDiff: -0.1,
          ciLow: -0.3,
          ciHigh: 0.1,
          beatsChance: false,
        },
      ],
    };
    render(<VerdictValidationTable report={report} />);
    expect(screen.getByText("Sell high")).toBeInTheDocument();
    expect(screen.getByText("price change (%)")).toBeInTheDocument();
    expect(screen.getByText("✗")).toBeInTheDocument();
  });

  it("renders a label row that has beaten chance with a check", () => {
    const report: ValidationReport = {
      generatedAt: "2026-10-01T00:00:00Z",
      labels: [
        {
          label: "Elite",
          metric: "points",
          n: 80,
          players: 20,
          hitRate: 0.7,
          baseRate: 0.5,
          meanDiff: 1.1,
          ciLow: 0.4,
          ciHigh: 1.8,
          beatsChance: true,
        },
      ],
    };
    render(<VerdictValidationTable report={report} />);
    expect(screen.getByText("Elite")).toBeInTheDocument();
    expect(screen.getByText("points")).toBeInTheDocument();
    expect(screen.getByText("✓")).toBeInTheDocument();
  });
});
