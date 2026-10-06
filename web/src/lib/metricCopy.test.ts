import { describe, expect, it } from "vitest";
import { bandFor, DEFAULT_BANDS, METRIC_COPY, rankText, type MetricKey } from "./metricCopy";

const ALL_KEYS: MetricKey[] = [
  "verdict",
  "power",
  "pointsValue",
  "outlook",
  "reliability",
  "xp",
  "form",
  "consistency",
  "momentum",
];

describe("METRIC_COPY", () => {
  it("has non-empty title, meaning and why for every metric", () => {
    for (const key of ALL_KEYS) {
      const copy = METRIC_COPY[key];
      expect(copy, `missing copy for ${key}`).toBeDefined();
      expect(copy.title.length).toBeGreaterThan(0);
      expect(copy.meaning.length).toBeGreaterThan(0);
      expect(copy.why.length).toBeGreaterThan(0);
    }
  });

  it("matches the brief's verbatim copy for power", () => {
    expect(METRIC_COPY.power.title).toBe("Power");
    expect(METRIC_COPY.power.why).toBe(
      "Points win the league; Power is the best single predictor of them we have.",
    );
  });
});

describe("DEFAULT_BANDS", () => {
  it("is ascending and ends with a catch-all band", () => {
    expect(DEFAULT_BANDS[0]).toEqual({ below: 20, word: "Very low" });
    expect(DEFAULT_BANDS[1]).toEqual({ below: 40, word: "Low" });
    expect(DEFAULT_BANDS[2]).toEqual({ below: 60, word: "Average" });
    expect(DEFAULT_BANDS[3]).toEqual({ below: 80, word: "High" });
  });
});

describe("bandFor", () => {
  it("bands a high percentile as Very high", () => {
    expect(bandFor("power", 85)).toBe("Very high");
  });

  it("bands a middling percentile as Average", () => {
    expect(bandFor("power", 50)).toBe("Average");
  });

  it("bands a low percentile as Low", () => {
    expect(bandFor("power", 25)).toBe("Low");
  });

  it("handles the singleton position case regardless of percentile", () => {
    expect(bandFor("power", 50, 1)).toBe("Only one at position");
    expect(bandFor("power", null, 1)).toBe("Only one at position");
  });

  it("returns null for a null percentile when not a singleton", () => {
    expect(bandFor("power", null)).toBeNull();
    expect(bandFor("power", null, 190)).toBeNull();
  });

  it("has no percentile band for metrics with their own vocabulary", () => {
    expect(bandFor("reliability", 85)).toBeNull();
    expect(bandFor("outlook", 85)).toBeNull();
    expect(bandFor("verdict", 85)).toBeNull();
  });

  it("still bands power, unaffected by the unbanded metrics", () => {
    expect(bandFor("power", 85)).toBe("Very high");
  });
});

describe("rankText", () => {
  it("formats a rank as #N of M POS", () => {
    expect(rankText({ rank: 5, of: 190, position: "DEF" })).toBe("#5 of 190 DEF");
  });

  it("returns null for a null rank", () => {
    expect(rankText(null)).toBeNull();
  });
});
