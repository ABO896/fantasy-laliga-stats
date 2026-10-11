import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import StaleBanner from "./StaleBanner";
import type { HealthResponse } from "../api-client/health";

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

import { fetchHealth, triggerScrape } from "../api-client/health";

function buildHealth(overrides: Partial<HealthResponse> = {}): HealthResponse {
  return {
    lastSuccessfulRun: {
      id: 1,
      startedAt: "2026-08-05T09:00:00Z",
      finishedAt: "2026-08-05T09:01:00Z",
      status: "success",
      rowCount: 342,
      validationErrors: [],
      mode: "quick",
      currentDataset: null,
    },
    lastCompleteRun: null,
    isStale: false,
    hoursSinceLastSuccess: 5,
    marketUpdatedAt: "2026-08-22T00:15:00+02:00",
    recentRuns: [],
    playerPages: { players: 556, complete: 540, withGaps: 16, withMatchGaps: 3, oldestLastDay: null },
    suggestComplete: false,
    nextLock: null,
    ...overrides,
  };
}

function renderWithClient(children: React.ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{children}</QueryClientProvider>);
}

describe("StaleBanner", () => {
  it("renders with the substituted hour counts when stale", async () => {
    vi.mocked(fetchHealth).mockResolvedValue(
      buildHealth({ isStale: true, hoursSinceLastSuccess: 34 }),
    );
    renderWithClient(<StaleBanner />);

    expect(await screen.findByText("The market has moved since this data — refresh now?")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Last scraped 34h ago, before the market update at 22 Aug, 00:15. Prices and points on screen are from the previous cycle.",
      ),
    ).toBeInTheDocument();
  });

  it("renders nothing when fresh", async () => {
    vi.mocked(fetchHealth).mockResolvedValue(buildHealth({ isStale: false }));
    renderWithClient(
      <>
        <StaleBanner />
        <div>Player table content</div>
      </>,
    );

    await screen.findByText("Player table content");
    expect(screen.queryByText("The market has moved since this data — refresh now?")).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("dismiss hides the banner without issuing any trigger request", async () => {
    vi.mocked(fetchHealth).mockResolvedValue(buildHealth({ isStale: true }));
    renderWithClient(<StaleBanner />);

    await screen.findByText("The market has moved since this data — refresh now?");
    fireEvent.click(screen.getByRole("button", { name: "Not now" }));

    expect(screen.queryByText("The market has moved since this data — refresh now?")).not.toBeInTheDocument();
    expect(triggerScrape).not.toHaveBeenCalled();
  });

  it("issues no trigger request unless Refresh now is clicked", async () => {
    vi.mocked(fetchHealth).mockResolvedValue(buildHealth({ isStale: true }));
    renderWithClient(<StaleBanner />);

    await screen.findByText("The market has moved since this data — refresh now?");

    expect(triggerScrape).not.toHaveBeenCalled();

    vi.mocked(triggerScrape).mockResolvedValue({ scrapeRunId: 1 });
    fireEvent.click(screen.getByRole("button", { name: "Refresh now" }));

    expect(triggerScrape).toHaveBeenCalledTimes(1);
  });

  it("keeps page content rendered beneath the banner while stale", async () => {
    vi.mocked(fetchHealth).mockResolvedValue(buildHealth({ isStale: true }));
    renderWithClient(
      <>
        <StaleBanner />
        <div>Player table content</div>
      </>,
    );

    await screen.findByText("The market has moved since this data — refresh now?");
    expect(screen.getByText("Player table content")).toBeInTheDocument();
  });

  it("adds a complete-refresh recommendation when suggestComplete is true", async () => {
    vi.mocked(fetchHealth).mockResolvedValue(buildHealth({ isStale: true, suggestComplete: true }));
    renderWithClient(<StaleBanner />);

    await screen.findByText("The market has moved since this data — refresh now?");
    expect(
      screen.getByText("A complete refresh is recommended — some players' history is behind."),
    ).toBeInTheDocument();
  });

  it("omits the complete-refresh recommendation when suggestComplete is false", async () => {
    vi.mocked(fetchHealth).mockResolvedValue(buildHealth({ isStale: true, suggestComplete: false }));
    renderWithClient(<StaleBanner />);

    await screen.findByText("The market has moved since this data — refresh now?");
    expect(
      screen.queryByText("A complete refresh is recommended — some players' history is behind."),
    ).not.toBeInTheDocument();
  });

  it("stays up and disabled for the whole run, naming the step it is on", async () => {
    vi.mocked(fetchHealth).mockResolvedValue(
      buildHealth({
        isStale: true,
        recentRuns: [
          {
            id: 2,
            startedAt: "2026-10-08T10:00:00Z",
            finishedAt: null,
            status: "running",
            rowCount: 0,
            validationErrors: [],
            mode: "quick",
            currentDataset: "player_pages",
          },
        ],
      }),
    );
    renderWithClient(<StaleBanner />);

    const button = await screen.findByRole("button", { name: "Refreshing… (player pages)" });
    expect(button).toBeDisabled();
    expect(screen.getByRole("button", { name: "Complete refresh" })).toBeDisabled();
  });

  it("reminds to refresh before a jornada locks, even when the data is fresh", async () => {
    const locksAt = new Date(Date.now() + 20 * 3600_000).toISOString();
    vi.mocked(fetchHealth).mockResolvedValue(
      buildHealth({ isStale: false, nextLock: { jornada: 8, locksAt, predictionsRecorded: false } }),
    );
    renderWithClient(<StaleBanner />);
    expect(await screen.findByText(/J8 locks/)).toBeInTheDocument();
    expect(screen.getByText(/Refresh before then to record predictions/)).toBeInTheDocument();
  });

  it("stays quiet when the lock is days away or predictions are recorded", async () => {
    const far = new Date(Date.now() + 60 * 3600_000).toISOString();
    const near = new Date(Date.now() + 20 * 3600_000).toISOString();
    vi.mocked(fetchHealth).mockResolvedValue(
      buildHealth({ isStale: false, nextLock: { jornada: 8, locksAt: far, predictionsRecorded: false } }),
    );
    const { unmount } = renderWithClient(<StaleBanner />);
    await vi.waitFor(() => expect(fetchHealth).toHaveBeenCalled());
    expect(screen.queryByText(/locks/)).not.toBeInTheDocument();
    unmount();

    vi.mocked(fetchHealth).mockClear();
    vi.mocked(fetchHealth).mockResolvedValue(
      buildHealth({ isStale: false, nextLock: { jornada: 8, locksAt: near, predictionsRecorded: true } }),
    );
    renderWithClient(<StaleBanner />);
    await vi.waitFor(() => expect(fetchHealth).toHaveBeenCalled());
    expect(screen.queryByText(/locks/)).not.toBeInTheDocument();
  });

  it("a refresh started on fresh data says it is refreshing, not that the data is stale", async () => {
    vi.mocked(fetchHealth).mockResolvedValue(
      buildHealth({
        isStale: false,
        recentRuns: [
          {
            id: 3, startedAt: "2026-10-08T10:00:00Z", finishedAt: null, status: "running",
            rowCount: 0, validationErrors: [], mode: "complete", currentDataset: "player_pages",
          },
        ],
      }),
    );
    renderWithClient(<StaleBanner />);
    expect(await screen.findByText("Refreshing the data…")).toBeInTheDocument();
    expect(screen.queryByText(/The market has moved/)).not.toBeInTheDocument();
  });
});
