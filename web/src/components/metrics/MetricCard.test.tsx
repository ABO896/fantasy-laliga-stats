import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import MetricCard from "./MetricCard";

describe("MetricCard", () => {
  it("renders value, word, rank, meaning, why, and a closed step table", () => {
    render(
      <MetricCard
        metric="power"
        value="71"
        rank={{ rank: 5, of: 190, percentile: 97, position: "DEF" }}
        steps={[{ step: "Rate", value: "4.6", meaning: "points per match" }]}
        headline={{ step: "Score", value: "71", meaning: "benchmark" }}
      />,
    );

    expect(screen.getAllByText("71").length).toBeGreaterThan(0);
    expect(screen.getByText("Very high")).toBeInTheDocument(); // bandFor at percentile 97
    expect(screen.getByText("#5 of 190 DEF")).toBeInTheDocument();
    expect(screen.getByText(/Expected points per match right now/)).toBeInTheDocument();
    expect(screen.getByText(/Why it matters:/)).toBeInTheDocument();
    const details = screen.getByText("How it's calculated").closest("details");
    expect(details).not.toBeNull();
    expect(details).not.toHaveAttribute("open");
  });

  it("shows the reason and no step table when the metric has no value", () => {
    render(
      <MetricCard
        metric="power"
        value={null}
        rank={null}
        steps={null}
        headline={null}
        emptyReason="2 matches with minutes this season"
      />,
    );

    expect(screen.getByText("2 matches with minutes this season")).toBeInTheDocument();
    expect(screen.queryByText("How it's calculated")).not.toBeInTheDocument();
  });

  it("lets a metric override the band word with its own vocabulary", () => {
    render(
      <MetricCard
        metric="reliability"
        value="62%"
        word="Regular"
        rank={null}
        steps={null}
        headline={null}
      />,
    );
    expect(screen.getByText("Regular")).toBeInTheDocument();
  });

  it("renders children (e.g. a window toggle) even when value is null", () => {
    render(
      <MetricCard metric="momentum" value={null} rank={null} steps={null} headline={null}>
        <button type="button">7d</button>
      </MetricCard>,
    );
    expect(screen.getByRole("button", { name: "7d" })).toBeInTheDocument();
  });
});
