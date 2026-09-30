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
    },
    isStale: false,
    hoursSinceLastSuccess: 5,
    marketUpdatedAt: "2026-08-22T00:15:00+02:00",
    recentRuns: [],
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
});
