import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import type { SeasonsResponse } from "../api-client/stats";

vi.mock("../api-client/stats", async () => {
  const actual = await vi.importActual<typeof import("../api-client/stats")>("../api-client/stats");
  return {
    ...actual,
    fetchStatsSeasons: vi.fn(),
    fetchJornadaScores: vi.fn().mockResolvedValue({
      week: 1, isProvisional: false,
      tiers: [
        { label: "≤0", min: null, max: 0, count: 0 },
        { label: "1–3", min: 1, max: 3, count: 0 },
        { label: "4–6", min: 4, max: 6, count: 0 },
        { label: "7–9", min: 7, max: 9, count: 0 },
        { label: "10+", min: 10, max: null, count: 0 },
      ],
      scores: [], teams: [],
    }),
  };
});
vi.mock("../api-client/players", async () => {
  const actual = await vi.importActual<typeof import("../api-client/players")>("../api-client/players");
  return { ...actual, fetchPlayers: vi.fn().mockResolvedValue({ as_of: null, players: [] }) };
});

import { fetchStatsSeasons } from "../api-client/stats";
import StatsPage from "./StatsPage";

function seasons(): SeasonsResponse {
  return { seasons: [2026, 2025], seasonWeekRanges: { "2026": 3, "2025": 36 } };
}

let capturedSearch = "";
function LocationSpy() {
  capturedSearch = useLocation().search;
  return null;
}

function renderPage(initialPath = "/stats") {
  const client = new QueryClient();
  capturedSearch = "";
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route
            path="/stats"
            element={
              <>
                <LocationSpy />
                <StatsPage />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.mocked(fetchStatsSeasons).mockReset());

describe("StatsPage", () => {
  it("defaults to the Scores tab and the latest season", async () => {
    vi.mocked(fetchStatsSeasons).mockResolvedValue(seasons());
    renderPage();
    await waitFor(() => expect(screen.getByText("Jornada")).toBeInTheDocument());
    expect(screen.getByRole("option", { name: "2026/27" })).toBeInTheDocument();
  });

  it("switches tabs and reflects it in the URL", async () => {
    vi.mocked(fetchStatsSeasons).mockResolvedValue(seasons());
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(screen.getByText("Jornada")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Streaks" }));

    await waitFor(() => expect(screen.getByText("Window")).toBeInTheDocument());
    expect(capturedSearch).toContain("tab=streaks");
  });

  it("shows the empty state when no season has data", async () => {
    vi.mocked(fetchStatsSeasons).mockResolvedValue({ seasons: [], seasonWeekRanges: {} });
    renderPage();
    await waitFor(() => expect(screen.getByText("No league stats yet")).toBeInTheDocument());
  });

  it("restores tab and season from the URL", async () => {
    vi.mocked(fetchStatsSeasons).mockResolvedValue(seasons());
    renderPage("/stats?tab=streaks&season=2025");
    await waitFor(() => expect(screen.getByText("Window")).toBeInTheDocument());
    expect(screen.getByRole("option", { name: "2025/26" })).toBeInTheDocument();
  });

  it("opens the Market model tab even when no season has jornada data", async () => {
    vi.mocked(fetchStatsSeasons).mockResolvedValue({ seasons: [], seasonWeekRanges: {} });
    renderPage("/stats?tab=market");
    await waitFor(() =>
      expect(screen.getByText(/inference under partial observation/)).toBeInTheDocument(),
    );
    expect(screen.queryByText("No league stats yet")).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });
});
