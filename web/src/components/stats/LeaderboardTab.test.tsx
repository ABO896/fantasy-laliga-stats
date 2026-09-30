import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import type { LeaderboardResponse } from "../../api-client/stats";
import type { PlayersResponse } from "../../api-client/players";

vi.mock("../../api-client/stats", async () => {
  const actual = await vi.importActual<typeof import("../../api-client/stats")>("../../api-client/stats");
  return { ...actual, fetchLeaderboard: vi.fn() };
});
vi.mock("../../api-client/players", async () => {
  const actual = await vi.importActual<typeof import("../../api-client/players")>("../../api-client/players");
  return { ...actual, fetchPlayers: vi.fn() };
});

import { fetchLeaderboard } from "../../api-client/stats";
import { fetchPlayers } from "../../api-client/players";
import { STAT_OPTIONS } from "../../lib/statFields";
import LeaderboardTab from "./LeaderboardTab";

function leaderboard(overrides: Partial<LeaderboardResponse> = {}): LeaderboardResponse {
  return {
    stat: "goals",
    players: [
      { playerId: 1, name: "Player One", team: "Team A", position: "DEL", value: 9, totalPoints: 40 },
    ],
    ...overrides,
  };
}

function players(): PlayersResponse {
  return {
    as_of: "2026-09-14",
    players: [
      {
        playerId: 1, externalId: "p1", name: "Player One", team: "Team A", position: "DEL",
        marketValue: 0, idealBid: null, maxBid: null, priceChangeAbs: null, priceChangePct: null,
        points: 0, pricePerPoint: null, starterProbability: null, availabilityStatus: "available",
        nextOpponent: null,
      },
      {
        playerId: 2, externalId: "p2", name: "Player Two", team: "Team B", position: "MED",
        marketValue: 0, idealBid: null, maxBid: null, priceChangeAbs: null, priceChangePct: null,
        points: 0, pricePerPoint: null, starterProbability: null, availabilityStatus: "available",
        nextOpponent: null,
      },
    ],
  };
}

function renderTab() {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/stats"]}>
        <LeaderboardTab season={2026} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(fetchLeaderboard).mockReset();
  vi.mocked(fetchPlayers).mockReset();
  vi.mocked(fetchPlayers).mockResolvedValue(players());
});

describe("LeaderboardTab", () => {
  it("renders the leaderboard table once data loads", async () => {
    vi.mocked(fetchLeaderboard).mockResolvedValue(leaderboard());
    renderTab();
    await waitFor(() => expect(screen.getByText("Player One")).toBeInTheDocument());
    expect(screen.getByText("9")).toBeInTheDocument();
  });

  it("defaults to the alphabetically-first stat", async () => {
    vi.mocked(fetchLeaderboard).mockResolvedValue(leaderboard());
    renderTab();
    await waitFor(() => expect(fetchLeaderboard).toHaveBeenCalled());
    const [, stat] = vi.mocked(fetchLeaderboard).mock.calls[0];
    expect(stat).toBe(STAT_OPTIONS[0].field);
  });

  it("shows an empty state when no players match", async () => {
    vi.mocked(fetchLeaderboard).mockResolvedValue(leaderboard({ players: [] }));
    renderTab();
    await waitFor(() =>
      expect(screen.getByText("No players match this statistic and these filters.")).toBeInTheDocument(),
    );
  });

  it("populates the team filter from the full player roster, not the filtered leaderboard", async () => {
    vi.mocked(fetchLeaderboard).mockResolvedValue(leaderboard());
    renderTab();
    await waitFor(() => expect(screen.getByText("Player One")).toBeInTheDocument());
    expect(screen.getByRole("option", { name: "Team B" })).toBeInTheDocument();
  });
});
