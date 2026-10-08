import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PlayerBrowser from "./PlayerBrowser";
import type { PlayerRow, PlayersResponse } from "../api-client/players";

vi.mock("../api-client/players", () => ({
  fetchPlayers: vi.fn(),
}));

import { fetchPlayers } from "../api-client/players";

vi.mock("../api-client/watchlist", () => ({
  fetchWatchlist: vi.fn(),
  addToWatchlist: vi.fn(),
  removeFromWatchlist: vi.fn(),
}));

import { addToWatchlist, fetchWatchlist } from "../api-client/watchlist";

vi.mock("../api-client/verdict", async () => {
  const actual =
    await vi.importActual<typeof import("../api-client/verdict")>("../api-client/verdict");
  return {
    ...actual,
    fetchVerdictValidation: vi.fn().mockResolvedValue({
      generatedAt: null, labels: [], disabledLabels: [],
    }),
  };
});

import { fetchVerdictValidation } from "../api-client/verdict";

function buildPlayer(overrides: Partial<PlayerRow> & { playerId: number }): PlayerRow {
  return {
    externalId: `player-${overrides.playerId}`,
    name: `Player ${overrides.playerId}`,
    team: `Team ${overrides.playerId}`,
    position: "DEF",
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
    ...overrides,
  };
}

const aPlayer: PlayerRow = {
  playerId: 0,
  externalId: "player-0",
  name: "Player 0",
  team: "Team 0",
  position: "DEF",
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

function renderWithClient(ui: React.ReactElement, initialEntry = "/") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

function mockPlayers(players: PlayerRow[]) {
  const response: PlayersResponse = { as_of: "2026-08-06", players };
  vi.mocked(fetchPlayers).mockResolvedValue(response);
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.search}</div>;
}

