import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import type { SquadResponse, SquadSummary } from "../api-client/squad";

const STANDARD_FORMATION_SHAPES: Record<string, Record<string, number>> = {
  "3-4-3": { POR: 1, DEF: 3, MED: 4, DEL: 3 },
  "3-5-2": { POR: 1, DEF: 3, MED: 5, DEL: 2 },
  "4-3-3": { POR: 1, DEF: 4, MED: 3, DEL: 3 },
  "4-4-2": { POR: 1, DEF: 4, MED: 4, DEL: 2 },
  "4-5-1": { POR: 1, DEF: 4, MED: 5, DEL: 1 },
  "5-3-2": { POR: 1, DEF: 5, MED: 3, DEL: 2 },
  "5-4-1": { POR: 1, DEF: 5, MED: 4, DEL: 1 },
};

vi.mock("../api-client/squad", async () => {
  const actual = await vi.importActual<typeof import("../api-client/squad")>(
    "../api-client/squad",
  );
  return { ...actual, fetchSquad: vi.fn() };
});

import { fetchSquad } from "../api-client/squad";
import SquadBar from "./SquadBar";

function buildSummary(overrides: Partial<SquadSummary> = {}): SquadSummary {
  return {
    squadSize: 12,
    maxSquadSize: 24,
    squadValue: 60_000_000,
    isLegal: true,
    canFieldXi: true,
    positionCounts: { POR: 1, DEF: 4, MED: 4, DEL: 3 },
    feasibleFormations: ["4-4-2", "4-3-3"],
    missingForXi: {},
    nearestFormation: null,
    memberPlayerIds: [1, 2],
    violations: [],
    formation: "4-4-2",
    formationShape: { POR: 1, DEF: 4, MED: 4, DEL: 2 },
    formationAvailable: true,
    allowedFormations: ["3-4-3", "3-5-2", "4-3-3", "4-4-2", "4-5-1", "5-3-2", "5-4-1"],
    formationShapes: STANDARD_FORMATION_SHAPES,
    benchEnabled: false,
    ...overrides,
  };
}

function renderBar(summary: SquadSummary) {
  const response: SquadResponse = { members: [], summary };
  vi.mocked(fetchSquad).mockResolvedValue(response);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SquadBar />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("SquadBar", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows squad occupancy", async () => {
    renderBar(buildSummary());
    expect(await screen.findByText("12 / 24")).toBeInTheDocument();
  });

  it("shows a count for every position", async () => {
    renderBar(buildSummary());
    await waitFor(() => expect(screen.getByTestId("slots-POR")).toHaveTextContent("POR 1"));
    expect(screen.getByTestId("slots-DEF")).toHaveTextContent("DEF 4");
    expect(screen.getByTestId("slots-MED")).toHaveTextContent("MED 4");
    expect(screen.getByTestId("slots-DEL")).toHaveTextContent("DEL 3");
  });

  it("names the reachable formations when an XI is possible", async () => {
    renderBar(buildSummary());
    expect(await screen.findByText(/4-4-2, 4-3-3/)).toBeInTheDocument();
  });

  it("says what is missing and what it buys, without calling it illegal", async () => {
    renderBar(
      buildSummary({
        canFieldXi: false,
        feasibleFormations: [],
        missingForXi: { DEF: 2, DEL: 1 },
        nearestFormation: "4-4-2",
        positionCounts: { POR: 1, DEF: 2, MED: 4, DEL: 1 },
      }),
    );
    expect(await screen.findByText(/No formation reachable/i)).toBeInTheDocument();
    expect(screen.getByText(/2 more DEF/)).toBeInTheDocument();
    expect(screen.getByText(/to reach 4-4-2/)).toBeInTheDocument();
    expect(screen.queryByText(/illegal/i)).not.toBeInTheDocument();
  });

  it("renders each violation message when the squad is illegal", async () => {
    renderBar(
      buildSummary({
        isLegal: false,
        violations: [
          {
            rule: "squad_size",
            actual: 25,
            limit: 24,
            message: "Squad has 25 players, 1 over the 24-player limit — remove 1.",
          },
        ],
      }),
    );
    expect(await screen.findByText(/1 over the 24-player limit/)).toBeInTheDocument();
  });

  it("shows squad value and size, and no cash or spending figures", async () => {
    vi.mocked(fetchSquad).mockResolvedValue({
      members: [],
      summary: {
        squadSize: 14,
        maxSquadSize: 24,
        squadValue: 119_133_354,
        isLegal: true,
        canFieldXi: true,
        positionCounts: { POR: 1, DEF: 5, MED: 5, DEL: 3 },
        feasibleFormations: ["4-4-2"],
        missingForXi: {},
        nearestFormation: null,
        memberPlayerIds: [],
        violations: [],
        formation: "4-4-2",
        formationShape: { POR: 1, DEF: 4, MED: 4, DEL: 2 },
        formationAvailable: true,
        allowedFormations: ["3-4-3", "3-5-2", "4-3-3", "4-4-2", "4-5-1", "5-3-2", "5-4-1"],
        formationShapes: STANDARD_FORMATION_SHAPES,
        benchEnabled: false,
      },
    });

    // useSquad's useQuery call unconditionally needs a QueryClient, so this
    // render (like every other test in this file) supplies one; the brief's
    // bare `render(<SquadBar />)` omits it, which crashes before the
    // assertions run for reasons unrelated to the ledger cut.
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <SquadBar />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText(/€119\.13M/)).toBeInTheDocument();
    // The app no longer holds a cash figure — it cannot be shown, correctly
    // or otherwise.
    expect(screen.queryByText(/Cash/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Can spend/)).not.toBeInTheDocument();
  });

  it("shows an error message when the squad query fails", async () => {
    vi.mocked(fetchSquad).mockRejectedValue(new Error("network error"));
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <SquadBar />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText(/squad unavailable/i)).toBeInTheDocument();
  });
});
