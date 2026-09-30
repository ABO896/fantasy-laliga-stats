import { describe, expect, it, vi, afterEach } from "vitest";
import {
  fetchStatsSeasons,
  fetchJornadaScores,
  fetchStreaks,
  fetchRecords,
  fetchLeaderboard,
} from "./stats";

function stubFetch(body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) })),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("stats client", () => {
  it("fetches the seasons list with no query params", async () => {
    stubFetch({ seasons: [2026], seasonWeekRanges: { "2026": 3 } });
    await fetchStatsSeasons();
    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toBe("http://127.0.0.1:8000/api/stats/seasons");
  });

  it("builds the scores query string from season and week", async () => {
    stubFetch({});
    await fetchJornadaScores(2026, 3);
    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toBe("http://127.0.0.1:8000/api/stats/scores?season=2026&week=3");
  });

  it("builds the streaks query string from season, end week, and window", async () => {
    stubFetch({});
    await fetchStreaks(2026, 3, 5);
    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toBe("http://127.0.0.1:8000/api/stats/streaks?season=2026&end_week=3&window=5");
  });

  it("builds the records query string from season only", async () => {
    stubFetch({});
    await fetchRecords(2026);
    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toBe("http://127.0.0.1:8000/api/stats/records?season=2026");
  });

  it("omits position and team from the leaderboard query when null", async () => {
    stubFetch({});
    await fetchLeaderboard(2026, "goals", null, null);
    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toBe("http://127.0.0.1:8000/api/stats/leaderboard?season=2026&stat=goals");
  });

  it("includes position and team in the leaderboard query when set", async () => {
    stubFetch({});
    await fetchLeaderboard(2026, "goals", "DEL", "Team A");
    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toBe(
      "http://127.0.0.1:8000/api/stats/leaderboard?season=2026&stat=goals&position=DEL&team=Team+A",
    );
  });
});
