import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ValueHistoryChart, { pickTicks } from "./ValueHistoryChart";
import { formatShortDate } from "../../lib/format";

const POINTS = [
  { asOf: "2026-08-06", marketValue: 100 },
  { asOf: "2026-08-07", marketValue: 120 },
];

describe("ValueHistoryChart", () => {
  it("renders a chart when there is history", () => {
    const { container } = render(
      <ValueHistoryChart points={POINTS} width={600} height={240} />,
    );
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("says how much history it is showing", () => {
    render(<ValueHistoryChart points={POINTS} width={600} height={240} />);
    expect(screen.getByText(/6 Aug – 7 Aug · 2 snapshots/i)).toBeInTheDocument();
  });

  it("states the real calendar span and sample count for a gapped series, not a count of points labelled 'days'", () => {
    // 08-06 to 08-27 is a 22-day calendar span; only 3 of those days were
    // actually snapshotted. The caption must say "3 snapshots" over that
    // real span — never "3 days", which would understate the gap.
    render(
      <ValueHistoryChart
        points={[
          { asOf: "2026-08-06", marketValue: 100 },
          { asOf: "2026-08-11", marketValue: 110 },
          { asOf: "2026-08-27", marketValue: 130 },
        ]}
        width={600}
        height={240}
      />,
    );
    expect(screen.getByText(/6 Aug – 27 Aug · 3 snapshots/i)).toBeInTheDocument();
    expect(screen.queryByText(/3 days/i)).not.toBeInTheDocument();
  });

  it("states the limit rather than drawing a line through one point", () => {
    render(
      <ValueHistoryChart
        points={[{ asOf: "2026-08-06", marketValue: 100 }]}
        width={600}
        height={240}
      />,
    );
    expect(screen.getByText(/one day of history/i)).toBeInTheDocument();
  });

  it("degrades to a stated absence with no history at all", () => {
    render(<ValueHistoryChart points={[]} width={600} height={240} />);
    expect(screen.getByText(/no market value history/i)).toBeInTheDocument();
  });

  it("draws a visible dot at each observation rather than hiding them", () => {
    const { container } = render(
      <ValueHistoryChart points={POINTS} width={600} height={240} />,
    );
    expect(container.querySelectorAll(".recharts-line-dot").length).toBeGreaterThan(0);
  });

  it("spaces an 8-day gap wider than a 1-day step on the axis", () => {
    // A category axis draws every step at equal width regardless of the
    // real calendar gap between snapshots. With a numeric time axis, the
    // pixel distance from 08-06 to 08-14 (8 days) must be roughly 8x the
    // distance from 08-14 to 08-15 (1 day).
    const { container } = render(
      <ValueHistoryChart
        points={[
          { asOf: "2026-08-06", marketValue: 100 },
          { asOf: "2026-08-14", marketValue: 110 },
          { asOf: "2026-08-15", marketValue: 120 },
        ]}
        width={600}
        height={240}
      />,
    );
    const dots = Array.from(container.querySelectorAll(".recharts-line-dot"));
    expect(dots.length).toBe(3);
    const cx = dots.map((d) => Number(d.getAttribute("cx")));
    const gapWide = cx[1]! - cx[0]!;
    const gapNarrow = cx[2]! - cx[1]!;
    expect(gapWide).toBeGreaterThan(gapNarrow * 4);
  });

  it("does not repeat the same tick label on a short two-point span", () => {
    // Recharts' default numeric-axis tick generation spaces ticks evenly
    // across the domain, not at the actual data points. Over a one-day span
    // that produced several ticks that all round to the same calendar day
    // under formatShortDate (e.g. "6 Aug · 6 Aug · 6 Aug · 6 Aug · 7 Aug").
    // With only 2 real snapshots, ticks derived from them must not repeat —
    // and there must be exactly 2 of them, one per real observation, not
    // Recharts' default 5 evenly-spaced ticks.
    const timestamps = POINTS.map((p) => new Date(p.asOf).getTime());
    const ticks = pickTicks(timestamps, 8);
    const labels = ticks.map((t) => formatShortDate(new Date(t).toISOString()));
    const adjacentDuplicates = labels.some((label, i) => i > 0 && label === labels[i - 1]);
    expect(adjacentDuplicates).toBe(false);
    expect(labels).toEqual(["6 Aug", "7 Aug"]);

    const { container } = render(<ValueHistoryChart points={POINTS} width={600} height={240} />);
    const tickLines = container.querySelectorAll(
      ".recharts-xAxis .recharts-cartesian-axis-tick-line",
    );
    expect(tickLines).toHaveLength(2);
  });

  it("uses a custom caption prefix when one is given, for reuse outside the player page", () => {
    render(<ValueHistoryChart points={POINTS} width={600} height={240} caption="Squad value" />);
    expect(screen.getByText(/^Squad value · 6 Aug – 7 Aug · 2 snapshots/i)).toBeInTheDocument();
    expect(screen.queryByText(/^Market value/i)).not.toBeInTheDocument();
  });

  it("uses a custom empty message when one is given", () => {
    render(
      <ValueHistoryChart
        points={[]}
        width={600}
        height={240}
        emptyMessage="No squad value history yet."
      />,
    );
    expect(screen.getByText(/no squad value history yet/i)).toBeInTheDocument();
  });

  it("thins ticks to an even spread, keeping the endpoints, when there are many snapshots", () => {
    const manyPoints = Array.from({ length: 30 }, (_, i) => ({
      asOf: `2026-08-${String((i % 28) + 1).padStart(2, "0")}`,
      marketValue: 100 + i,
    }));
    const timestamps = manyPoints.map((p) => new Date(p.asOf).getTime());
    const ticks = pickTicks(timestamps, 8);
    expect(ticks.length).toBeLessThanOrEqual(8);
    expect(ticks[0]).toBe(timestamps[0]);
    expect(ticks[ticks.length - 1]).toBe(timestamps[timestamps.length - 1]);
  });
});
