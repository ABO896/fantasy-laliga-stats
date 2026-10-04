import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import HealthPage from "./HealthPage";
import type { HealthResponse, ScrapeRunDto } from "../api-client/health";

vi.mock("../api-client/health", async () => {
  const actual = await vi.importActual<typeof import("../api-client/health")>(
    "../api-client/health",
  );
  return {
    ...actual,
    fetchHealth: vi.fn(),
    triggerScrape: vi.fn(),
  };
});

import { fetchHealth, ScrapeAlreadyRunningError, triggerScrape } from "../api-client/health";

function buildRun(overrides: Partial<ScrapeRunDto> & { id: number }): ScrapeRunDto {
  return {
    startedAt: "2026-08-06T09:00:00Z",
    finishedAt: "2026-08-06T09:01:00Z",
    status: "success",
    rowCount: 342,
    validationErrors: [],
    mode: "quick",
    ...overrides,
  };
}

function buildHealth(overrides: Partial<HealthResponse> = {}): HealthResponse {
  return {
    lastSuccessfulRun: buildRun({ id: 1 }),
    lastCompleteRun: buildRun({ id: 1, mode: "complete" }),
    isStale: false,
    hoursSinceLastSuccess: 5,
    marketUpdatedAt: "2026-08-22T00:15:00+02:00",
    recentRuns: [buildRun({ id: 1 })],
    playerPages: { players: 556, complete: 540, withGaps: 16, withMatchGaps: 3, oldestLastDay: "2026-08-20" },
    suggestComplete: false,
    ...overrides,
  };
}

function renderWithClient() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <HealthPage />
    </QueryClientProvider>,
  );
}

function mockHealth(response: HealthResponse) {
  vi.mocked(fetchHealth).mockResolvedValue(response);
}

