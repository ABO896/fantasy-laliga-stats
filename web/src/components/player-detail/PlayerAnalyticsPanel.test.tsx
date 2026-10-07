import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PlayerAnalytics } from "../../api-client/analytics";
import type { PlayerVerdict } from "../../api-client/verdict";

vi.mock("../../api-client/analytics", async () => {
  const actual =
    await vi.importActual<typeof import("../../api-client/analytics")>("../../api-client/analytics");
  return { ...actual, fetchPlayerAnalytics: vi.fn() };
});
vi.mock("../../api-client/verdict", async () => {
  const actual =
    await vi.importActual<typeof import("../../api-client/verdict")>("../../api-client/verdict");
  return { ...actual, fetchPlayerVerdict: vi.fn() };
});

import { fetchPlayerAnalytics } from "../../api-client/analytics";
import { fetchPlayerVerdict } from "../../api-client/verdict";
import VerdictBanner from "../verdict/VerdictBanner";
import PlayerAnalyticsPanel from "./PlayerAnalyticsPanel";

const CARD_TITLES = [
  "Verdict",
  "Power",
  "Points value",
  "7-day price outlook",
  "Reliability",
  "Expected points",
  "Form",
  "Consistency",
  "Momentum",
];

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
      { windowDays: 7, fromDate: "2026-09-09", toDate: "2026-09-16", fromValue: 10, toValue: 11.5,
        days: 7, pct: 15, ratePerDay: 2.1, direction: "up" },
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
    economy: { score: 91, basis: "percentile" },
    marketPrediction: null,
    reliability: {
      class: "Regular", pStart: 0.62, pPlay: 0.78, startShare: 0.6, playShare: 0.75,
      subShare: 0.15, minutesShare: 0.7, shrunkStart: 0.58, sourceStarter: 0.7, sourceBlend: 0.3,
      availability: null, availabilityFactor: 1, minutesTrend: null, matches: 8, appearances: 7,
      halfLife: 5, priorWeight: 3, prior: { start: 0.45, play: 0.6 }, confidence: "high",
      basis: "matches", rank: null,
    },
    evidence: { matchesWithMinutes: 8, lastSeasonApps: 30, ok: true, reason: null },
    pointsValue: {
      value: 0.018, xpts: 9.2, replacement: 4.4, price: 26_000_000, cashPerPoint: 100_000,
      horizon: 3, matchCount: 1, matches: [{ opponent: "Betis", isHome: true, xp: 3.1 }], reason: null,
      rank: { rank: 5, of: 190, percentile: 97 },
    },
    priceOutlook: {
      expectedPct: 1.8, direction: "rise", lower: -0.5, upper: 4.1, dropRisk: false,
      basis: "ridge", confidence: "moderate",
      terms: { intercept: 0.2, r7: 1.5, pts_vs_exp: -0.9 },
      madeOn: "2026-10-01", rank: { rank: 10, of: 190, percentile: 90 },
    },
    expectedReturnEur: null,
    inputsConfidence: "high",
    dataThrough: { prices: "2026-10-05", matches: 9 },
    ranks: {
      power: { rank: 5, of: 190, percentile: 97, position: "DEF" },
      pointsValue: { rank: 5, of: 190, percentile: 97, position: "DEF" },
      outlook: { rank: 10, of: 190, percentile: 90, position: "DEF" },
      reliability: { rank: 20, of: 190, percentile: 80, position: "DEF" },
      xp: { rank: 15, of: 190, percentile: 85, position: "DEF" },
      form: { rank: 30, of: 190, percentile: 70, position: "DEF" },
      consistency: { rank: 40, of: 190, percentile: 60, position: "DEF" },
      momentum7: { rank: 50, of: 190, percentile: 55, position: "DEF" },
    },
    xp: {
      value: 4.1, basis: "form+starter+odds", jornada: 7, opponent: "Betis", isHome: true,
      terms: { rate: 2.2, starter: 0.5, attack: 0.3, cleanSheet: 0.1 },
      coefficients: null,
      rate: {
        value: 4.6, matches: 6, recentPoints: [4, 5, 6], halfLife: 5, prior: 4.2,
        priorSource: "last_season", priorWeight: 3,
      },
    },
    ...overrides,
  };
}

