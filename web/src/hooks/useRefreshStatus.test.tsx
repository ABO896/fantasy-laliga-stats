import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import type { HealthResponse, ScrapeRunDto } from "../api-client/health";
import { useRefreshStatus } from "./useRefreshStatus";

vi.mock("../api-client/health", async () => {
  const actual = await vi.importActual<typeof import("../api-client/health")>("../api-client/health");
  return { ...actual, fetchHealth: vi.fn() };
});

import { fetchHealth } from "../api-client/health";

function run(status: ScrapeRunDto["status"], currentDataset: string | null = null): ScrapeRunDto {
  return {
    id: 9,
    startedAt: "2026-10-08T10:00:00Z",
    finishedAt: status === "running" ? null : "2026-10-08T10:05:00Z",
    status,
    rowCount: 0,
    validationErrors: [],
    mode: "quick",
    currentDataset,
  };
}

function health(newest: ScrapeRunDto): HealthResponse {
  return {
    lastSuccessfulRun: null,
    lastCompleteRun: null,
    isStale: true,
    hoursSinceLastSuccess: null,
    marketUpdatedAt: "2026-10-08T00:15:00+02:00",
    recentRuns: [newest],
    playerPages: { players: 0, complete: 0, withGaps: 0, withMatchGaps: 0, oldestLastDay: null },
    suggestComplete: false,
  };
}

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper };
}

describe("useRefreshStatus", () => {
  it("reports a running refresh and the dataset it is on", async () => {
    vi.mocked(fetchHealth).mockResolvedValue(health(run("running", "player_pages")));
    const { wrapper } = setup();
    const { result } = renderHook(() => useRefreshStatus(), { wrapper });

    await waitFor(() => expect(result.current.running).toBe(true));
    expect(result.current.currentDataset).toBe("player_pages");
  });

  it("reloads every query once when the run finishes", async () => {
    vi.mocked(fetchHealth).mockResolvedValue(health(run("running", "market")));
    const { client, wrapper } = setup();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useRefreshStatus(), { wrapper });
    await waitFor(() => expect(result.current.running).toBe(true));

    vi.mocked(fetchHealth).mockResolvedValue(health(run("success")));
    await client.refetchQueries({ queryKey: ["health"] });

    await waitFor(() => expect(result.current.running).toBe(false));
    expect(invalidate).toHaveBeenCalledTimes(1);
    expect(invalidate).toHaveBeenCalledWith();
  });

  it("does not reload anything when no run was going", async () => {
    vi.mocked(fetchHealth).mockResolvedValue(health(run("success")));
    const { client, wrapper } = setup();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useRefreshStatus(), { wrapper });

    await waitFor(() => expect(result.current.loaded).toBe(true));
    expect(result.current.running).toBe(false);
    expect(invalidate).not.toHaveBeenCalled();
  });
});
