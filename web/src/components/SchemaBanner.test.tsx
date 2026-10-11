import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import SchemaBanner from "./SchemaBanner";

vi.mock("../api-client/health", async () => {
  const actual = await vi.importActual<typeof import("../api-client/health")>("../api-client/health");
  return { ...actual, fetchHealth: vi.fn() };
});

import { fetchHealth } from "../api-client/health";

function renderBanner() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <SchemaBanner />
    </QueryClientProvider>,
  );
}

function health(upToDate: boolean) {
  return {
    schema: { current: upToDate ? "0019" : "0018", head: "0019", upToDate },
  } as unknown as Awaited<ReturnType<typeof fetchHealth>>;
}

describe("SchemaBanner", () => {
  it("names the command when the database is behind the code", async () => {
    vi.mocked(fetchHealth).mockResolvedValue(health(false));
    renderBanner();
    expect(await screen.findByText(/uv run alembic upgrade head/)).toBeInTheDocument();
    expect(screen.getByText(/0018/)).toBeInTheDocument();
  });

  it("stays hidden when the schema is current", async () => {
    vi.mocked(fetchHealth).mockResolvedValue(health(true));
    renderBanner();
    await vi.waitFor(() => expect(fetchHealth).toHaveBeenCalled());
    expect(screen.queryByText(/alembic/)).not.toBeInTheDocument();
  });
});
