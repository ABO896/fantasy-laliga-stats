import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ExpectedPointsPrediction } from "../../api-client/expected-points";

vi.mock("../../api-client/expected-points", async () => {
  const actual = await vi.importActual<typeof import("../../api-client/expected-points")>(
    "../../api-client/expected-points",
  );
  return { ...actual, fetchPlayerExpectedPoints: vi.fn() };
});

import { describeBasis, fetchPlayerExpectedPoints } from "../../api-client/expected-points";
import ExpectedPointsLine from "./ExpectedPointsLine";

function prediction(overrides: Partial<ExpectedPointsPrediction> = {}): ExpectedPointsPrediction {
  return {
    playerId: 7,
    seasonYear: 2026,
    jornada: 8,
    expectedPoints: 5.04,
    basis: "form+starter+odds",
    opponent: "Getafe",
    isHome: false,
    locksAt: null,
    updatedAt: "2026-10-05T12:00:00+00:00",
    modelVersion: "xp-2",
    inputs: {
      modelVersion: "xp-2",
      rate: {
        value: 4.1, matches: 5, recentPoints: [6, 2, 8], halfLife: 5, prior: 3.2,
        priorSource: "last_season", priorWeight: 5,
      },
      starterProbability: 90,
      availability: "available",
      fixture: {
        opponent: "Getafe", isHome: false, teamGoals: 1.62, cleanSheet: 0.31,
        oddsSource: "football-data",
      },
      terms: { rate: 1.8, rateXStarter: 3.3, starter: 1.4, attack: 0.07, cleanSheet: -0.01 },
    },
    ...overrides,
  };
}

function renderLine() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ExpectedPointsLine playerId={7} />
    </QueryClientProvider>,
  );
}

describe("ExpectedPointsLine (MODEL-02)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows xP, the jornada, the fixture, the basis and every input", async () => {
    vi.mocked(fetchPlayerExpectedPoints).mockResolvedValue({ playerId: 7, prediction: prediction() });
    renderLine();
    expect(await screen.findByText("5.0 xP")).toBeInTheDocument();
    expect(screen.getByText(/jornada 8 · at Getafe/)).toBeInTheDocument();
    expect(
      screen.getByText("Basis: recent points + starter probability + match odds."),
    ).toBeInTheDocument();
    expect(screen.getByText(/starter 90%/)).toBeInTheDocument();
    expect(screen.getByText(/team expected goals 1.62, clean sheet 31%/)).toBeInTheDocument();
    expect(screen.getByText(/rate × starter \+3.30/)).toBeInTheDocument();
  });

  it("says so when no prediction is stored", async () => {
    vi.mocked(fetchPlayerExpectedPoints).mockResolvedValue({ playerId: 7, prediction: null });
    renderLine();
    expect(await screen.findByText(/No prediction stored yet/)).toBeInTheDocument();
  });

  it("names a blank jornada as such", () => {
    expect(describeBasis("no_fixture")).toBe("his team has no fixture this jornada");
    expect(describeBasis(null)).toBe("no prediction yet");
  });
});
