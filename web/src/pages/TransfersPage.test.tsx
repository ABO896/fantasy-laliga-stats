import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  BargainsResponse,
  BestResponse,
  BidsResponse,
  Envelope,
  Freshness,
  SuggestionsResponse,
  TransferPlayer,
} from "../api-client/transfers";

vi.mock("../api-client/transfers", async () => {
  const actual = await vi.importActual<typeof import("../api-client/transfers")>(
    "../api-client/transfers",
  );
  return {
    ...actual,
    fetchSuggestions: vi.fn(),
    fetchBargains: vi.fn(),
    fetchBest: vi.fn(),
    fetchBids: vi.fn(),
  };
});

import {
  fetchBargains,
  fetchBest,
  fetchBids,
  fetchSuggestions,
  transferParams,
} from "../api-client/transfers";
import TransfersPage from "./TransfersPage";

const FRESH: Freshness = { confidence: 1, label: "high", reasons: [], datasets: [] };
const STALE: Freshness = {
  confidence: 0.41,
  label: "low",
  reasons: ["Prices are 4 market updates behind — refresh before acting."],
  datasets: [],
};

function env(freshness: Freshness = FRESH): Envelope {
  return {
    serverTime: "2026-09-27T10:00:00Z",
    asOf: "2026-09-27",
    jornadas: { requested: 3, window: [8, 9, 10], spreadOver: 3 },
    ceiling: null,
    expectedPointsUsed: false,
    freshness,
  };
}

function player(playerId: number, name: string, extra: Partial<TransferPlayer> = {}): TransferPlayer {
  return {
    playerId, name, team: "Levante", position: "DEL", owned: false, marketValue: 4_600_000,
    availability: "available", starterProbability: 80, recentJornadas: 10, powerScore: 40, powerRank: null,
    economyScore: 80, fairValue: 9_000_000, valuationGapPct: 95, predictedPct: 1.2,
    predictionConfidence: "strong", expectedReturn: 5.2, expectedPoints: null,
    expectedPointsUsed: false, backwardPpg: 4.8, minutesFactor: 0.9, fixtureMultiplier: 1.1,
    fixtureDataAvailable: true,
    fixtures: [{ matchday: 8, kickoffUtc: "2026-10-03T14:00:00Z", kickoffConfirmed: true,
                 opponent: "Malaga", isHome: true, difficulty: 0.44, label: "vs Malaga (0.44)" }],
    fixtureDriver: { matchday: 8, kickoffUtc: "2026-10-03T14:00:00Z", kickoffConfirmed: true,
                     opponent: "Malaga", isHome: true, difficulty: 0.44, label: "vs Malaga (0.44)" },
    efficiency: 1.13, holdValue: 16.2, evidence: 1,
    bids: { ourIdeal: 4_655_000, ourMax: 5_100_000, sourceIdeal: 4_600_000, sourceMax: 4_700_000,
            inputs: { horizonUpdates: 3, surplusShare: 0.1, maxPremium: 0.25 } },
    verdict: { label: "Fair price", reason: "No strong signal either way." },
    ...extra,
  };
}

function suggestions(freshness: Freshness = FRESH): SuggestionsResponse {
  return {
    ...env(freshness),
    squadSize: 24, maxSquadSize: 24, unassessedMembers: [],
    moves: [{
      kind: "swap",
      sell: player(1, "Pérez", {
        owned: true, expectedReturn: 0,
        verdict: { label: "Sell high", reason: "Price is falling with drop risk." },
      }),
      buy: player(2, "Brugué", { verdict: { label: "Elite", reason: "Top-quarter quality." } }),
      gain: 17.7,
      signals: [
        { name: "points", text: "Best XI +5.2 expected pts/jornada over 3 jornadas", contribution: 15.6 },
        { name: "fixtures", text: "Brugué: vs Malaga (0.44) (×1.10)", contribution: null },
      ],
      confidence: freshness.confidence,
      confidenceLabel: freshness.label,
      confidenceReasons: freshness.reasons,
      feasibleFormations: ["4-4-2", "4-3-3"],
      phrase: "Sell Pérez (Sell high) → buy Brugué (Elite)",
    }],
  };
}

const BARGAINS: BargainsResponse = {
  ...env(), affordableOnly: false,
  players: [{ ...player(3, "O. Rey", { position: "MED" }), forwardFairValue: 13_000_000,
              forwardGapPct: 506 }],
};

function best(extra: Partial<BestResponse> = {}): BestResponse {
  return { ...env(), position: "DEL", affordableOnly: false, ceilingMissing: true,
           players: [player(4, "Mbappé", { marketValue: 143_000_000 })], ...extra };
}

const BIDS: BidsResponse = {
  serverTime: "", asOf: "2026-09-27", freshness: FRESH,
  players: [{ playerId: 4, name: "Mbappé", team: "Real Madrid", position: "DEL",
              marketValue: 143_225_708, availability: "available", ourIdeal: 144_260_000,
              ourMax: 149_010_000, sourceIdeal: 144_933_088, sourceMax: 146_297_230,
              inputs: { horizonUpdates: 3, surplusShare: 0.1, maxPremium: 0.25 } }],
};

