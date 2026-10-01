import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PlayerAnalytics } from "../../api-client/analytics";

vi.mock("../../api-client/analytics", async () => {
  const actual =
    await vi.importActual<typeof import("../../api-client/analytics")>("../../api-client/analytics");
  return { ...actual, fetchPlayerAnalytics: vi.fn() };
});

import { fetchPlayerAnalytics } from "../../api-client/analytics";
import PlayerAnalyticsPanel from "./PlayerAnalyticsPanel";

function payload(overrides: Partial<PlayerAnalytics> = {}): PlayerAnalytics {
  return {
    playerId: 7,
    form: {
      value: 1.5, formAvg: 6, baselineAvg: 4.5, window: 5, baselineWindow: 38,
      formJornadas: 5, baselineJornadas: 30, recentPoints: [6, 6, 6, 6, 6],
    },
    consistency: { value: 80, mean: 5, sd: 1.25, window: 10, jornadas: 10, points: [5, 5] },
    momentum: [
      { windowDays: 1, fromDate: "2026-09-15", toDate: "2026-09-16", fromValue: 10, toValue: 11,
        days: 1, pct: 10, ratePerDay: 10, direction: "up" },
      { windowDays: 30, fromDate: null, toDate: "2026-09-16", fromValue: null, toValue: 11,
        days: null, pct: null, ratePerDay: null, direction: null },
    ],
    power: {
      score: 62.4, powerPpg: 0.77, qualityPpg: 5.1, rate: 4.6, rateMatches: 6, prior: 4.2,
      priorSource: "last_season", calibration: { a: 1.328, c: -0.839 }, availability: "injured",
      availabilityFactor: 0.15, recentJornadas: 10, referencePpg: 10,
    },
    valuation: {
      marketValue: 20_000_000, fairValue: 30_000_000, gapPct: 50, reason: null,
      fit: { intercept: 14.2, slope: 0.43, n: 104, rSquared: 0.51, pooled: false },
    },
    economy: { score: 91, basis: "percentile of the valuation gap among all valued players" },
    marketPrediction: {
      madeOn: "2026-09-16", modelVersion: "market-v1", predictedPct: -1.2, direction: "fall",
      confidence: "strong", retroactive: false, outcome: null,
      inputs: {
        asOf: "2026-09-16", lastMovePct: -1.2, previousSnapshot: "2026-09-09",
        previousMovePct: null, accelerationTerm: null, starterProbability: 80,
        previousStarterProbability: 80, starterTerm: 0, availabilityChange: null,
        availabilityTerm: null, freshPoints: null, freshPointsTerm: null, baseRateFallback: false,
      },
    },
    ...overrides,
  };
}

function renderPanel() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <PlayerAnalyticsPanel playerId={7} />
    </QueryClientProvider>,
  );
}

describe("PlayerAnalyticsPanel (ANALYTICS-05)", () => {
  beforeEach(() => vi.mocked(fetchPlayerAnalytics).mockReset());

  it("shows each metric with its inputs and window", async () => {
    vi.mocked(fetchPlayerAnalytics).mockResolvedValue(payload());
    renderPanel();

    expect(await screen.findByText("62")).toBeInTheDocument(); // Power
    expect(screen.getByText("91")).toBeInTheDocument(); // Economy
    expect(screen.getByText(/Last 5 jornadas avg 6.00/)).toBeInTheDocument();
    expect(screen.getByText(/fitted on 104/)).toBeInTheDocument();
    expect(screen.getByText(/over the last 10 of 10/)).toBeInTheDocument();
    expect(screen.getByText("no snapshot that far back")).toBeInTheDocument();
    expect(screen.getByText(/strong/)).toBeInTheDocument();
    expect(screen.getByText(/× 0.15 \(injured\)/)).toBeInTheDocument();
    expect(screen.getByText(/log-log/)).toBeInTheDocument();
    expect(screen.queryByText(/exp\(/)).not.toBeInTheDocument();
    expect(screen.getByText(/\^/)).toBeInTheDocument();
  });

  it("says why there is no valuation instead of showing a number", async () => {
    vi.mocked(fetchPlayerAnalytics).mockResolvedValue(
      payload({
        valuation: { marketValue: 1, fairValue: null, gapPct: null, reason: "no points in the recent window", fit: null },
        economy: { score: null, basis: "x" },
      }),
    );
    renderPanel();
    expect(await screen.findByText(/No valuation: no points in the recent window/)).toBeInTheDocument();
  });

  it("refetches with the momentum windows the owner toggles", async () => {
    vi.mocked(fetchPlayerAnalytics).mockResolvedValue(payload());
    renderPanel();
    await screen.findByText("62");
    await userEvent.click(screen.getByRole("button", { name: "60d" }));
    await waitFor(() =>
      expect(fetchPlayerAnalytics).toHaveBeenLastCalledWith(7, [1, 7, 14, 30, 60]),
    );
  });
});
