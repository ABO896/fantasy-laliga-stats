import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { PlayerVerdict } from "../../api-client/verdict";

vi.mock("../../api-client/verdict", async () => {
  const actual = await vi.importActual<typeof import("../../api-client/verdict")>(
    "../../api-client/verdict",
  );
  return { ...actual, fetchPlayerVerdict: vi.fn() };
});

import { fetchPlayerVerdict } from "../../api-client/verdict";
import VerdictBanner from "./VerdictBanner";

function renderBanner(url = "/players/7") {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[url]}>
        <VerdictBanner playerId={7} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const BASE: PlayerVerdict = {
  playerId: 7,
  label: "Bargain",
  tags: ["good value", "minutes up"],
  reason: "Top-quarter value for money with reliable minutes.",
  confidence: "high",
  deciding: {},
  disabledLabels: [],
  personal: null,
  validation: null,
};

describe("VerdictBanner", () => {
  it("shows the chip, tags, reason sentence and confidence", async () => {
    vi.mocked(fetchPlayerVerdict).mockResolvedValue(BASE);
    renderBanner();
    expect(await screen.findByText("Bargain")).toBeInTheDocument();
    expect(screen.getByText("good value")).toBeInTheDocument();
    expect(screen.getByText("minutes up")).toBeInTheDocument();
    expect(screen.getByText(BASE.reason)).toBeInTheDocument();
    expect(screen.getByText(/high confidence/)).toBeInTheDocument();
  });

  it("shows the personal line with an icon for its kind", async () => {
    vi.mocked(fetchPlayerVerdict).mockResolvedValue({
      ...BASE,
      personal: {
        kind: "upgrade",
        text: "Upgrade available: X (+1.2 pts over 3 jornadas, costs €1.0M more)",
        gain: 1.2,
        cost: 1_000_000,
        otherPlayerId: 2,
        otherName: "X",
        overCeilingBy: null,
      },
    });
    renderBanner();
    expect(await screen.findByText(/Upgrade available/)).toBeInTheDocument();
  });

  it("shows the hasn't-beaten-chance note when the label's track record hasn't", async () => {
    vi.mocked(fetchPlayerVerdict).mockResolvedValue({
      ...BASE,
      validation: { label: "Bargain", beatsChance: false, hitRate: 0.5, n: 10 },
    });
    renderBanner();
    expect(
      await screen.findByText(/hasn't yet beaten chance on our history/),
    ).toBeInTheDocument();
  });

  it("says nothing extra when the label has beaten chance", async () => {
    vi.mocked(fetchPlayerVerdict).mockResolvedValue({
      ...BASE,
      validation: { label: "Bargain", beatsChance: true, hitRate: 0.7, n: 40 },
    });
    renderBanner();
    await screen.findByText("Bargain");
    expect(screen.queryByText(/hasn't yet beaten chance/)).not.toBeInTheDocument();
  });

  it("says the label is not yet validated when no report covers it", async () => {
    vi.mocked(fetchPlayerVerdict).mockResolvedValue({ ...BASE, validation: null });
    renderBanner();
    expect(
      await screen.findByText("Not yet validated on our history — treat it as a hint."),
    ).toBeInTheDocument();
  });

  it("says the label is not yet validated when it has no scored observations", async () => {
    vi.mocked(fetchPlayerVerdict).mockResolvedValue({
      ...BASE,
      validation: { label: "Bargain", beatsChance: false, hitRate: null, n: 0 },
    });
    renderBanner();
    expect(await screen.findByText(/Not yet validated on our history/)).toBeInTheDocument();
    expect(screen.queryByText(/hasn't yet beaten chance/)).not.toBeInTheDocument();
  });

  it("adds no validation note to a label that makes no forward claim", async () => {
    vi.mocked(fetchPlayerVerdict).mockResolvedValue({
      ...BASE,
      label: "Unavailable",
      validation: { label: "Unavailable", beatsChance: false, hitRate: null, n: 40 },
    });
    renderBanner();
    await screen.findByText(BASE.reason);
    expect(screen.queryByText(/validated|beaten chance/)).not.toBeInTheDocument();
  });

  it("passes the ceiling from the URL's ?max= through to the fetch", async () => {
    vi.mocked(fetchPlayerVerdict).mockResolvedValue(BASE);
    renderBanner("/players/7?max=5000000");
    await screen.findByText("Bargain");
    expect(fetchPlayerVerdict).toHaveBeenCalledWith(7, 5_000_000);
  });

  it("renders nothing when the request fails", async () => {
    vi.mocked(fetchPlayerVerdict).mockRejectedValue(new Error("404"));
    const { container } = renderBanner();
    await vi.waitFor(() => expect(fetchPlayerVerdict).toHaveBeenCalled());
    await vi.waitFor(() => expect(container).toBeEmptyDOMElement());
  });
});
