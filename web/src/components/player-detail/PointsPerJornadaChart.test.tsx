import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import PointsPerJornadaChart, { buildJornadaSlots } from "./PointsPerJornadaChart";

describe("buildJornadaSlots", () => {
  it("creates one slot per league week, not per week the player played", () => {
    const slots = buildJornadaSlots(
      [{ seasonYear: 2026, week: 2, points: 7, isProvisional: true }],
      { 2026: 3 },
    );
    expect(slots.map((s) => s.week)).toEqual([1, 2, 3]);
  });

  it("leaves an absent week null rather than dropping it", () => {
    const slots = buildJornadaSlots(
      [
        { seasonYear: 2025, week: 1, points: 4, isProvisional: false },
        { seasonYear: 2025, week: 3, points: 6, isProvisional: false },
      ],
      { 2025: 3 },
    );
    expect(slots.map((s) => s.points)).toEqual([4, null, 6]);
  });

  it("distinguishes an absent week from a zero-point week", () => {
    const slots = buildJornadaSlots(
      [
        { seasonYear: 2025, week: 1, points: 0, isProvisional: false },
        { seasonYear: 2025, week: 3, points: 6, isProvisional: false },
      ],
      { 2025: 3 },
    );
    expect(slots[0]!.points).toBe(0);
    expect(slots[0]!.recorded).toBe(true);
    expect(slots[1]!.points).toBeNull();
    expect(slots[1]!.recorded).toBe(false);
  });

  it("orders seasons oldest first and carries the season on every slot", () => {
    const slots = buildJornadaSlots(
      [
        { seasonYear: 2026, week: 1, points: 5, isProvisional: false },
        { seasonYear: 2025, week: 1, points: 3, isProvisional: false },
      ],
      { 2025: 1, 2026: 1 },
    );
    expect(slots.map((s) => s.seasonYear)).toEqual([2025, 2026]);
  });

  it("marks a provisional week", () => {
    const slots = buildJornadaSlots(
      [{ seasonYear: 2026, week: 1, points: 7, isProvisional: true }],
      { 2026: 1 },
    );
    expect(slots[0]!.isProvisional).toBe(true);
  });

  it("labels each slot with its season and week", () => {
    const slots = buildJornadaSlots(
      [{ seasonYear: 2025, week: 4, points: 1, isProvisional: false }],
      { 2025: 4 },
    );
    expect(slots[3]!.label).toBe("2025/26 J4");
  });
});

describe("PointsPerJornadaChart", () => {
  it("renders a chart when there are jornadas", () => {
    const { container } = render(
      <PointsPerJornadaChart
        rows={[{ seasonYear: 2026, week: 1, points: 5, isProvisional: false }]}
        seasonWeekRanges={{ 2026: 1 }}
        width={600}
        height={240}
      />,
    );
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("states the absence when no jornada has been scored", () => {
    render(
      <PointsPerJornadaChart rows={[]} seasonWeekRanges={{}} width={600} height={240} />,
    );
    expect(screen.getByText(/no jornada scores/i)).toBeInTheDocument();
  });

  it("says that the latest week is provisional", () => {
    render(
      <PointsPerJornadaChart
        rows={[{ seasonYear: 2026, week: 1, points: 5, isProvisional: true }]}
        seasonWeekRanges={{ 2026: 1 }}
        width={600}
        height={240}
      />,
    );
    expect(screen.getByText(/provisional/i)).toBeInTheDocument();
  });

  it("draws a bar rectangle for a recorded zero but none for an absent week", () => {
    // Recharts' Bar renders no rectangle at all for a value of `null`
    // (an absent week — genuinely unknown) *and*, without `minPointSize`,
    // for a value of `0` too — collapsing "recorded zero" and "unknown"
    // into the same invisible gap. Week 1 here is a recorded zero, week 2
    // is absent (no row), week 3 is a recorded six: this asserts the chart
    // renders a rectangle for weeks 1 and 3 but not for week 2, i.e. that
    // `minPointSize` is doing its job and a zero is visually distinct from
    // an absence rather than looking identical to it.
    const { container } = render(
      <PointsPerJornadaChart
        rows={[
          { seasonYear: 2025, week: 1, points: 0, isProvisional: false },
          { seasonYear: 2025, week: 3, points: 6, isProvisional: false },
        ]}
        seasonWeekRanges={{ 2025: 3 }}
        width={600}
        height={240}
      />,
    );
    // 3 slots exist (weeks 1-3) but only the 2 recorded ones — the zero
    // and the six — should produce a rectangle; the absent week 2 must not.
    expect(container.querySelectorAll(".recharts-bar-rectangle")).toHaveLength(2);
  });

  it("labels the season divider with the season it introduces", () => {
    // Without a label, a reader sees a bare dashed line with no statement
    // of which side is which — the X-axis tick text alone doesn't carry
    // it reliably, since `interval="preserveStartEnd"` drops most ticks.
    const { container } = render(
      <PointsPerJornadaChart
        rows={[
          { seasonYear: 2025, week: 1, points: 4, isProvisional: false },
          { seasonYear: 2026, week: 1, points: 5, isProvisional: false },
        ]}
        seasonWeekRanges={{ 2025: 1, 2026: 1 }}
        width={600}
        height={240}
      />,
    );
    expect(container.querySelector(".recharts-reference-line")).toBeInTheDocument();
    expect(screen.getByText("2026/27")).toBeInTheDocument();
  });

  it("uses a custom caption when one is given, for reuse outside the player page", () => {
    render(
      <PointsPerJornadaChart
        rows={[{ seasonYear: 2026, week: 1, points: 4, isProvisional: false }]}
        seasonWeekRanges={{ 2026: 1 }}
        width={600}
        height={240}
        caption="Squad points per jornada · current squad, every recorded week"
      />,
    );
    expect(
      screen.getByText(/^Squad points per jornada · current squad, every recorded week$/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/^Points per jornada$/i)).not.toBeInTheDocument();
  });

  it("uses a custom empty message when one is given", () => {
    render(
      <PointsPerJornadaChart
        rows={[]}
        seasonWeekRanges={{}}
        width={600}
        height={240}
        emptyMessage="No jornada scores recorded for the squad."
      />,
    );
    expect(screen.getByText(/no jornada scores recorded for the squad/i)).toBeInTheDocument();
  });
});
