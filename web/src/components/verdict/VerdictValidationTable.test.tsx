import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ValidationReport } from "../../api-client/verdict";
import VerdictValidationTable from "./VerdictValidationTable";

describe("VerdictValidationTable", () => {
  it("shows the refresh instruction when no report has ever been generated", () => {
    render(<VerdictValidationTable report={{ generatedAt: null, labels: [], disabledLabels: [] }} />);
    expect(
      screen.getByText(/uv run python -m storage\.verdict_backtest --write/),
    ).toBeInTheDocument();
  });

  it("renders a label row that hasn't beaten chance with a cross", () => {
    const report: ValidationReport = {
      generatedAt: "2026-10-01T00:00:00Z",
      disabledLabels: [],
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
      disabledLabels: [],
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

  it("shows the momentum baseline beside a price label (final review #2)", () => {
    const report: ValidationReport = {
      generatedAt: "2026-10-01T00:00:00Z",
      disabledLabels: ["Sell high"],
      labels: [
        {
          label: "Sell high", metric: "price_pct", n: 300, players: 40, hitRate: 0.55,
          baseRate: 0.5, meanDiff: 7.9, ciLow: 2.1, ciHigh: 12.0, beatsChance: true,
          momentumBaseline: { n: 900, hitRate: 0.62, meanDiff: 13.8 },
        },
        {
          label: "Elite", metric: "points", n: 80, players: 20, hitRate: 0.7, baseRate: 0.5,
          meanDiff: 1.1, ciLow: 0.4, ciHigh: 1.8, beatsChance: true, momentumBaseline: null,
        },
      ],
    };
    render(<VerdictValidationTable report={report} />);
    expect(screen.getByRole("columnheader", { name: /vs momentum/i })).toBeInTheDocument();
    expect(screen.getByText("13.80 (n 900, hit 62.0%)")).toBeInTheDocument();
  });
});
