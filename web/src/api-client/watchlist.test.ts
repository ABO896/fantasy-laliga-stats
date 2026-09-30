import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { addToWatchlist, fetchWatchlist, removeFromWatchlist } from "./watchlist";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ playerIds: [4, 2] }),
      }),
    ),
  );
});

afterEach(() => vi.unstubAllGlobals());

describe("watchlist client", () => {
  it("reads the id list", async () => {
    await expect(fetchWatchlist()).resolves.toEqual({ playerIds: [4, 2] });
    expect(String(vi.mocked(fetch).mock.calls[0][0])).toMatch(/\/api\/watchlist$/);
  });

  it("adds with an idempotent PUT on the player's sub-resource", async () => {
    await expect(addToWatchlist(2)).resolves.toEqual({ playerIds: [4, 2] });
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toMatch(/\/api\/watchlist\/2$/);
    expect(init?.method).toBe("PUT");
  });

  it("removes with a DELETE on the player's sub-resource", async () => {
    await removeFromWatchlist(4);
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toMatch(/\/api\/watchlist\/4$/);
    expect(init?.method).toBe("DELETE");
  });

  it("throws on a failed write rather than resolving a stale list", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: () => Promise.resolve({}),
    } as Response);
    await expect(addToWatchlist(999)).rejects.toThrow();
  });
});
