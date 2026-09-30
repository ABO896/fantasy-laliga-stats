import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import SettingsPage from "./SettingsPage";

vi.mock("../api-client/league-settings", () => ({
  fetchLeagueSettings: vi.fn(),
  saveLeagueSettings: vi.fn(),
}));

import { fetchLeagueSettings, saveLeagueSettings } from "../api-client/league-settings";

const off = {
  premiumFormationsEnabled: false,
  premiumBenchEnabled: false,
};

beforeEach(() => {
  vi.mocked(fetchLeagueSettings).mockResolvedValue({ ...off });
  vi.mocked(saveLeagueSettings).mockImplementation((s) => Promise.resolve(s));
});

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <SettingsPage />
    </QueryClientProvider>,
  );
}

describe("SettingsPage", () => {
  it("offers both premium toggles", async () => {
    renderPage();
    expect(await screen.findByLabelText(/bench/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/formations/i)).toBeInTheDocument();
  });

  it("sends both flags when one is switched on", async () => {
    renderPage();
    await userEvent.click(await screen.findByLabelText(/bench/i));

    await waitFor(() =>
      expect(saveLeagueSettings).toHaveBeenCalledWith({
        premiumFormationsEnabled: false,
        premiumBenchEnabled: true,
      }),
    );
  });

  it("says these are the league admin's settings, not a purchase", async () => {
    renderPage();
    expect(
      await screen.findByText(
        /switched on per league by its admin, and the app has no way to detect them/i,
      ),
    ).toBeInTheDocument();
  });

  it("says turning a feature off narrows what you can field, not what you have set", async () => {
    renderPage();
    expect(
      await screen.findByText(/it never rearranges the team you have already set/i),
    ).toBeInTheDocument();
  });
});
