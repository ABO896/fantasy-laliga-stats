import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import RefreshControls from "./RefreshControls";

vi.mock("../api-client/health", async () => {
  const actual = await vi.importActual<typeof import("../api-client/health")>(
    "../api-client/health",
  );
  return {
    ...actual,
    triggerScrape: vi.fn(),
    // No run going: the controls read the shared refresh status.
    fetchHealth: vi.fn(() => Promise.reject(new Error("offline"))),
  };
});

import { ScrapeAlreadyRunningError, triggerScrape } from "../api-client/health";

function renderControls() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <RefreshControls />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  vi.mocked(triggerScrape).mockReset();
});

describe("RefreshControls", () => {
  it("Refresh now triggers quick by default", async () => {
    vi.mocked(triggerScrape).mockResolvedValue({ scrapeRunId: 1 });
    renderControls();

    fireEvent.click(screen.getByRole("button", { name: "Refresh now" }));

    await waitFor(() => expect(triggerScrape).toHaveBeenCalledWith("quick"));
  });

  it("toggling + squad & watchlist sends mine, and the choice survives a remount", async () => {
    vi.mocked(triggerScrape).mockResolvedValue({ scrapeRunId: 1 });
    const { unmount } = renderControls();

    fireEvent.click(screen.getByRole("checkbox", { name: "+ squad & watchlist" }));
    fireEvent.click(screen.getByRole("button", { name: "Refresh now" }));

    await waitFor(() => expect(triggerScrape).toHaveBeenCalledWith("mine"));

    unmount();
    vi.mocked(triggerScrape).mockClear();
    renderControls();

    expect(screen.getByRole("checkbox", { name: "+ squad & watchlist" })).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "Refresh now" }));

    await waitFor(() => expect(triggerScrape).toHaveBeenCalledWith("mine"));
  });

  it("Complete refresh triggers complete", async () => {
    vi.mocked(triggerScrape).mockResolvedValue({ scrapeRunId: 1 });
    renderControls();

    fireEvent.click(screen.getByRole("button", { name: "Complete refresh" }));

    await waitFor(() => expect(triggerScrape).toHaveBeenCalledWith("complete"));
  });

  it("shows the already-running message on a 409", async () => {
    vi.mocked(triggerScrape).mockRejectedValue(
      new ScrapeAlreadyRunningError("A scrape is already running"),
    );
    renderControls();

    fireEvent.click(screen.getByRole("button", { name: "Refresh now" }));

    expect(await screen.findByText("A scrape is already in progress.")).toBeInTheDocument();
  });
});