describe("HealthPage", () => {
  it("zero_runs", async () => {
    mockHealth(buildHealth({ lastSuccessfulRun: null, hoursSinceLastSuccess: null, recentRuns: [] }));
    renderWithClient();

    expect(await screen.findByText("No scrape runs yet")).toBeInTheDocument();
    expect(screen.queryByTestId(/^status-badge-/)).not.toBeInTheDocument();
  });

  it("one_run", async () => {
    mockHealth(buildHealth({ recentRuns: [buildRun({ id: 1 })] }));
    renderWithClient();

    await screen.findByTestId("status-badge-1");
    expect(screen.getAllByTestId(/^status-badge-/)).toHaveLength(1);
  });

  it("ten_runs", async () => {
    const runs = Array.from({ length: 10 }, (_, i) => buildRun({ id: i + 1 }));
    mockHealth(buildHealth({ recentRuns: runs }));
    renderWithClient();

    await screen.findByTestId("status-badge-1");
    expect(screen.getAllByTestId(/^status-badge-/)).toHaveLength(10);
    // Most recent first — array order is preserved by the list, not re-sorted.
    const badges = screen.getAllByTestId(/^status-badge-/);
    expect(badges[0]!.getAttribute("data-testid")).toBe("status-badge-1");
    expect(badges[9]!.getAttribute("data-testid")).toBe("status-badge-10");
  });

  it("headline_shows_recency_and_row_count", async () => {
    mockHealth(
      buildHealth({
        lastSuccessfulRun: buildRun({ id: 1, rowCount: 342 }),
        hoursSinceLastSuccess: 7,
      }),
    );
    renderWithClient();

    await waitFor(() =>
      expect(screen.getByTestId("health-headline-row-count")).toHaveTextContent("342 players"),
    );
    expect(screen.getByTestId("health-headline-recency")).toHaveTextContent("7h ago");
  });

  it("rejected_run_shows_reasons", async () => {
    mockHealth(
      buildHealth({
        recentRuns: [
          buildRun({
            id: 2,
            status: "rejected",
            rowCount: 12,
            validationErrors: ["row_count 12 below minimum 300"],
          }),
        ],
      }),
    );
    renderWithClient();

    expect(await screen.findByText("Scrape rejected")).toBeInTheDocument();
    expect(screen.getAllByText(/row_count 12 below minimum 300/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Yesterday's data is unchanged/)).toBeInTheDocument();
  });

  it("long_error_list_collapses", async () => {
    const reasons = Array.from({ length: 5 }, (_, i) => `reason ${i + 1}`);
    mockHealth(
      buildHealth({
        recentRuns: [buildRun({ id: 3, status: "rejected", validationErrors: reasons })],
      }),
    );
    renderWithClient();

    await screen.findByText("Scrape rejected");
    expect(screen.getByText("reason 1")).toBeInTheDocument();
    expect(screen.getByText("reason 3")).toBeInTheDocument();
    expect(screen.queryByText("reason 4")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("Show all 5"));

    expect(screen.getByText("reason 4")).toBeInTheDocument();
    expect(screen.getByText("reason 5")).toBeInTheDocument();
  });

  it("refresh_now_always_available", async () => {
    mockHealth(buildHealth({ isStale: false }));
    renderWithClient();

    expect(await screen.findByRole("button", { name: "Refresh now" })).toBeInTheDocument();
  });

  it("refresh_in_progress", async () => {
    mockHealth(buildHealth());
    let resolveTrigger: (value: { scrapeRunId: number }) => void = () => {};
    vi.mocked(triggerScrape).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveTrigger = resolve;
        }),
    );
    renderWithClient();

    const button = await screen.findByRole("button", { name: "Refresh now" });
    fireEvent.click(button);

    const refreshingButton = await screen.findByRole("button", { name: "Refreshing…" });
    expect(refreshingButton).toBeDisabled();

    resolveTrigger!({ scrapeRunId: 99 });
    await waitFor(() => expect(screen.getByRole("button", { name: "Refresh now" })).toBeEnabled());
  });

  it("refresh_in_progress reflects a newest run already running (poll-driven)", async () => {
    mockHealth(buildHealth({ recentRuns: [buildRun({ id: 4, status: "running", finishedAt: null })] }));
    renderWithClient();

    const button = await screen.findByRole("button", { name: "Refreshing…" });
    expect(button).toBeDisabled();
  });

  it("surfaces the 409 single-flight response rather than failing silently", async () => {
    mockHealth(buildHealth());
    vi.mocked(triggerScrape).mockRejectedValue(new ScrapeAlreadyRunningError("A scrape is already running"));
    renderWithClient();

    fireEvent.click(await screen.findByRole("button", { name: "Refresh now" }));

    expect(await screen.findByText("A scrape is already in progress.")).toBeInTheDocument();
  });

  it("renders last complete refresh and player-page coverage", async () => {
    mockHealth(
      buildHealth({
        playerPages: { players: 556, complete: 540, withGaps: 16, withMatchGaps: 3, oldestLastDay: "2026-08-20" },
      }),
    );
    renderWithClient();

    expect(screen.getByText("Last complete refresh")).toBeInTheDocument();
    expect(await screen.findByText("540 of 556 players complete")).toBeInTheDocument();
    expect(screen.getByText("oldest data: 2026-08-20")).toBeInTheDocument();
    expect(screen.getByText("3 with missing matches")).toBeInTheDocument();
  });

  it("hides oldest data and missing matches when there is nothing to show", async () => {
    mockHealth(
      buildHealth({
        playerPages: { players: 0, complete: 0, withGaps: 0, withMatchGaps: 0, oldestLastDay: null },
      }),
    );
    renderWithClient();

    expect(await screen.findByText("0 of 0 players complete")).toBeInTheDocument();
    expect(screen.queryByText(/oldest data/)).not.toBeInTheDocument();
    expect(screen.queryByText(/with missing matches/)).not.toBeInTheDocument();
  });

  it("status_badge_colors", async () => {
    mockHealth(
      buildHealth({
        recentRuns: [
          buildRun({ id: 10, status: "success" }),
          buildRun({ id: 11, status: "rejected", validationErrors: ["bad data"] }),
          buildRun({ id: 12, status: "failed", validationErrors: ["ScrapeBlocked: HTTP 403"] }),
          buildRun({ id: 13, status: "running", finishedAt: null }),
        ],
      }),
    );
    renderWithClient();

    await screen.findByTestId("status-badge-10");
    const success = screen.getByTestId("status-badge-10");
    const rejected = screen.getByTestId("status-badge-11");
    const failed = screen.getByTestId("status-badge-12");
    const running = screen.getByTestId("status-badge-13");

    expect(success.className).toContain("color-accent");
    expect(rejected.className).toContain("color-destructive");
    expect(failed.className).toContain("color-destructive");
    expect(running.className).toContain("color-neutral");

    // Each status renders its own literal label, so the four are visually distinct.
    expect(within(success).getByText("success")).toBeInTheDocument();
    expect(within(rejected).getByText("rejected")).toBeInTheDocument();
    expect(within(failed).getByText("failed")).toBeInTheDocument();
    expect(within(running).getByText("running")).toBeInTheDocument();
  });
});
