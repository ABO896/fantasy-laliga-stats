import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PlayerDetailResponse } from "../api-client/player-detail";

vi.mock("../api-client/player-detail", async () => {
  const actual = await vi.importActual<typeof import("../api-client/player-detail")>(
    "../api-client/player-detail",
  );
  return { ...actual, fetchPlayerDetail: vi.fn() };
});

import { fetchPlayerDetail, PlayerNotFoundError } from "../api-client/player-detail";

vi.mock("../api-client/watchlist", () => ({
  fetchWatchlist: vi.fn(),
  addToWatchlist: vi.fn(),
  removeFromWatchlist: vi.fn(),
}));

import { addToWatchlist, fetchWatchlist } from "../api-client/watchlist";
import PlayerDetail from "./PlayerDetail";

function detail(overrides: Partial<PlayerDetailResponse> = {}): PlayerDetailResponse {
  return {
    asOf: "2026-08-27",
    player: {
      playerId: 412,
      externalId: "p-412",
      name: "Player One",
      team: "Team A",
      position: "DEL",
    },
    latest: {
      marketValue: 18_400_000,
      idealBid: null,
      maxBid: null,
      priceChangeAbs: 320_000,
      priceChangePct: 1.8,
      points: 12,
      pricePerPoint: 1.53,
      starterProbability: 0.87,
      availabilityStatus: "available",
      nextOpponent: "GET",
    },
    valueHistory: [{ asOf: "2026-08-27", marketValue: 18_400_000 }],
    gameweekPoints: [],
    seasonWeekRanges: { 2026: 2 },
    seasonStats: [],
    squad: null,
    predictions: {},
    ...overrides,
  };
}

function renderAt(playerId: number) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/players/${playerId}`]}>
        <Routes>
          <Route path="/players/:playerId" element={<PlayerDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname + location.search}</div>;
}

/** Mirrors a real click-through: a browser-list entry (carrying its own
 * filter/sort querystring) pushed to a player-page entry, exactly what
 * `PlayerTable`'s row link and the pitch card's link do. */
function renderArrivedFromBrowser(playerId: number, browserSearch: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[`/${browserSearch}`, `/players/${playerId}`]}
        initialIndex={1}
      >
        <Routes>
          <Route path="/players/:playerId" element={<PlayerDetail />} />
          <Route path="/" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** A pasted/bookmarked link: the player page is the only entry in the
 * history stack, so there is nothing for "back" to pop to. */
function renderAsTheOnlyEntry(playerId: number) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/players/${playerId}`]}>
        <Routes>
          <Route path="/players/:playerId" element={<PlayerDetail />} />
          <Route path="/" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PlayerDetail", () => {
  // `vi.clearAllMocks()` here, not `vi.mocked(fetchPlayerDetail).mockReset()`:
  // resetting this specific spy instance (via `.mockReset()`/`.mockClear()`)
  // races Vitest 4's own promise-result tracking in `@vitest/spy` when the
  // very next statement gives it a rejecting implementation — the mock's
  // rejection can end up unhandled from Vitest's perspective even though
  // react-query's retryer attaches its `.catch()` synchronously. Confirmed
  // by direct repro: swapping to the global `vi.clearAllMocks()` clears the
  // same state without hitting that race. Same intent as the brief's
  // `mockReset()`, different call shape.
  beforeEach(() => vi.clearAllMocks());

  it("shows the player's identity once loaded", async () => {
    vi.mocked(fetchPlayerDetail).mockResolvedValue(detail());
    renderAt(412);
    expect(await screen.findByRole("heading", { name: /Player One/ })).toBeInTheDocument();
    expect(screen.getByText(/Team A/)).toBeInTheDocument();
  });

  it("fetches the id from the route", async () => {
    vi.mocked(fetchPlayerDetail).mockResolvedValue(detail());
    renderAt(412);
    await waitFor(() => expect(fetchPlayerDetail).toHaveBeenCalledWith(412));
  });

  it("reports a missing player as not found rather than as a failure", async () => {
    vi.mocked(fetchPlayerDetail).mockRejectedValue(new PlayerNotFoundError());
    renderAt(999);
    expect(await screen.findByText(/no player with that id/i)).toBeInTheDocument();
  });

  it("offers a retry when the request fails for any other reason", async () => {
    vi.mocked(fetchPlayerDetail).mockRejectedValue(new Error("boom"));
    renderAt(412);
    expect(await screen.findByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("the back link returns to the browser exactly as it was left, filters and all", async () => {
    vi.mocked(fetchPlayerDetail).mockResolvedValue(detail());
    renderArrivedFromBrowser(412, "?pos=DEL&sort=points&dir=desc");
    await screen.findByRole("heading", { name: /Player One/ });

    await userEvent.click(screen.getByRole("button", { name: /back to the player browser/i }));

    expect(screen.getByTestId("location")).toHaveTextContent("/?pos=DEL&sort=points&dir=desc");
  });

  it("falls back to the bare browser when there is no history entry to pop", async () => {
    // A pasted link or a fresh session: `renderAsTheOnlyEntry` never pushed
    // a browser-list entry, so popping one would leave the app's own route
    // tree entirely rather than landing on the browser.
    vi.mocked(fetchPlayerDetail).mockResolvedValue(detail());
    renderAsTheOnlyEntry(412);
    await screen.findByRole("heading", { name: /Player One/ });

    await userEvent.click(screen.getByRole("button", { name: /back to the player browser/i }));

    expect(screen.getByTestId("location")).toHaveTextContent("/");
  });

  it("the not-found page's back action also returns to the browser as it was left", async () => {
    vi.mocked(fetchPlayerDetail).mockRejectedValue(new PlayerNotFoundError());
    renderArrivedFromBrowser(999, "?pos=DEL");
    await screen.findByText(/no player with that id/i);

    await userEvent.click(screen.getByRole("button", { name: /back to the player browser/i }));

    expect(screen.getByTestId("location")).toHaveTextContent("/?pos=DEL");
  });

  describe("watchlist and compare entry points (DETAIL-04, DETAIL-06)", () => {
    it("stars the player from their page", async () => {
      vi.mocked(fetchPlayerDetail).mockResolvedValue(detail());
      vi.mocked(fetchWatchlist).mockResolvedValue({ playerIds: [] });
      vi.mocked(addToWatchlist).mockResolvedValue({ playerIds: [412] });
      renderAt(412);

      await userEvent.click(
        await screen.findByRole("button", { name: "Add Player One to watchlist" }),
      );
      expect(addToWatchlist).toHaveBeenCalledWith(412);
      await screen.findByRole("button", { name: "Remove Player One from watchlist" });
    });

    it("links to a comparison with this player already in the first slot", async () => {
      vi.mocked(fetchPlayerDetail).mockResolvedValue(detail());
      vi.mocked(fetchWatchlist).mockResolvedValue({ playerIds: [] });
      renderAt(412);

      const link = await screen.findByRole("link", { name: /compare/i });
      expect(link).toHaveAttribute("href", "/compare?a=412");
    });
  });
});
