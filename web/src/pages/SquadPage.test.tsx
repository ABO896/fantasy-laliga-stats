import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SquadHistoryResponse, SquadMemberRow, SquadResponse } from "../api-client/squad";
import type { PlayersResponse } from "../api-client/players";

vi.mock("../api-client/squad", async () => {
  const actual = await vi.importActual<typeof import("../api-client/squad")>("../api-client/squad");
  return {
    ...actual,
    fetchSquad: vi.fn(),
    fetchSquadHistory: vi.fn(),
    addSquadPlayer: vi.fn(),
    removeSquadPlayer: vi.fn(),
    saveXi: vi.fn(),
  };
});

vi.mock("../api-client/players", async () => {
  const actual = await vi.importActual<typeof import("../api-client/players")>(
    "../api-client/players",
  );
  return { ...actual, fetchPlayers: vi.fn() };
});

import { fetchSquad, fetchSquadHistory, removeSquadPlayer, saveXi, SquadRuleError } from "../api-client/squad";
import { fetchPlayers } from "../api-client/players";
import SquadPage from "./SquadPage";

const EMPTY_HISTORY: SquadHistoryResponse = {
  valueHistory: [],
  pointsHistory: [],
  seasonWeekRanges: {},
};

const STANDARD_FORMATION_SHAPES: Record<string, Record<string, number>> = {
  "3-4-3": { POR: 1, DEF: 3, MED: 4, DEL: 3 },
  "3-5-2": { POR: 1, DEF: 3, MED: 5, DEL: 2 },
  "4-3-3": { POR: 1, DEF: 4, MED: 3, DEL: 3 },
  "4-4-2": { POR: 1, DEF: 4, MED: 4, DEL: 2 },
  "4-5-1": { POR: 1, DEF: 4, MED: 5, DEL: 1 },
  "5-3-2": { POR: 1, DEF: 5, MED: 3, DEL: 2 },
  "5-4-1": { POR: 1, DEF: 5, MED: 4, DEL: 1 },
};

function member(
  playerId: number,
  name: string,
  position: string,
  role: SquadMemberRow["role"] = "reserve",
  availability = "available",
): SquadMemberRow {
  return {
    playerId,
    name,
    position,
    purchasePrice: 4_000_000,
    marketValue: 5_000_000,
    effectiveValue: 5_000_000,
    role,
    availability,
  };
}

function squadOf(members: SquadMemberRow[], overrides: Partial<SquadResponse["summary"]> = {}) {
  return {
    members,
    summary: {
      squadSize: members.length,
      maxSquadSize: 24,
      squadValue: members.length * 5_000_000,
      isLegal: true,
      canFieldXi: false,
      positionCounts: { POR: 0, DEF: 0, MED: 0, DEL: 0 },
      feasibleFormations: [],
      missingForXi: {},
      nearestFormation: null,
      memberPlayerIds: members.map((m) => m.playerId),
      violations: [],
      formation: "4-4-2",
      formationShape: { POR: 1, DEF: 4, MED: 4, DEL: 2 },
      formationAvailable: true,
      allowedFormations: ["3-4-3", "3-5-2", "4-3-3", "4-4-2", "4-5-1", "5-3-2", "5-4-1"],
      formationShapes: STANDARD_FORMATION_SHAPES,
      benchEnabled: false,
      ...overrides,
    },
  } as SquadResponse;
}

const players: PlayersResponse = {
  as_of: "2026-08-22",
  players: [
    {
      playerId: 99,
      externalId: "ext-99",
      name: "Free Agent",
      team: "Team",
      position: "DEF",
      marketValue: 3_000_000,
      idealBid: null,
      maxBid: null,
      priceChangeAbs: null,
      priceChangePct: null,
      points: 10,
      pricePerPoint: null,
      starterProbability: null,
      availabilityStatus: "available",
      nextOpponent: null,
    },
  ],
};

