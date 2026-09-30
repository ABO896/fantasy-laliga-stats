import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PlayerDetailResponse } from "../api-client/player-detail";
import type { PlayerRow } from "../api-client/players";

vi.mock("../api-client/player-detail", async () => {
  const actual = await vi.importActual<typeof import("../api-client/player-detail")>(
    "../api-client/player-detail",
  );
  return { ...actual, fetchPlayerDetail: vi.fn() };
});
vi.mock("../api-client/players", () => ({ fetchPlayers: vi.fn() }));
vi.mock("../api-client/watchlist", () => ({
  fetchWatchlist: vi.fn(),
  addToWatchlist: vi.fn(),
  removeFromWatchlist: vi.fn(),
}));

import { fetchPlayerDetail, PlayerNotFoundError } from "../api-client/player-detail";
import { fetchPlayers } from "../api-client/players";
import { fetchWatchlist } from "../api-client/watchlist";
import ComparePage from "./ComparePage";

function detail(id: number, name: string, points: number): PlayerDetailResponse {
  return {
    asOf: "2026-09-27",
    player: { playerId: id, externalId: `p-${id}`, name, team: `Team ${id}`, position: "MED" },
    latest: {
      marketValue: 10_000_000,
      idealBid: null,
      maxBid: null,
      priceChangeAbs: 0,
      priceChangePct: 0,
      points,
      pricePerPoint: null,
      starterProbability: null,
      availabilityStatus: "available",
      nextOpponent: null,
    },
    valueHistory: [{ asOf: "2026-09-27", marketValue: 10_000_000 }],
    gameweekPoints: [],
    seasonWeekRanges: {},
    seasonStats: [],
    squad: null,
    predictions: {},
  };
}

function listRow(playerId: number, name: string): PlayerRow {
  return {
    playerId,
    externalId: `p-${playerId}`,
    name,
    team: `Team ${playerId}`,
    position: "MED",
    marketValue: 10_000_000,
    idealBid: null,
    maxBid: null,
    priceChangeAbs: null,
    priceChangePct: null,
    points: 0,
    pricePerPoint: null,
    starterProbability: null,
    availabilityStatus: "available",
    nextOpponent: null,
  };
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.search}</div>;
}

function renderAt(search: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/compare${search}`]}>
        <Routes>
          <Route
            path="/compare"
            element={
              <>
                <ComparePage />
                <LocationProbe />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchWatchlist).mockResolvedValue({ playerIds: [] });
  vi.mocked(fetchPlayers).mockResolvedValue({
    as_of: "2026-09-27",
    players: [listRow(1, "Pedri"), listRow(2, "Bellingham"), listRow(3, "Aspas")],
  });
  vi.mocked(fetchPlayerDetail).mockImplementation(async (id: number) => {
    if (id === 1) return detail(1, "Pedri", 40);
    if (id === 2) return detail(2, "Bellingham", 55);
    if (id === 3) return detail(3, "Aspas", 30);
    throw new PlayerNotFoundError();
  });
});

describe("ComparePage", () => {
  it("asks for two players when none are chosen", async () => {
    renderAt("");
    expect(await screen.findByText(/pick two players to compare/i)).toBeInTheDocument();
    expect(await screen.findByRole("combobox", { name: "First player" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Second player" })).toBeInTheDocument();
  });

  it("shows both players side by side with the better value marked", async () => {
    renderAt("?a=1&b=2");

    expect(await screen.findByRole("link", { name: "Pedri" })).toHaveAttribute("href", "/players/1");
    expect(await screen.findByRole("link", { name: "Bellingham" })).toHaveAttribute(
      "href",
      "/players/2",
    );

    const table = within(screen.getByRole("table", { name: "Key stats" }));
    const pointsRow = table.getByRole("row", { name: /^Points/ });
    const cells = within(pointsRow).getAllByRole("cell");
    expect(cells[0]).toHaveTextContent("40");
    expect(cells[0]).not.toHaveAttribute("data-better");
    expect(cells[1]).toHaveTextContent("55");
    expect(cells[1]).toHaveAttribute("data-better", "true");
  });

  it("renders each player's market value history and points charts", async () => {
    renderAt("?a=1&b=2");
    await screen.findByRole("link", { name: "Bellingham" });
    // Each fixture holds one snapshot, so each side shows the value chart's
    // own single-point state — once per player.
    const values = within(screen.getByRole("region", { name: "Market value history" }));
    expect(values.getAllByText(/one day of history so far/)).toHaveLength(2);
    // Neither fixture has jornada rows, so each side shows the chart's own
    // empty state — once per player, not once for the page.
    expect(screen.getAllByText("No jornada scores recorded for this player.")).toHaveLength(2);
  });

  it("picking a player writes that slot to the URL, keeping the other", async () => {
    renderAt("?a=1");
    const second = await screen.findByRole("combobox", { name: "Second player" });
    await within(second).findByRole("option", { name: /Aspas/ });
    await userEvent.selectOptions(second, "3");

    const search = screen.getByTestId("location").textContent ?? "";
    expect(search).toContain("a=1");
    expect(search).toContain("b=3");
    expect(await screen.findByRole("link", { name: "Aspas" })).toBeInTheDocument();
  });

  it("an unknown player breaks only its own slot", async () => {
    renderAt("?a=1&b=999");
    expect(await screen.findByRole("link", { name: "Pedri" })).toBeInTheDocument();
    expect(await screen.findByText("Player not found")).toBeInTheDocument();
  });
});
