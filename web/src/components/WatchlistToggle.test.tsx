import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api-client/watchlist", () => ({
  fetchWatchlist: vi.fn(),
  addToWatchlist: vi.fn(),
  removeFromWatchlist: vi.fn(),
}));

import { addToWatchlist, fetchWatchlist, removeFromWatchlist } from "../api-client/watchlist";
import WatchlistToggle, { StarButton } from "./WatchlistToggle";

function renderToggle() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <WatchlistToggle playerId={7} playerName="Pedri" />
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe("StarButton", () => {
  it("names the action it will take, and reports its state via aria-pressed", () => {
    const { rerender } = render(<StarButton watched={false} playerName="Pedri" onClick={() => {}} />);
    const off = screen.getByRole("button", { name: "Add Pedri to watchlist" });
    expect(off).toHaveAttribute("aria-pressed", "false");

    rerender(<StarButton watched playerName="Pedri" onClick={() => {}} />);
    const on = screen.getByRole("button", { name: "Remove Pedri from watchlist" });
    expect(on).toHaveAttribute("aria-pressed", "true");
  });
});

describe("WatchlistToggle", () => {
  it("adds an unwatched player and reflects the server's new list", async () => {
    vi.mocked(fetchWatchlist).mockResolvedValue({ playerIds: [] });
    vi.mocked(addToWatchlist).mockResolvedValue({ playerIds: [7] });

    renderToggle();
    await userEvent.click(await screen.findByRole("button", { name: "Add Pedri to watchlist" }));

    expect(addToWatchlist).toHaveBeenCalledWith(7);
    await screen.findByRole("button", { name: "Remove Pedri from watchlist" });
  });

  it("removes a watched player", async () => {
    vi.mocked(fetchWatchlist).mockResolvedValue({ playerIds: [7] });
    vi.mocked(removeFromWatchlist).mockResolvedValue({ playerIds: [] });

    renderToggle();
    await userEvent.click(
      await screen.findByRole("button", { name: "Remove Pedri from watchlist" }),
    );

    expect(removeFromWatchlist).toHaveBeenCalledWith(7);
    await screen.findByRole("button", { name: "Add Pedri to watchlist" });
  });

  it("renders nothing while the watchlist is unavailable, rather than a guess", async () => {
    vi.mocked(fetchWatchlist).mockRejectedValue(new Error("down"));
    renderToggle();
    await waitFor(() => expect(fetchWatchlist).toHaveBeenCalled());
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
