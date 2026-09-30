import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import type { RecordsResponse } from "../../api-client/stats";

vi.mock("../../api-client/stats", async () => {
  const actual = await vi.importActual<typeof import("../../api-client/stats")>("../../api-client/stats");
  return { ...actual, fetchRecords: vi.fn() };
});

import { fetchRecords } from "../../api-client/stats";
import RecordsTab from "./RecordsTab";

function response(overrides: Partial<RecordsResponse> = {}): RecordsResponse {
  return {
    jornadaRecords: [{ playerId: 1, name: "Player One", team: "Team A", week: 4, points: 22 }],
    seasonRecords: [{ field: "goals", playerId: 2, name: "Player Two", team: "Team B", value: 27 }],
    ...overrides,
  };
}

function renderTab() {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <RecordsTab season={2026} />
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.mocked(fetchRecords).mockReset());

describe("RecordsTab", () => {
  it("renders both the jornada records table and the season record cards", async () => {
    vi.mocked(fetchRecords).mockResolvedValue(response());
    renderTab();
    await waitFor(() => expect(screen.getByText("Player One")).toBeInTheDocument());
    expect(screen.getByText("J4")).toBeInTheDocument();
    expect(screen.getByText("Goals")).toBeInTheDocument();
    expect(screen.getByText("27")).toBeInTheDocument();
  });

  it("omits season record cards for fields with no qualifying data, rather than rendering them blank", async () => {
    vi.mocked(fetchRecords).mockResolvedValue(response({ seasonRecords: [] }));
    renderTab();
    await waitFor(() => expect(screen.getByText("Player One")).toBeInTheDocument());
    expect(screen.getByText("No season records yet.")).toBeInTheDocument();
  });

  it("shows an empty state when there are no jornada records", async () => {
    vi.mocked(fetchRecords).mockResolvedValue(response({ jornadaRecords: [] }));
    renderTab();
    await waitFor(() =>
      expect(screen.getByText("No jornada scores recorded yet.")).toBeInTheDocument(),
    );
  });
});