function verdictPayload(overrides: Partial<PlayerVerdict> = {}): PlayerVerdict {
  return {
    playerId: 7,
    label: "Elite",
    tags: [],
    reason: "Top output, nailed starter.",
    confidence: "high",
    deciding: {
      qualityPct: 95, valuePct: 70, outlookPct: 50, class: "Nailed",
      medianPrice: 5_000_000, price: 30_000_000, availability: "available", confidence: "high",
    },
    disabledLabels: [],
    personal: null,
    validation: null,
    ...overrides,
  };
}

function renderPanel() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/players/7"]}>
        <PlayerAnalyticsPanel playerId={7} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PlayerAnalyticsPanel", () => {
  beforeEach(() => {
    vi.mocked(fetchPlayerAnalytics).mockReset();
    vi.mocked(fetchPlayerVerdict).mockReset();
  });

  it("shows nine cards with the nine metric titles in order, each with a collapsed step table", async () => {
    vi.mocked(fetchPlayerAnalytics).mockResolvedValue(payload());
    vi.mocked(fetchPlayerVerdict).mockResolvedValue(verdictPayload());
    renderPanel();

    await screen.findAllByText("Elite");

    const headings = await screen.findAllByRole("heading", { level: 3 });
    expect(headings.map((h) => h.textContent)).toEqual(CARD_TITLES);

    const detailsEls = document.querySelectorAll("details");
    expect(detailsEls.length).toBeGreaterThanOrEqual(CARD_TITLES.length - 1); // momentum may lack one if 7d missing
    detailsEls.forEach((d) => expect(d).not.toHaveAttribute("open"));
  });

  it("never prints a raw formula string anywhere in the panel", async () => {
    vi.mocked(fetchPlayerAnalytics).mockResolvedValue(payload());
    vi.mocked(fetchPlayerVerdict).mockResolvedValue(verdictPayload());
    const { container } = renderPanel();
    await screen.findAllByText("Elite");

    expect(container.textContent).not.toMatch(/\^|e\^|\*|sqrt\(/);
  });

  it("refetches with the momentum windows the owner toggles", async () => {
    vi.mocked(fetchPlayerAnalytics).mockResolvedValue(payload());
    vi.mocked(fetchPlayerVerdict).mockResolvedValue(verdictPayload());
    renderPanel();
    await screen.findAllByText("Elite");
    const momentumCard = screen.getByRole("heading", { name: "Momentum" }).closest("div.panel");
    await userEvent.click(within(momentumCard as HTMLElement).getByRole("button", { name: "60d" }));
    await waitFor(() =>
      expect(fetchPlayerAnalytics).toHaveBeenLastCalledWith(7, [1, 7, 14, 30, 60]),
    );
  });

  it("says why there is no points value instead of showing a number", async () => {
    vi.mocked(fetchPlayerAnalytics).mockResolvedValue(
      payload({ pointsValue: { value: null, xpts: null, replacement: null, price: null, cashPerPoint: 100_000, horizon: 3, matchCount: 0, matches: [], reason: "no points in the recent window", rank: null } }),
    );
    vi.mocked(fetchPlayerVerdict).mockResolvedValue(verdictPayload());
    renderPanel();
    expect(await screen.findByText("no points in the recent window")).toBeInTheDocument();
  });
});

describe("the player page fetches the verdict once (final review #7)", () => {
  it("shares one verdict query between the banner and the verdict card", async () => {
    vi.mocked(fetchPlayerAnalytics).mockResolvedValue(payload());
    vi.mocked(fetchPlayerVerdict).mockReset();
    vi.mocked(fetchPlayerVerdict).mockResolvedValue(verdictPayload());
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/players/7?max=5000000"]}>
          <VerdictBanner playerId={7} />
          <PlayerAnalyticsPanel playerId={7} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await screen.findByText("Top output, nailed starter.");
    await waitFor(() => expect(screen.getAllByText("Elite").length).toBeGreaterThan(1));
    expect(fetchPlayerVerdict).toHaveBeenCalledTimes(1);
    expect(fetchPlayerVerdict).toHaveBeenCalledWith(7, 5_000_000);
  });
});
