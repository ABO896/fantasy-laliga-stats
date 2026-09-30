import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import type { StreaksResponse } from "../../api-client/stats";

vi.mock("../../api-client/stats", async () => {
  const actual = await vi.importActual<typeof import("../../api-client/stats")>("../../api-client/stats");
  return { ...actual, fetchStreaks: vi.fn() };
});

import { fetchStreaks } from "../../api-client/stats";
import StreaksTab from "./StreaksTab";

function response(overrides: Partial<StreaksResponse> = {}): StreaksResponse {
  return {
    endWeek: 5,
    window: 5,
    players: [
      { playerId: 1, name: "Player One", team: "Team A", position: "DEL", totalPoints: 20, weeksCounted: 5 },
    ],
    ...overrides,
  };
}

function renderTab() {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/stats"]}>
        <StreaksTab season={2026} maxWeek={5} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.mocked(fetchStreaks).mockReset());

describe("StreaksTab", () => {
  it("renders the ranked table once data loads", async () => {
    vi.mocked(fetchStreaks).mockResolvedValue(response());
    renderTab();
    await waitFor(() => expect(screen.getByText("Player One")).toBeInTheDocument());
    expect(screen.getByText("20")).toBeInTheDocument();
  });

  it("shows a weeks-counted note only when the window was shortened", async () => {
    vi.mocked(fetchStreaks).mockResolvedValue(
      response({ window: 5, players: [{ playerId: 1, name: "P", team: "T", position: "DEL", totalPoints: 6, weeksCounted: 2 }] }),
    );
    renderTab();
    await waitFor(() => expect(screen.getByText("(2/5)")).toBeInTheDocument());
  });

  it("omits the note when the window is full", async () => {
    vi.mocked(fetchStreaks).mockResolvedValue(response());
    renderTab();
    await waitFor(() => expect(screen.getByText("Player One")).toBeInTheDocument());
    expect(screen.queryByText(/\(\d\/\d\)/)).not.toBeInTheDocument();
  });

  it("defaults the window select to 5", async () => {
    vi.mocked(fetchStreaks).mockResolvedValue(response());
    renderTab();
    await waitFor(() => expect(fetchStreaks).toHaveBeenCalledWith(2026, 5, 5));
  });
});