describe("PlayerBrowser", () => {
  beforeEach(() => {
    vi.mocked(fetchWatchlist).mockResolvedValue({ playerIds: [] });
  });

  it("default_sort_is_efficiency_asc", async () => {
    const players = [
      buildPlayer({ playerId: 1, name: "Low Value", points: 10, pricePerPoint: 5 }),
      buildPlayer({ playerId: 2, name: "Best Value", points: 10, pricePerPoint: 1 }),
      buildPlayer({ playerId: 3, name: "No Points", points: 0, pricePerPoint: null }),
    ];
    mockPlayers(players);

    renderWithClient(<PlayerBrowser />);

    await screen.findByText("Best Value");
    // Ascending price/point: cheapest-per-point first, nulls always last
    // regardless of direction. Asserting the full rendered order (not just
    // the first row) means this test fails if the default flips back to
    // descending, not just if it drops the null-last rule.
    const names = screen
      .getAllByRole("row")
      .slice(1)
      .map((row) => within(row).getAllByRole("cell")[0]!.textContent);
    expect(names).toEqual(["Best Value", "Low Value", "No Points"]);
  });

  // Pre-season every player has zero points, so every efficiency is null and
  // the default sort has nothing to order on. Falling back to player id — the
  // final tie-break — puts the list in an order that means nothing to anyone.
  it("falls back to market value when no player has an efficiency yet", async () => {
    const players = [
      buildPlayer({ playerId: 1, name: "Cheap", marketValue: 1_000_000, pricePerPoint: null }),
      buildPlayer({ playerId: 2, name: "Dearest", marketValue: 90_000_000, pricePerPoint: null }),
      buildPlayer({ playerId: 3, name: "Mid", marketValue: 40_000_000, pricePerPoint: null }),
    ];
    mockPlayers(players);

    renderWithClient(<PlayerBrowser />);
    await screen.findByText("Dearest");

    const names = screen
      .getAllByRole("row")
      .slice(1)
      .map((row) => within(row).getAllByRole("cell")[0]!.textContent);
    expect(names).toEqual(["Dearest", "Mid", "Cheap"]);
  });

  // Efficiency still wins where it exists; value only breaks the tie.
  it("ranks by efficiency first and uses market value only to break a tie", async () => {
    const players = [
      buildPlayer({ playerId: 1, name: "Efficient", marketValue: 1_000_000, points: 10, pricePerPoint: 1 }),
      // Ids deliberately contradict the value order, so ordering by id would
      // put Poor first and this test would catch it.
      buildPlayer({ playerId: 5, name: "Rich No Points", marketValue: 90_000_000, pricePerPoint: null }),
      buildPlayer({ playerId: 3, name: "Poor No Points", marketValue: 2_000_000, pricePerPoint: null }),
    ];
    mockPlayers(players);

    renderWithClient(<PlayerBrowser />);
    await screen.findByText("Efficient");

    const names = screen
      .getAllByRole("row")
      .slice(1)
      .map((row) => within(row).getAllByRole("cell")[0]!.textContent);
    expect(names).toEqual(["Efficient", "Rich No Points", "Poor No Points"]);
  });

  it("default_columns", async () => {
    mockPlayers([buildPlayer({ playerId: 1 })]);
    renderWithClient(<PlayerBrowser />);

    await screen.findByText("Player 1");
    const table = within(screen.getByRole("table"));

    expect(table.getByText("Player")).toBeInTheDocument();
    expect(table.getByText("Team")).toBeInTheDocument();
    expect(table.getByText("Position")).toBeInTheDocument();
    expect(table.getByText("Market value")).toBeInTheDocument();
    expect(table.getByText("Points")).toBeInTheDocument();
    expect(table.getByText("€ / point")).toBeInTheDocument();

    expect(table.queryByText("Price change (%)")).not.toBeInTheDocument();
    expect(table.queryByText("Starter %")).not.toBeInTheDocument();
    expect(table.queryByText("Availability")).not.toBeInTheDocument();
  });

  // Both columns start hidden per D-06 (see PlayerTable.tsx), so this test
  // switches them on through the same toggle a real owner would use, rather
  // than asserting against a default render — the hidden-by-default state is
  // a deliberate decision this test must not invert.
  it("shows the ideal bid and max bid the scrape already collects", async () => {
    mockPlayers([
      buildPlayer({
        playerId: 1,
        name: "Raphinha",
        marketValue: 93_471_864,
        idealBid: 95_182_920,
        maxBid: 96_320_111,
      }),
    ]);
    renderWithClient(<PlayerBrowser />);

    await screen.findByText("Raphinha");

    fireEvent.click(screen.getByLabelText("Toggle column visibility"));
    fireEvent.click(screen.getByRole("checkbox", { name: "Ideal bid" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Max bid" }));

    expect(screen.getByRole("columnheader", { name: "Ideal bid" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Max bid" })).toBeInTheDocument();
    expect(screen.getByText("€95.18M")).toBeInTheDocument();
    expect(screen.getByText("€96.32M")).toBeInTheDocument();
  });

  it("disables the visibility checkbox for the column the price filter is currently keyed to", async () => {
    mockPlayers([
      buildPlayer({ playerId: 1, name: "Raphinha", marketValue: 93_000_000, idealBid: 95_000_000 }),
    ]);
    renderWithClient(<PlayerBrowser />);

    await screen.findByText("Raphinha");
    await userEvent.selectOptions(screen.getByLabelText("Price basis"), "idealBid");

    fireEvent.click(screen.getByLabelText("Toggle column visibility"));
    const idealBidCheckbox = screen.getByRole("checkbox", { name: "Ideal bid" });

    // The basis selector forces this column visible every render, so
    // unchecking it here would be a silent no-op — the checkbox is disabled
    // rather than left clickable but inert.
    expect(idealBidCheckbox).toBeDisabled();
    expect(screen.getByRole("columnheader", { name: "Ideal bid" })).toBeInTheDocument();

    // Switching the basis away frees the column up again. Changing the
    // basis select is a click outside the toggle's dropdown, which closes
    // it (see ColumnVisibilityToggle's click-outside handler) — reopen it
    // to check the checkbox's state.
    await userEvent.selectOptions(screen.getByLabelText("Price basis"), "marketValue");
    fireEvent.click(screen.getByLabelText("Toggle column visibility"));
    expect(screen.getByRole("checkbox", { name: "Ideal bid" })).not.toBeDisabled();
  });

  it("column_visibility_toggle", async () => {
    mockPlayers([buildPlayer({ playerId: 1, availabilityStatus: "injured" })]);
    renderWithClient(<PlayerBrowser />);

    await screen.findByText("Player 1");
    expect(within(screen.getByRole("table")).queryByText("Availability")).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Toggle column visibility"));
    fireEvent.click(screen.getByRole("checkbox", { name: "Availability" }));

    expect(screen.getAllByText("Availability").length).toBeGreaterThanOrEqual(1);
    expect(within(screen.getByRole("table")).getByText("injured")).toBeInTheDocument();
  });

  it("identical_stats_render_two_rows", async () => {
    const players = [
      buildPlayer({ playerId: 1, name: "Twin A", marketValue: 20_000_000, points: 15 }),
      buildPlayer({ playerId: 2, name: "Twin B", marketValue: 20_000_000, points: 15 }),
    ];
    mockPlayers(players);

    renderWithClient(<PlayerBrowser />);

    await screen.findByText("Twin A");
    expect(screen.getByText("Twin B")).toBeInTheDocument();
    const rows = await screen.findAllByRole("row");
    // header + 2 distinct body rows, never merged/deduplicated
    expect(rows).toHaveLength(3);
  });

  it("single_and_null_rendering", async () => {
    // Scores set so the one em dash asserted below is price/point's own —
    // every other visible-by-default numeric column (Task 7's Value/Plays/
    // 7d outlook, and Plan C Task 6's Verdict, included) gets a non-null
    // value too.
    mockPlayers([
      buildPlayer({
        playerId: 1, pricePerPoint: null, powerScore: 50, economyScore: 50, expectedPoints: 3,
        pointsValuePct: 40, reliabilityClass: "Regular", pStart: 0.6, outlookPct: 1.2,
        outlookDirection: "rise", dropRisk: false,
        verdict: { label: "Fair price", tags: [], confidence: "medium" },
      }),
    ]);
    renderWithClient(<PlayerBrowser />);

    await screen.findByText("Player 1");
    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(2);
    expect(screen.getByText("Player")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("zero_match_empty_state", async () => {
    mockPlayers([
      buildPlayer({ playerId: 1, position: "DEF" }),
      buildPlayer({ playerId: 2, position: "MED" }),
    ]);
    renderWithClient(<PlayerBrowser />);

    await screen.findByText("Player 1");

    fireEvent.click(screen.getByRole("checkbox", { name: "POR" }));

    expect(await screen.findByText("No players match these filters")).toBeInTheDocument();
    expect(
      screen.getByText("Try widening your position, team, availability, or price filters."),
    ).toBeInTheDocument();
    // the table header and sort indicator remain rendered, not replaced entirely
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(within(screen.getByRole("table")).getByText("€ / point")).toBeInTheDocument();
  });

  it("zero_match_does_not_throw", async () => {
    mockPlayers([buildPlayer({ playerId: 1, position: "DEF" })]);
    renderWithClient(<PlayerBrowser />);

    await screen.findByText("Player 1");

    fireEvent.click(screen.getByRole("checkbox", { name: "POR" }));
    await screen.findByText("No players match these filters");

    expect(() => {
      fireEvent.click(within(screen.getByRole("table")).getByText("Market value"));
    }).not.toThrow();
  });

  it("shows skeleton rows matching the default visible column count while loading", () => {
    vi.mocked(fetchPlayers).mockImplementation(() => new Promise(() => {}));
    renderWithClient(<PlayerBrowser />);

    const table = within(screen.getByRole("table", { name: "Loading players" }));
    expect(table.getAllByTestId("skeleton-row").length).toBeGreaterThan(0);
    const headerCells = table.getAllByTestId("skeleton-header-cell");
    expect(headerCells).toHaveLength(6); // matches the D-06 default visible column count
  });

  it("shows the error state with a working Try again control", async () => {
    vi.mocked(fetchPlayers).mockRejectedValue(new Error("network error"));
    renderWithClient(<PlayerBrowser />);

    expect(await screen.findByText("Couldn't load player data")).toBeInTheDocument();
    const retryButton = screen.getByRole("button", { name: "Try again" });

    vi.mocked(fetchPlayers).mockResolvedValue({
      as_of: "2026-08-06",
      players: [buildPlayer({ playerId: 1 })],
    });
    fireEvent.click(retryButton);

    expect(await screen.findByText("Player 1")).toBeInTheDocument();
  });

  it("preserves accented player names exactly, with the full value in the title attribute", async () => {
    mockPlayers([buildPlayer({ playerId: 1, name: "Íñigo Martínez Berridi" })]);
    renderWithClient(<PlayerBrowser />);

    const cell = await screen.findByText("Íñigo Martínez Berridi");
    expect(cell.getAttribute("title")).toBe("Íñigo Martínez Berridi");
    expect(cell.textContent).toBe("Íñigo Martínez Berridi");
  });

  it("filters to players at or below the price, on the chosen basis", async () => {
    vi.mocked(fetchPlayers).mockResolvedValue({
      as_of: "2026-08-21",
      players: [
        { ...aPlayer, playerId: 1, name: "Raphinha", marketValue: 93_000_000, idealBid: 95_000_000 },
        { ...aPlayer, playerId: 2, name: "Cardona", marketValue: 4_000_000, idealBid: 4_200_000 },
      ],
    });

    renderWithClient(<PlayerBrowser />);
    expect(await screen.findByText("Raphinha")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Max price (€M)"), "10");

    expect(screen.queryByText("Raphinha")).not.toBeInTheDocument();
    expect(screen.getByText("Cardona")).toBeInTheDocument();
  });

  it("treats an empty price box as no ceiling rather than a ceiling of zero", async () => {
    vi.mocked(fetchPlayers).mockResolvedValue({
      as_of: "2026-08-21",
      players: [{ ...aPlayer, playerId: 1, name: "Raphinha", marketValue: 93_000_000 }],
    });

    renderWithClient(<PlayerBrowser />);
    const box = await screen.findByLabelText("Max price (€M)");

    await userEvent.type(box, "10");
    expect(screen.queryByText("Raphinha")).not.toBeInTheDocument();

    await userEvent.clear(box);
    expect(await screen.findByText("Raphinha")).toBeInTheDocument();
  });

  it("switches which price the ceiling applies to", async () => {
    vi.mocked(fetchPlayers).mockResolvedValue({
      as_of: "2026-08-21",
      players: [
        // Inside budget at market value, outside it at the ideal bid — the
        // exact case the basis selector exists for.
        { ...aPlayer, playerId: 1, name: "Borderline", marketValue: 9_500_000, idealBid: 10_400_000 },
      ],
    });

    renderWithClient(<PlayerBrowser />);
    await userEvent.type(await screen.findByLabelText("Max price (€M)"), "10");
    expect(screen.getByText("Borderline")).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Price basis"), "idealBid");
    expect(screen.queryByText("Borderline")).not.toBeInTheDocument();
  });

  it("composes the price filter with a position facet", async () => {
    vi.mocked(fetchPlayers).mockResolvedValue({
      as_of: "2026-08-21",
      players: [
        { ...aPlayer, playerId: 1, name: "CheapDef", position: "DEF", marketValue: 3_000_000 },
        { ...aPlayer, playerId: 2, name: "CheapMed", position: "MED", marketValue: 3_000_000 },
        { ...aPlayer, playerId: 3, name: "PriceyDef", position: "DEF", marketValue: 20_000_000 },
      ],
    });

    renderWithClient(<PlayerBrowser />);
    await screen.findByText("CheapDef");

    fireEvent.click(screen.getByRole("checkbox", { name: "DEF" }));
    await userEvent.type(screen.getByLabelText("Max price (€M)"), "10");

    // Only the player that satisfies both facets survives — position and
    // price compose as AND, same as any other two facets.
    expect(screen.getByText("CheapDef")).toBeInTheDocument();
    expect(screen.queryByText("CheapMed")).not.toBeInTheDocument();
    expect(screen.queryByText("PriceyDef")).not.toBeInTheDocument();
  });

  it("reaches the no-results empty state via the price filter alone", async () => {
    mockPlayers([buildPlayer({ playerId: 1, marketValue: 20_000_000 })]);
    renderWithClient(<PlayerBrowser />);

    await screen.findByText("Player 1");

    await userEvent.type(screen.getByLabelText("Max price (€M)"), "1");

    expect(await screen.findByText("No players match these filters")).toBeInTheDocument();
    expect(
      screen.getByText("Try widening your position, team, availability, or price filters."),
    ).toBeInTheDocument();
  });

  it("opens a player from the browser", async () => {
    mockPlayers([buildPlayer({ playerId: 1, name: "Player One" })]);
    renderWithClient(<PlayerBrowser />);

    const link = await screen.findByRole("link", { name: "Player One" });
    expect(link).toHaveAttribute("href", "/players/1");
  });

  it("scrolls the table rather than the page", async () => {
    mockPlayers([buildPlayer({ playerId: 1, name: "Player One" })]);
    const { container } = renderWithClient(<PlayerBrowser />);

    // findByRole("table") alone would resolve against the loading skeleton
    // (which is also a <table>) before the real data renders — wait for an
    // actual row first, same as the other data-dependent tests in this file.
    await screen.findByText("Player One");
    expect(container.querySelector("[data-testid='player-table-scroll']")).toHaveClass(
      "overflow-x-auto",
    );
  });

  it("reflects the active filters in the URL", async () => {
    mockPlayers([
      buildPlayer({ playerId: 1, name: "Forward One", position: "DEL" }),
      buildPlayer({ playerId: 2, name: "Midfield One", position: "MED" }),
    ]);
    renderWithClient(
      <>
        <PlayerBrowser />
        <LocationProbe />
      </>,
    );

    await screen.findByRole("table");
    fireEvent.click(await screen.findByRole("checkbox", { name: "DEL" }));

    await waitFor(() =>
      expect(screen.getByTestId("location")).toHaveTextContent("pos=DEL"),
    );
  });

  it("reflects a column-header sort change in the URL", async () => {
    mockPlayers([
      buildPlayer({ playerId: 1, name: "Forward One", marketValue: 1_000_000 }),
      buildPlayer({ playerId: 2, name: "Midfield One", marketValue: 2_000_000 }),
    ]);
    renderWithClient(
      <>
        <PlayerBrowser />
        <LocationProbe />
      </>,
    );

    // The default sort (pricePerPoint, ascending) is applied uncontrolled by
    // PlayerTable and not reflected in the URL until the owner changes it —
    // clicking a header routes through TanStack's functional updater
    // (`(old) => new`), which PlayerTable must resolve before handing the
    // owner a concrete SortingState.
    await screen.findByText("Forward One");
    fireEvent.click(within(screen.getByRole("table")).getByText("Market value"));

    await waitFor(() =>
      expect(screen.getByTestId("location")).toHaveTextContent("sort=marketValue"),
    );
  });

  it("restores filters from the URL on mount", async () => {
    mockPlayers([
      buildPlayer({ playerId: 1, name: "Forward One", position: "DEL" }),
      buildPlayer({ playerId: 2, name: "Midfield One", position: "MED" }),
    ]);
    renderWithClient(<PlayerBrowser />, "/?pos=DEL");

    // findByRole("table") alone would resolve against the loading skeleton
    // (also a <table>) before the real data renders — wait for the real
    // row first, same as the other data-dependent tests in this file.
    await screen.findByText("Forward One");
    const table = screen.getByRole("table");
    expect(within(table).getByText("Forward One")).toBeInTheDocument();
    expect(within(table).queryByText("Midfield One")).not.toBeInTheDocument();
  });

  // The read path for sort (`searchParams.get("sort")`/`"dir"`) is entirely
  // separate code from the filter read path above — a bug there wouldn't be
  // caught by the filter-restoration test, so it needs its own coverage.
  it("restores sort from the URL on mount", async () => {
    mockPlayers([
      buildPlayer({ playerId: 1, name: "Low Scorer", points: 2 }),
      buildPlayer({ playerId: 2, name: "High Scorer", points: 20 }),
      buildPlayer({ playerId: 3, name: "Mid Scorer", points: 10 }),
    ]);
    renderWithClient(<PlayerBrowser />, "/?sort=points&dir=desc");

    await screen.findByText("High Scorer");
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1); // drop header
    expect(within(rows[0]!).getByText("High Scorer")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("Mid Scorer")).toBeInTheDocument();
    expect(within(rows[2]!).getByText("Low Scorer")).toBeInTheDocument();
  });

  // A hand-edited or truncated bookmark can carry a non-numeric `max`
  // (`?max=abc`). `Number("abc")` is `NaN`, which is `!== null`, so a naive
  // read would still surface it as an active price filter. `maxPriceFilter`
  // (columns.tsx) already treats a NaN filter value as "no constraint" at
  // the row level, so the table itself doesn't empty — but the raw NaN was
  // still leaking into `PlayerFilters`, corrupting every other consumer of
  // that state: `FilterSidebar` rendered a nonsensical "≤ €NaNM" active-filter
  // chip, and the max-price number input's controlled `value` became `NaN`.
  // A malformed `max` must degrade to "no ceiling" — no chip, no NaN — same
  // as `max` being absent, not leak downstream as a value nothing can use.
  it("treats a non-numeric max in the URL as no ceiling, not a corrupted NaN filter", async () => {
    mockPlayers([buildPlayer({ playerId: 1, name: "Player One", marketValue: 20_000_000 })]);

    renderWithClient(<PlayerBrowser />, "/?max=abc");

    expect(await screen.findByText("Player One")).toBeInTheDocument();
    expect(screen.queryByText("No players match these filters")).not.toBeInTheDocument();
    // No active-filter chip at all — a real ceiling would render one, and a
    // leaked NaN would render a broken "≤ €NaNM" one.
    expect(screen.queryByTestId("active-filter-chips")).not.toBeInTheDocument();
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Max price (€M)")).toHaveValue(null);
  });

  // Every filter dimension goes through the same generic setFilters(next)
  // path — this exercises team, availability, price basis and max price
  // together (positions and sort are already covered by their own tests
  // above) to confirm none of them was special-cased or missed.
  it("restores team, availability, price basis and max price filters from the URL together", async () => {
    vi.mocked(fetchPlayers).mockResolvedValue({
      as_of: "2026-08-21",
      players: [
        {
          ...aPlayer,
          playerId: 1,
          name: "Matches All",
          team: "Barcelona",
          availabilityStatus: "injured",
          idealBid: 9_000_000,
        },
        {
          ...aPlayer,
          playerId: 2,
          name: "Wrong Team",
          team: "Sevilla",
          availabilityStatus: "injured",
          idealBid: 9_000_000,
        },
        {
          ...aPlayer,
          playerId: 3,
          name: "Wrong Availability",
          team: "Barcelona",
          availabilityStatus: "available",
          idealBid: 9_000_000,
        },
        {
          ...aPlayer,
          playerId: 4,
          name: "Over Budget",
          team: "Barcelona",
          availabilityStatus: "injured",
          idealBid: 50_000_000,
        },
      ],
    });

    renderWithClient(
      <PlayerBrowser />,
      "/?team=Barcelona&avail=injured&basis=idealBid&max=10000000",
    );

    await screen.findByText("Matches All");
    expect(screen.queryByText("Wrong Team")).not.toBeInTheDocument();
    expect(screen.queryByText("Wrong Availability")).not.toBeInTheDocument();
    expect(screen.queryByText("Over Budget")).not.toBeInTheDocument();
  });
  describe("watchlist (DETAIL-04)", () => {
    it("stars a player from their row", async () => {
      mockPlayers([buildPlayer({ playerId: 1, name: "Pedri" })]);
      vi.mocked(addToWatchlist).mockResolvedValue({ playerIds: [1] });
      renderWithClient(<PlayerBrowser />);

      await userEvent.click(await screen.findByRole("button", { name: "Add Pedri to watchlist" }));

      expect(addToWatchlist).toHaveBeenCalledWith(1);
      await screen.findByRole("button", { name: "Remove Pedri from watchlist" });
    });

    it("filters to watchlisted players from the URL", async () => {
      mockPlayers([
        buildPlayer({ playerId: 1, name: "Watched" }),
        buildPlayer({ playerId: 2, name: "Not Watched" }),
      ]);
      vi.mocked(fetchWatchlist).mockResolvedValue({ playerIds: [1] });
      renderWithClient(<PlayerBrowser />, "/?watch=1");

      await screen.findByText("Watched");
      expect(screen.queryByText("Not Watched")).not.toBeInTheDocument();
      expect(screen.getByRole("checkbox", { name: "Watchlist only" })).toBeChecked();
    });

    it("writes the watchlist filter to the URL", async () => {
      mockPlayers([buildPlayer({ playerId: 1, name: "Watched" })]);
      vi.mocked(fetchWatchlist).mockResolvedValue({ playerIds: [1] });
      renderWithClient(
        <>
          <PlayerBrowser />
          <LocationProbe />
        </>,
      );

      await userEvent.click(await screen.findByRole("checkbox", { name: "Watchlist only" }));
      expect(screen.getByTestId("location").textContent).toContain("watch=1");
    });

    it("says the watchlist is empty rather than blaming the filters", async () => {
      mockPlayers([buildPlayer({ playerId: 1, name: "Someone" })]);
      renderWithClient(<PlayerBrowser />, "/?watch=1");

      await screen.findByText("Your watchlist is empty");
      expect(screen.queryByText("Someone")).not.toBeInTheDocument();
    });
  });
});

describe("PlayerBrowser — disabled verdict labels (final review #11)", () => {
  it("hides the verdict filter for labels live verdicts skip", async () => {
    mockPlayers([buildPlayer({ playerId: 1, name: "Someone" })]);
    vi.mocked(fetchVerdictValidation).mockResolvedValueOnce({
      generatedAt: null, labels: [], disabledLabels: ["Rotation risk"],
    });
    renderWithClient(<PlayerBrowser />);
    await screen.findByText("Someone");
    await waitFor(() =>
      expect(screen.queryByLabelText("Rotation risk")).not.toBeInTheDocument(),
    );
    expect(screen.getByLabelText("Elite")).toBeInTheDocument();
  });
});
