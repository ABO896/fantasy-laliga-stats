import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { fetchLeagueSettings, saveLeagueSettings } from "./league-settings";

const settings = {
  premiumFormationsEnabled: false,
  premiumBenchEnabled: false,
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(settings) }),
    ),
  );
});

afterEach(() => vi.unstubAllGlobals());

describe("league settings client", () => {
  it("reads both flags", async () => {
    await expect(fetchLeagueSettings()).resolves.toEqual(settings);
  });

  it("sends both flags on save, never a partial set", async () => {
    await saveLeagueSettings(settings);
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(JSON.parse(String(init?.body))).toEqual(settings);
  });
});