function renderPage(url = "/transfers") {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[url]}>
        <TransfersPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("TransfersPage (TRANSFER-01…05, MODEL-05)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchSuggestions).mockResolvedValue(suggestions());
    vi.mocked(fetchBargains).mockResolvedValue(BARGAINS);
    vi.mocked(fetchBest).mockResolvedValue(best());
    vi.mocked(fetchBids).mockResolvedValue(BIDS);
  });

  it("shows sell → buy moves with the signals that drove them", async () => {
    renderPage();
    const moves = await screen.findByRole("region", { name: "Suggested moves" });
    expect(await within(moves).findByText("Pérez")).toBeInTheDocument();
    expect(within(moves).getByText("Brugué")).toBeInTheDocument();
    expect(within(moves).getByText(/Best XI \+5.2/)).toBeInTheDocument();
    expect(within(moves).getByText(/vs Malaga/)).toBeInTheDocument();
    expect(within(moves).getByText(/high confidence/)).toBeInTheDocument();
  });

  it("leads each move's heading with the server's phrase, and shows a chip per player (Plan C Task 6)", async () => {
    renderPage();
    const moves = await screen.findByRole("region", { name: "Suggested moves" });
    expect(
      await within(moves).findByText("Sell Pérez (Sell high) → buy Brugué (Elite)"),
    ).toBeInTheDocument();
    expect(within(moves).getByText("Sell high")).toBeInTheDocument();
    expect(within(moves).getByText("Elite")).toBeInTheDocument();
  });

  it("visibly loses confidence when the data is stale, and says why", async () => {
    vi.mocked(fetchSuggestions).mockResolvedValue(suggestions(STALE));
    renderPage();
    const moves = await screen.findByRole("region", { name: "Suggested moves" });
    expect(await within(moves).findByText(/less certain than they look/)).toBeInTheDocument();
    expect(within(moves).getAllByText(/4 market updates behind/).length).toBeGreaterThan(0);
    expect(within(moves).getByText(/low confidence/)).toBeInTheDocument();
  });

  it("passes the owner's ceiling from the URL, never a derived budget", async () => {
    renderPage("/transfers?max=5000000&basis=ourIdealBid&n=5");
    await screen.findByText("Pérez");
    expect(fetchSuggestions).toHaveBeenCalledWith({ n: 5, max: 5_000_000, basis: "ourIdealBid" });
    expect(fetchBargains).toHaveBeenCalledWith({ n: 5, max: 5_000_000, basis: "ourIdealBid" }, true);
  });

  it("lists bargains and our bids beside the source's, each bargain carrying its verdict chip", async () => {
    renderPage();
    expect(await screen.findByText("O. Rey")).toBeInTheDocument();
    const bargains = await screen.findByRole("region", { name: "Bargains" });
    expect(within(bargains).getByText("Fair price")).toBeInTheDocument();
    const bids = await screen.findByRole("region", { name: /Our bids/ });
    expect(await within(bids).findByText("€144.26M")).toBeInTheDocument();
    expect(within(bids).getByText("€144.93M")).toBeInTheDocument();
  });

  it("best by position: position picker and the within-budget toggle", async () => {
    renderPage();
    expect(await screen.findByText(/No price ceiling entered/)).toBeInTheDocument();
    expect(fetchBest).toHaveBeenLastCalledWith(expect.anything(), "DEL", true);

    fireEvent.click(screen.getByRole("button", { name: "MED" }));
    await vi.waitFor(() =>
      expect(fetchBest).toHaveBeenLastCalledWith(expect.anything(), "MED", true),
    );
    fireEvent.click(screen.getByRole("checkbox", { name: /Within budget only/ }));
    await vi.waitFor(() =>
      expect(fetchBest).toHaveBeenLastCalledWith(expect.anything(), "MED", false),
    );
  });

  it("best by position shows Power with its within-position rank (final review #9)", async () => {
    vi.mocked(fetchBest).mockResolvedValue(
      best({ players: [player(4, "Mbappé", { powerScore: 71.2, powerRank: { rank: 2, of: 40 } })] }),
    );
    renderPage();
    const cell = await screen.findByTitle("#2 of 40 DEL by Power");
    expect(cell.textContent).toBe("71 · #2");
  });

  it("an empty squad points to My Squad instead of an empty list", async () => {
    vi.mocked(fetchSuggestions).mockResolvedValue({ ...suggestions(), squadSize: 0, moves: [] });
    renderPage();
    expect(await screen.findByText(/Add your squad on My Squad first/)).toBeInTheDocument();
  });
});

describe("transferParams", () => {
  it("sends the basis only with a ceiling", () => {
    expect(transferParams({ n: 3, max: null, basis: "maxBid" })).toBe("n=3");
    expect(transferParams({ n: 3, max: 1_000_000, basis: "maxBid" }, { position: "POR" })).toBe(
      "n=3&max=1000000&basis=maxBid&position=POR",
    );
  });
});
