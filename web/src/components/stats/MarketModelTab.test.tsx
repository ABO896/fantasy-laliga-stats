import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  DivergenceResponse,
  MarketPredictionRow,
  RecordBucket,
  TrackRecordResponse,
} from "../../api-client/market-model";

vi.mock("../../api-client/market-model", async () => {
  const actual = await vi.importActual<typeof import("../../api-client/market-model")>(
    "../../api-client/market-model",
  );
  return {
    ...actual,
    fetchMarketPredictions: vi.fn(),
    fetchTrackRecord: vi.fn(),
    fetchDivergence: vi.fn(),
  };
});

vi.mock("../../api-client/verdict", async () => {
  const actual = await vi.importActual<typeof import("../../api-client/verdict")>(
    "../../api-client/verdict",
  );
  return { ...actual, fetchVerdictValidation: vi.fn() };
});

import {
  fetchDivergence,
  fetchMarketPredictions,
  fetchTrackRecord,
} from "../../api-client/market-model";
import { fetchVerdictValidation } from "../../api-client/verdict";
import { formatRate, tierRecord } from "../../lib/marketRecord";
import MarketModelTab from "./MarketModelTab";

const INPUTS = {
  asOf: "2026-09-16", lastMovePct: 1, previousSnapshot: null, previousMovePct: null,
  accelerationTerm: null, starterProbability: null, previousStarterProbability: null,
  starterTerm: null, availabilityChange: null, availabilityTerm: null, freshPoints: null,
  freshPointsTerm: null,
};

function row(playerId: number, name: string, pct: number): MarketPredictionRow {
  return {
    playerId, name, team: "T", position: "MED", marketValue: 10_000_000, madeOn: "2026-09-16",
    modelVersion: "market-v2", predictedPct: pct, direction: pct > 0 ? "rise" : "fall",
    lower: pct - 4, upper: pct + 4, horizonDays: 7,
    confidence: Math.abs(pct) >= 1 ? "strong" : "weak", inputs: INPUTS, retroactive: false,
    outcome: null,
  };
}

function bucket(scored: number, hits: number, pending = 0): RecordBucket {
  const b = { scored, hits, hitRate: scored ? hits / scored : null };
  return {
    ...b, pending,
    byConfidence: { strong: b, moderate: { scored: 0, hits: 0, hitRate: null }, weak: b },
    byScoring: { exact: b, interval: { scored: 0, hits: 0, hitRate: null } },
  };
}

function record(live: RecordBucket, retro: RecordBucket): TrackRecordResponse {
  return {
    modelVersion: "market-v1",
    ours: { live, retroactive: retro },
    days: [{ madeOn: "2026-09-09", predictions: 540, scored: 533, hits: 496, hitRate: 0.93,
             scoring: "interval", gapDays: 7, retroactive: true }],
    source: { scored: 44, hits: 42, hitRate: 42 / 44,
              oursOnSamePlayers: { scored: 44, hits: 40, hitRate: 40 / 44 } },
  };
}

const V2_RECORD: TrackRecordResponse = {
  modelVersion: "market-v2",
  ours: { live: bucket(0, 0, 16), retroactive: bucket(50, 40) },
  intervalCoverage: 0.82,
  mae: 1.2,
  naive: { rule: "next week repeats last week", hitRate: 0.6, mae: 1.8 },
};

const DIVERGENCE: DivergenceResponse = {
  asOf: "2026-09-16", agree: 0, disagree: 1, ourCallMissing: 0,
  rows: [{
    playerId: 3, name: "Antony", team: "T", position: "DEL", sourceList: "market_possible_risers",
    sourceDirection: "rise", status: "disagree",
    ours: { ...row(3, "Antony", -0.8), confidence: "weak" },
  }],
};

function renderTab() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <MarketModelTab />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("MarketModelTab (MODEL-01/03/04)", () => {
  beforeEach(() => {
    vi.mocked(fetchMarketPredictions).mockResolvedValue({
      madeOn: "2026-09-16", modelVersion: "market-v2",
      predictions: [row(1, "Riser", 2.1), row(2, "Faller", -1.4)],
    });
    vi.mocked(fetchTrackRecord).mockResolvedValue(V2_RECORD);
    vi.mocked(fetchDivergence).mockResolvedValue(DIVERGENCE);
    vi.mocked(fetchVerdictValidation).mockResolvedValue({ generatedAt: null, labels: [], disabledLabels: [] });
  });

  it("shows the verdict validation section, with the refresh instruction before a report exists (Plan C Task 6)", async () => {
    renderTab();
    expect(await screen.findByText("Verdict validation")).toBeInTheDocument();
    expect(await screen.findByText(/verdict_backtest --write/)).toBeInTheDocument();
  });

  it("renders the stored report's label rows once one exists", async () => {
    vi.mocked(fetchVerdictValidation).mockResolvedValue({
      generatedAt: "2026-10-01T00:00:00Z",
      disabledLabels: [],
      labels: [
        { label: "Sell high", metric: "price_pct", n: 40, players: 12, hitRate: 0.5,
          baseRate: 0.52, meanDiff: -0.1, ciLow: -0.3, ciHigh: 0.1, beatsChance: false },
      ],
    });
    renderTab();
    expect(await screen.findByText("Sell high")).toBeInTheDocument();
    expect(screen.getByText("✗")).toBeInTheDocument();
  });

  it("lists risers and fallers with their confidence", async () => {
    renderTab();
    expect(await screen.findByText("Riser")).toBeInTheDocument();
    expect(screen.getByText("Faller")).toBeInTheDocument();
    expect(screen.getByText("Likely risers")).toBeInTheDocument();
  });

  it("quotes the backtest, labelled as such, until live calls are scored", async () => {
    renderTab();
    expect(await screen.findByText(/backtest hit rates/)).toBeInTheDocument();
  });

  it("labels the predictions as a 7-day outlook with its range", async () => {
    renderTab();
    expect(await screen.findByText(/Next 7 days/)).toBeInTheDocument();
    expect(screen.getByText("-1.90% to +6.10%")).toBeInTheDocument(); // Riser 2.1 ± 4
  });

  it("shows disagreements with the source as a view", async () => {
    renderTab();
    expect(await screen.findByText("Where we disagree with the source")).toBeInTheDocument();
    expect(await screen.findByText("Antony")).toBeInTheDocument();
    expect(screen.getByText("disagree")).toBeInTheDocument();
  });

  it("shows only the 7-day model's track record, with no version toggle", async () => {
    renderTab();
    expect(await screen.findByText(/Interval coverage/)).toBeInTheDocument();
    expect(fetchTrackRecord).toHaveBeenCalledWith("market-v2");
    expect(screen.queryByText("v1 · next update")).not.toBeInTheDocument();
  });
});

describe("tierRecord / formatRate", () => {
  it("prefers the live record once anything live is scored", () => {
    expect(tierRecord(record(bucket(3, 2), bucket(10, 9))).label).toBe("live");
    expect(tierRecord(record(bucket(0, 0), bucket(10, 9))).label).toBe("backtest");
  });

  it("formats a rate with its sample, and a dash with none", () => {
    expect(formatRate({ scored: 4, hits: 3, hitRate: 0.75 })).toBe("75.0% (3/4)");
    expect(formatRate({ scored: 0, hits: 0, hitRate: null })).toBe("—");
  });
});
