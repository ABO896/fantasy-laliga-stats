import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../api-client/transfers", async () => {
  const actual = await vi.importActual<typeof import("../../api-client/transfers")>(
    "../../api-client/transfers",
  );
  return { ...actual, fetchPlayerBid: vi.fn() };
});

import { fetchPlayerBid } from "../../api-client/transfers";
import OurBidCard from "./OurBidCard";

function renderCard() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <OurBidCard playerId={7} />
    </QueryClientProvider>,
  );
}

describe("OurBidCard (MODEL-05 on the player page)", () => {
  it("shows our ideal and max bid beside the source's, with any staleness reason", async () => {
    vi.mocked(fetchPlayerBid).mockResolvedValue({
      asOf: "2026-09-27", playerId: 7, name: "X", team: "T", position: "MED",
      marketValue: 10_000_000, availability: "available", ourIdeal: 10_200_000,
      ourMax: 10_900_000, sourceIdeal: 10_100_000, sourceMax: 10_300_000, inputs: {},
      freshness: { confidence: 0.64, label: "medium", datasets: [],
                   reasons: ["Prices are 2 market updates behind — refresh before acting."] },
    });
    renderCard();
    expect(await screen.findByText("€10.2M")).toBeInTheDocument();
    expect(screen.getByText("€10.9M")).toBeInTheDocument();
    expect(screen.getByText(/source €10.1M \/ €10.3M/)).toBeInTheDocument();
    expect(screen.getByText(/2 market updates behind/)).toBeInTheDocument();
  });

  it("renders nothing when there is no current snapshot", async () => {
    vi.mocked(fetchPlayerBid).mockRejectedValue(new Error("404"));
    const { container } = renderCard();
    await vi.waitFor(() => expect(fetchPlayerBid).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
