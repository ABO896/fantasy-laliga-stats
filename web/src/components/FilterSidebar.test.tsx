import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import FilterSidebar, { type PlayerFilters } from "./FilterSidebar";
import type { PlayerRow } from "../api-client/players";

function buildPlayer(overrides: Partial<PlayerRow> & { playerId: number }): PlayerRow {
  return {
    externalId: `player-${overrides.playerId}`,
    name: `Player ${overrides.playerId}`,
    team: "Real Zaragoza",
    position: "DEF",
    marketValue: 1_000_000,
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

const EMPTY: PlayerFilters = {
  positions: [],
  teams: [],
  availability: [],
  verdict: [],
  maxPrice: null,
  priceBasis: "marketValue",
};

function renderSidebar(value: PlayerFilters, players: PlayerRow[], onChange = vi.fn()) {
  render(<FilterSidebar value={value} onChange={onChange} players={players} />);
  return onChange;
}

describe("FilterSidebar", () => {
  const players = [
    buildPlayer({ playerId: 1, team: "Sevilla", position: "DEF" }),
    buildPlayer({ playerId: 2, team: "Alavés", position: "MED" }),
    buildPlayer({ playerId: 3, team: "Betis", position: "DEF" }),
  ];

  it("no_default_filters", () => {
    renderSidebar(EMPTY, players);
    expect(screen.queryByTestId("active-filter-chips")).not.toBeInTheDocument();
    expect(screen.queryByText("Clear all")).not.toBeInTheDocument();
  });

  it("within_facet_is_or (selecting two positions)", () => {
    const onChange = renderSidebar(EMPTY, players);
    fireEvent.click(screen.getByRole("checkbox", { name: "DEF" }));
    expect(onChange).toHaveBeenCalledWith({
      positions: ["DEF"],
      teams: [],
      availability: [],
      verdict: [],
      maxPrice: null,
      priceBasis: "marketValue",
    });
  });

  it("across_facet_is_and (position + availability both set)", () => {
    const value: PlayerFilters = {
      positions: ["DEF"],
      teams: [],
      availability: [],
      verdict: [],
      maxPrice: null,
      priceBasis: "marketValue",
    };
    const onChange = renderSidebar(value, players);
    fireEvent.click(screen.getByRole("checkbox", { name: "injured" }));
    expect(onChange).toHaveBeenCalledWith({
      positions: ["DEF"],
      teams: [],
      availability: ["injured"],
      verdict: [],
      maxPrice: null,
      priceBasis: "marketValue",
    });
  });

  it("empty_facet_is_no_constraint (deselecting restores unconstrained)", () => {
    const value: PlayerFilters = {
      positions: ["DEF"],
      teams: [],
      availability: [],
      verdict: [],
      maxPrice: null,
      priceBasis: "marketValue",
    };
    const onChange = renderSidebar(value, players);
    fireEvent.click(screen.getByRole("checkbox", { name: "DEF" }));
    expect(onChange).toHaveBeenCalledWith({
      positions: [],
      teams: [],
      availability: [],
      verdict: [],
      maxPrice: null,
      priceBasis: "marketValue",
    });
  });

  it("chips_reflect_active_filters", () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <FilterSidebar value={EMPTY} onChange={onChange} players={players} />,
    );
    expect(screen.queryByTestId("active-filter-chips")).not.toBeInTheDocument();

    const active: PlayerFilters = {
      positions: ["DEF"],
      teams: ["Sevilla"],
      availability: ["injured"],
      verdict: [],
      maxPrice: null,
      priceBasis: "marketValue",
    };
    rerender(<FilterSidebar value={active} onChange={onChange} players={players} />);

    const chips = screen.getByTestId("active-filter-chips");
    expect(chips.querySelectorAll("button")).toHaveLength(4); // 3 chips + Clear all
    expect(screen.getByText("Clear all")).toBeInTheDocument();

    fireEvent.click(screen.getByText(/DEF ×/));
    expect(onChange).toHaveBeenCalledWith({
      positions: [],
      teams: ["Sevilla"],
      availability: ["injured"],
      verdict: [],
      maxPrice: null,
      priceBasis: "marketValue",
    });
  });

  it("a_price_ceiling_alone_shows_a_chip_and_a_reachable_clear_all", () => {
    const value: PlayerFilters = {
      positions: [],
      teams: [],
      availability: [],
      verdict: [],
      maxPrice: 4_100_000,
      priceBasis: "idealBid",
    };
    const onChange = renderSidebar(value, players);

    const chips = screen.getByTestId("active-filter-chips");
    expect(chips).toBeInTheDocument();
    expect(screen.getByText(/€4\.1M \(Ideal bid \(Analítica\)\) ×/)).toBeInTheDocument();
    expect(screen.getByText("Clear all")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Clear all"));
    expect(onChange).toHaveBeenCalledWith({
      positions: [],
      teams: [],
      availability: [],
      verdict: [],
      maxPrice: null,
      priceBasis: "marketValue",
      watchlistOnly: false,
    });
  });

  it("clicking the price chip clears only the price, keeping other filters", () => {
    const value: PlayerFilters = {
      positions: ["DEF"],
      teams: [],
      availability: [],
      verdict: [],
      maxPrice: 4_100_000,
      priceBasis: "marketValue",
    };
    const onChange = renderSidebar(value, players);

    fireEvent.click(screen.getByText(/€4\.1M/));
    expect(onChange).toHaveBeenCalledWith({
      positions: ["DEF"],
      teams: [],
      availability: [],
      verdict: [],
      maxPrice: null,
      priceBasis: "marketValue",
    });
  });

  it("converts millions to euros exactly, without floating-point drift", () => {
    const onChange = renderSidebar(EMPTY, players);
    fireEvent.change(screen.getByLabelText("Max price (€M)"), { target: { value: "4.1" } });
    // 4.1 * 1_000_000 is 4099999.9999999995 in raw floating point — a naive
    // multiply would exclude a player priced at exactly this ceiling.
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ maxPrice: 4_100_000 }),
    );
  });

  it("verdict_facet_toggles_like_every_other_facet (Plan C Task 6)", () => {
    const onChange = renderSidebar(EMPTY, players);
    fireEvent.click(screen.getByRole("checkbox", { name: "Elite" }));
    expect(onChange).toHaveBeenCalledWith({
      positions: [],
      teams: [],
      availability: [],
      verdict: ["Elite"],
      maxPrice: null,
      priceBasis: "marketValue",
    });
  });

  it("verdict_options_follow_LABELS_priority_order_not_alphabetical", () => {
    renderSidebar(EMPTY, players);
    const legend = screen.getByText("Verdict").closest("fieldset")!;
    const labels = Array.from(legend.querySelectorAll("label")).map((l) => l.textContent?.trim());
    expect(labels).toEqual([
      "Unavailable",
      "Unproven",
      "Sell high",
      "Elite",
      "Bargain",
      "Rising",
      "Rotation risk",
      "Overpriced",
      "Avoid",
      "Fair price",
    ]);
  });

  it("teams_derived_from_data", () => {
    renderSidebar(EMPTY, players);
    const teamCheckboxes = [
      screen.getByRole("checkbox", { name: "Alavés" }),
      screen.getByRole("checkbox", { name: "Betis" }),
      screen.getByRole("checkbox", { name: "Sevilla" }),
    ];
    expect(teamCheckboxes).toHaveLength(3);

    const legend = screen.getByText("Team").closest("fieldset")!;
    const labels = Array.from(legend.querySelectorAll("label")).map((l) => l.textContent?.trim());
    expect(labels).toEqual(["Alavés", "Betis", "Sevilla"]);
  });
  describe("watchlist filter (DETAIL-04)", () => {
    it("is absent until the watchlist has loaded", () => {
      renderSidebar(EMPTY, players);
      expect(screen.queryByRole("checkbox", { name: "Watchlist only" })).not.toBeInTheDocument();
    });

    it("toggles on, and shows how many players are watched", () => {
      const onChange = vi.fn();
      render(
        <FilterSidebar value={EMPTY} onChange={onChange} players={players} watchlistCount={3} />,
      );
      expect(screen.getByText("3 watched")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("checkbox", { name: "Watchlist only" }));
      expect(onChange).toHaveBeenCalledWith({ ...EMPTY, watchlistOnly: true });
    });

    it("shows an active chip that clears only itself", () => {
      const onChange = vi.fn();
      const value: PlayerFilters = { ...EMPTY, positions: ["DEF"], watchlistOnly: true };
      render(
        <FilterSidebar value={value} onChange={onChange} players={players} watchlistCount={3} />,
      );
      fireEvent.click(screen.getByText("Watchlist ×"));
      expect(onChange).toHaveBeenCalledWith({ ...value, watchlistOnly: false });
    });
  });
});