function renderPage(squad: SquadResponse, history: SquadHistoryResponse = EMPTY_HISTORY) {
  vi.mocked(fetchSquad).mockResolvedValue(squad);
  vi.mocked(fetchPlayers).mockResolvedValue(players);
  vi.mocked(fetchSquadHistory).mockResolvedValue(history);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SquadPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("SquadPage — the pitch", () => {
  beforeEach(() => vi.resetAllMocks());

  it("draws one slot per player the formation fields", async () => {
    renderPage(squadOf([]));
    expect(await screen.findAllByRole("button", { name: /empty goalkeeper slot/i })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: /empty defender slot/i })).toHaveLength(4);
    expect(screen.getAllByRole("button", { name: /empty midfielder slot/i })).toHaveLength(4);
    expect(screen.getAllByRole("button", { name: /empty forward slot/i })).toHaveLength(2);
  });

  it("stands the starters in their slots and leaves the rest in the rail", async () => {
    renderPage(squadOf([member(1, "Courtois", "POR", "starter"), member(2, "Sorloth", "DEL")]));
    expect(await screen.findByRole("button", { name: /^courtois/i })).toBeInTheDocument();
    // queryAllByRole, not getAllByRole: the get* family throws when nothing
    // matches, so it can never assert an absence.
    expect(screen.queryAllByRole("button", { name: /empty goalkeeper slot/i })).toHaveLength(0);
    expect(screen.getByTestId("squad-rail")).toHaveTextContent("Sorloth");
  });

  it("shows no bench strip while the league has no bench", async () => {
    renderPage(squadOf([member(1, "Courtois", "POR")]));
    await screen.findByTestId("squad-rail");
    expect(screen.queryByTestId("bench-strip")).not.toBeInTheDocument();
  });

  it("shows one bench slot per position the formation fields, once the bench is on", async () => {
    renderPage(squadOf([member(1, "Aranda", "DEF", "bench")], { benchEnabled: true }));
    const bench = await screen.findByTestId("bench-strip");
    expect(bench).toHaveTextContent("Aranda");
    // 4 slot buttons (one player card plus three empty slots) — the player
    // card's own "Remove Aranda" button is excluded by the anchored regex.
    expect(within(bench).getAllByRole("button", { name: /^(aranda|empty)/i })).toHaveLength(4);
  });

  it("labels an unfinished XI incomplete, and never as a violation", async () => {
    renderPage(squadOf([member(1, "Courtois", "POR", "starter")]));
    expect(await screen.findByText(/incomplete/i)).toBeInTheDocument();
    expect(screen.queryByText(/illegal/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("badges an unavailable player without refusing anything", async () => {
    renderPage(squadOf([member(1, "Pedri", "MED", "starter", "injured")]));
    expect(await screen.findByText(/injured/i)).toBeInTheDocument();
  });

  it("says so when the stored formation is no longer one the league allows", async () => {
    renderPage(
      squadOf([], {
        formation: "4-6-0",
        formationShape: { POR: 1, DEF: 4, MED: 6, DEL: 0 },
        formationAvailable: false,
      }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(/4-6-0/);
    expect(screen.getAllByRole("button", { name: /empty midfielder slot/i })).toHaveLength(6);
  });

  it("renders without crashing when the rules file no longer knows the stored formation at all", async () => {
    // Unreachable today — `formationShape` is only null when the stored name
    // isn't in the rules file at all, which nothing in the app can currently
    // produce. Guards against a silent blank render rather than a loud
    // failure if that ever changes.
    renderPage(squadOf([], { formationShape: null }));
    expect(await screen.findByTestId("squad-rail")).toBeInTheDocument();
    expect(screen.queryByTestId("pitch")).toBeInTheDocument();
  });

  it("still adds from the rail's search", async () => {
    renderPage(squadOf([]));
    fireEvent.change(await screen.findByLabelText(/search players/i), {
      target: { value: "free" },
    });
    expect(await screen.findByRole("button", { name: /add free agent/i })).toBeInTheDocument();
  });

  it("still removes a player through the confirmation dialog", async () => {
    vi.mocked(removeSquadPlayer).mockResolvedValue(squadOf([]));
    renderPage(squadOf([member(1, "Sorloth", "DEL")]));
    fireEvent.click(await screen.findByRole("button", { name: /remove sorloth/i }));
    fireEvent.click(await screen.findByRole("button", { name: /skip/i }));
    await waitFor(() => expect(removeSquadPlayer).toHaveBeenCalledWith(1, undefined));
  });

  it("removes a starter directly from the pitch, without moving them to the rail first", async () => {
    vi.mocked(removeSquadPlayer).mockResolvedValue(squadOf([]));
    renderPage(squadOf([member(1, "Courtois", "POR", "starter")]));

    fireEvent.click(await screen.findByRole("button", { name: /remove courtois/i }));
    fireEvent.click(await screen.findByRole("button", { name: /skip/i }));

    await waitFor(() => expect(removeSquadPlayer).toHaveBeenCalledWith(1, undefined));
  });

  it("shows an error message when the squad fails to load", async () => {
    vi.mocked(fetchSquad).mockRejectedValue(new Error("network error"));
    vi.mocked(fetchPlayers).mockResolvedValue(players);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <SquadPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText(/couldn't be loaded/i)).toBeInTheDocument();
  });

  it("opens a player from the pitch", async () => {
    renderPage(squadOf([member(1, "Player One", "DEL", "starter")]));

    const link = await screen.findByRole("link", { name: /view player one/i });
    expect(link).toHaveAttribute("href", "/players/1");
  });

  it("still lifts the player when the card itself is clicked", async () => {
    renderPage(squadOf([member(1, "Player One", "DEL", "starter")]));

    const card = await screen.findByRole("button", { name: /player one, forward/i });
    fireEvent.click(card);
    expect(card).toHaveAttribute("aria-pressed", "true");
  });

  it("does not render the pitch while the squad is loading", () => {
    vi.mocked(fetchSquad).mockImplementation(() => new Promise(() => {}));
    vi.mocked(fetchPlayers).mockResolvedValue(players);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <SquadPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByText(/loading your squad/i)).toBeInTheDocument();
  });
});

describe("SquadPage — moving players", () => {
  beforeEach(() => vi.resetAllMocks());

  const starter = member(1, "Balde", "DEF", "starter");
  const reserve = member(2, "Grimaldo", "DEF");

  it("puts a lifted reserve into an empty slot and saves the whole shape", async () => {
    vi.mocked(saveXi).mockResolvedValue(squadOf([starter, { ...reserve, role: "starter" }]));
    renderPage(squadOf([starter, reserve]));

    fireEvent.click(await screen.findByRole("button", { name: /^grimaldo/i }));
    fireEvent.click(screen.getAllByRole("button", { name: /empty defender slot/i })[0]);

    await waitFor(() => expect(saveXi).toHaveBeenCalledWith("4-4-2", [1, 2], []));
  });

  it("swaps two players when the destination slot is occupied", async () => {
    vi.mocked(saveXi).mockResolvedValue(squadOf([]));
    renderPage(squadOf([starter, reserve]));

    fireEvent.click(await screen.findByRole("button", { name: /^grimaldo/i }));
    fireEvent.click(screen.getByRole("button", { name: /^balde/i }));

    await waitFor(() => expect(saveXi).toHaveBeenCalledWith("4-4-2", [2], []));
  });

  it("puts a lifted player down again without saving", async () => {
    renderPage(squadOf([starter, reserve]));
    const card = await screen.findByRole("button", { name: /^grimaldo/i });

    fireEvent.click(card);
    expect(card).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(card);
    expect(card).toHaveAttribute("aria-pressed", "false");
    expect(saveXi).not.toHaveBeenCalled();
  });

  it("sends a starter back to the rail", async () => {
    vi.mocked(saveXi).mockResolvedValue(squadOf([]));
    renderPage(squadOf([starter, reserve]));

    fireEvent.click(await screen.findByRole("button", { name: /^balde/i }));
    fireEvent.click(screen.getByRole("button", { name: /send to the rest of the squad/i }));

    await waitFor(() => expect(saveXi).toHaveBeenCalledWith("4-4-2", [], []));
  });

  it("seats a player on the bench when the league has one", async () => {
    vi.mocked(saveXi).mockResolvedValue(squadOf([]));
    renderPage(squadOf([reserve], { benchEnabled: true }));

    fireEvent.click(await screen.findByRole("button", { name: /^grimaldo/i }));
    const strip = screen.getByTestId("bench-strip");
    fireEvent.click(within(strip).getByRole("button", { name: /empty defender slot/i }));

    await waitFor(() => expect(saveXi).toHaveBeenCalledWith("4-4-2", [], [2]));
  });

  it("moves the pitch before the server answers, and back again when it refuses", async () => {
    // `SquadRuleError` comes from the mocked module's `...actual` spread — the
    // same class object the component's `instanceof` check sees. Re-importing
    // it through `vi.importActual` here would risk a second module instance
    // and a silently-failing `instanceof`, which would show up as the generic
    // fallback message instead of the server's sentence.
    //
    // `saveXi` is hung on a controlled promise so the optimistic move can be
    // observed *before* the server answers — without this, asserting only the
    // end state cannot tell "the move happened, then rolled back" apart from
    // "the move never happened at all", which is exactly the bug this test
    // once let through (see releaseRef pattern below, used again here).
    const releaseRef: { current: ((reason: unknown) => void) | null } = { current: null };
    vi.mocked(saveXi).mockImplementation(
      () =>
        new Promise<SquadResponse>((_resolve, reject) => {
          releaseRef.current = reject;
        }),
    );
    renderPage(squadOf([starter, reserve]));

    // The refetch `onSettled` fires must never land, or it would restore the
    // pre-move squad on its own and this test would pass with the rollback
    // deleted. Hanging it leaves `onError`'s rollback as the only thing that
    // can put the third empty slot back.
    vi.mocked(fetchSquad).mockImplementation(() => new Promise(() => {}));

    fireEvent.click(await screen.findByRole("button", { name: /^grimaldo/i }));
    fireEvent.click(screen.getAllByRole("button", { name: /empty defender slot/i })[0]);

    // Forward half: while the save is still pending, the optimistic move has
    // already landed — two empty defender slots, not three.
    await waitFor(() =>
      expect(screen.getAllByRole("button", { name: /empty defender slot/i })).toHaveLength(2),
    );

    releaseRef.current?.(
      new SquadRuleError({
        rule: "formation_shape",
        actual: 5,
        limit: 4,
        message: "4-4-2 fields 4 defender(s) and you've placed 5.",
      }),
    );

    // The server's own sentence, rendered verbatim.
    expect(
      await screen.findByText(/4-4-2 fields 4 defender\(s\) and you've placed 5\./),
    ).toBeInTheDocument();
    // And the arrangement is the last one the server accepted: three empty
    // defender slots again, not two.
    await waitFor(() =>
      expect(screen.getAllByRole("button", { name: /empty defender slot/i })).toHaveLength(3),
    );
  });

  it("changing formation demotes whoever no longer fits, in one save", async () => {
    vi.mocked(saveXi).mockResolvedValue(squadOf([]));
    const backFive = [
      member(1, "A", "DEF", "starter"),
      member(2, "B", "DEF", "starter"),
      member(3, "C", "DEF", "starter"),
      member(4, "D", "DEF", "starter"),
      member(5, "E", "DEF", "starter"),
    ];
    renderPage(squadOf(backFive));

    fireEvent.change(await screen.findByLabelText(/formation/i), { target: { value: "3-4-3" } });

    await waitFor(() => expect(saveXi).toHaveBeenCalledTimes(1));
    expect(saveXi).toHaveBeenCalledWith("3-4-3", [1, 2, 3], []);
  });

  it("refuses to move anything while the stored formation is unavailable", async () => {
    renderPage(
      squadOf([reserve], {
        formation: "4-6-0",
        formationShape: { POR: 1, DEF: 4, MED: 6, DEL: 0 },
        formationAvailable: false,
      }),
    );

    fireEvent.click(await screen.findByRole("button", { name: /^grimaldo/i }));
    fireEvent.click(screen.getAllByRole("button", { name: /empty defender slot/i })[0]);

    expect(saveXi).not.toHaveBeenCalled();
  });

  it("drops a bench role stranded by the league switching its bench off", async () => {
    // Without reconciliation the stale bench member rides along in every
    // save and the server refuses the lot with `bench_disabled`.
    const stranded = member(3, "Aranda", "DEF", "bench");
    vi.mocked(saveXi).mockResolvedValue(squadOf([]));
    renderPage(squadOf([starter, reserve, stranded], { benchEnabled: false }));

    fireEvent.click(await screen.findByRole("button", { name: /^grimaldo/i }));
    fireEvent.click(screen.getAllByRole("button", { name: /empty defender slot/i })[0]);

    await waitFor(() => expect(saveXi).toHaveBeenCalledWith("4-4-2", [1, 2], []));
  });

  it("does not start a second save while one is still in flight", async () => {
    const releaseRef: { current: ((value: SquadResponse) => void) | null } = { current: null };
    vi.mocked(saveXi).mockImplementation(
      () =>
        new Promise<SquadResponse>((resolve) => {
          releaseRef.current = resolve;
        }),
    );
    renderPage(squadOf([starter, reserve]));

    fireEvent.click(await screen.findByRole("button", { name: /^grimaldo/i }));
    fireEvent.click(screen.getAllByRole("button", { name: /empty defender slot/i })[0]);
    await waitFor(() => expect(saveXi).toHaveBeenCalledTimes(1));

    // A second gesture while the first is unresolved must not reach the server.
    fireEvent.click(screen.getByRole("button", { name: /^balde/i }));
    fireEvent.click(screen.getAllByRole("button", { name: /empty defender slot/i })[0]);

    // A guard that blocks the second `mutate()` call does so synchronously,
    // before `onMutate`'s `await cancelQueries(...)` — but a guard that is
    // missing only fires `saveXi` after that microtask resolves. Asserting
    // immediately would pass either way; flushing first is what makes "still
    // 1" mean the second gesture was actually refused, not just not-yet-sent.
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(saveXi).toHaveBeenCalledTimes(1);

    releaseRef.current?.(squadOf([starter, reserve]));
  });
});

describe("SquadPage — squad history (SQUAD-04)", () => {
  beforeEach(() => vi.resetAllMocks());

  it("plots the squad's value and points history with squad-specific captions", async () => {
    renderPage(squadOf([]), {
      valueHistory: [
        { asOf: "2026-08-06", squadValue: 10_000_000 },
        { asOf: "2026-08-07", squadValue: 10_500_000 },
      ],
      pointsHistory: [{ seasonYear: 2026, week: 1, points: 12, isProvisional: false }],
      seasonWeekRanges: { 2026: 1 },
    });

    const section = await screen.findByTestId("squad-history");
    // Squad-flavored captions, not the player-page originals — this is what
    // signals "current squad, not the roster as it actually changed" for the
    // points chart without a separate disclaimer paragraph.
    expect(within(section).getByText(/^Squad value/i)).toBeInTheDocument();
    expect(
      within(section).getByText(/^Squad points per jornada · current squad/i),
    ).toBeInTheDocument();
    expect(within(section).queryByText(/^Market value/i)).not.toBeInTheDocument();
    expect(within(section).queryByText(/^Points per jornada$/i)).not.toBeInTheDocument();
  });

  it("shows the squad-flavored empty states rather than the player page's when there is no history yet", async () => {
    renderPage(squadOf([]), EMPTY_HISTORY);

    const section = await screen.findByTestId("squad-history");
    expect(within(section).getByText(/no squad value history yet/i)).toBeInTheDocument();
    expect(
      within(section).getByText(/no jornada scores recorded for the squad yet/i),
    ).toBeInTheDocument();
  });
});
