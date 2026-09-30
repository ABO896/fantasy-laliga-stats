import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import type { ScoresResponse } from "../../api-client/stats";

vi.mock("../../api-client/stats", async () => {
  const actual = await vi.importActual<typeof import("../../api-client/stats")>("../../api-client/stats");
  return { ...actual, fetchJornadaScores: vi.fn() };
});

import { fetchJornadaScores } from "../../api-client/stats";
import ScoresTab from "./ScoresTab";

function response(overrides: Partial<ScoresResponse> = {}): ScoresResponse {
  return {
    week: 3,
    isProvisional: false,
    tiers: [
      { label: "≤0", min: null, max: 0, count: 1 },
      { label: "1–3", min: 1, max: 3, count: 0 },
      { label: "4–6", min: 4, max: 6, count: 2 },
      { label: "7–9", min: 7, max: 9, count: 0 },
      { label: "10+", min: 10, max: null, count: 0 },
    ],
    scores: [
      {
        playerId: 1,
        name: "Player One",
        team: "Team A",
        position: "DEL",
        points: 5,
        marketValue: 2_000_000,
        pricePerPoint: 400_000,
      },
    ],
    teams: [{ team: "Team A", totalPoints: 5, playerCount: 1, averagePoints: 5 }],
    ...overrides,
  };
}

function renderTab(maxWeek = 3) {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/stats"]}>
        <ScoresTab season={2026} maxWeek={maxWeek} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(fetchJornadaScores).mockReset();
});

describe("ScoresTab", () => {
  it("renders the team table once data loads", async () => {
    vi.mocked(fetchJornadaScores).mockResolvedValue(response());
    renderTab();
    await waitFor(() => expect(screen.getAllByText("Team A").length).toBeGreaterThan(0));
    expect(screen.getByText("Player One")).toBeInTheDocument();
  });

  it("shows a provisional badge when the jornada is still live", async () => {
    vi.mocked(fetchJornadaScores).mockResolvedValue(response({ isProvisional: true }));
    renderTab();
    await waitFor(() => expect(screen.getByText(/provisional/i)).toBeInTheDocument());
  });

  it("shows the empty state for a jornada with no rows", async () => {
    vi.mocked(fetchJornadaScores).mockResolvedValue(response({ scores: [], teams: [] }));
    renderTab();
    await waitFor(() =>
      expect(screen.getByText("No results recorded for this jornada yet.")).toBeInTheDocument(),
    );
  });

  it("defaults the jornada select to maxWeek", async () => {
    vi.mocked(fetchJornadaScores).mockResolvedValue(response());
    renderTab(3);
    await waitFor(() => expect(fetchJornadaScores).toHaveBeenCalledWith(2026, 3));
  });

  it("shows each player's current market value and price/point, and links their name", async () => {
    vi.mocked(fetchJornadaScores).mockResolvedValue(response());
    renderTab();

    await waitFor(() => expect(screen.getByText("Player One")).toBeInTheDocument());

    expect(screen.getByText("€2M")).toBeInTheDocument();
    expect(screen.getByText("€0.4M")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Player One" })).toHaveAttribute(
      "href",
      "/players/1",
    );
  });

  it("shows an em dash for market value and price/point when there's no snapshot yet", async () => {
    vi.mocked(fetchJornadaScores).mockResolvedValue(
      response({
        scores: [
          {
            playerId: 2,
            name: "New Player",
            team: "Team B",
            position: "MED",
            points: 3,
            marketValue: null,
            pricePerPoint: null,
          },
        ],
      }),
    );
    renderTab();

    await waitFor(() => expect(screen.getByText("New Player")).toBeInTheDocument());
    expect(screen.getAllByText("—")).toHaveLength(2);
  });
});
