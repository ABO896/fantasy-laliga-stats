import { describe, expect, it } from "vitest";
import { SEASON_RECORD_FIELDS, STAT_OPTIONS, statLabel } from "./statFields";

describe("statFields", () => {
  it("has 24 fields, matching the backend allowlist", () => {
    expect(SEASON_RECORD_FIELDS).toHaveLength(24);
  });

  it("labels a known STAT_PAIRS field from SeasonStatsTable's map", () => {
    expect(statLabel("goals")).toBe("Goals");
  });

  it("labels the three summary fields not in STAT_PAIRS", () => {
    expect(statLabel("totalPoints")).toBe("Total points");
    expect(statLabel("averagePoints")).toBe("Average points");
    expect(statLabel("matchesPlayed")).toBe("Matches played");
  });

  it("falls back to the raw field name for an unlabelled field", () => {
    expect(statLabel("somethingNew")).toBe("somethingNew");
  });

  it("sorts STAT_OPTIONS alphabetically by label", () => {
    const labels = STAT_OPTIONS.map((o) => o.label);
    expect(labels).toEqual([...labels].sort((a, b) => a.localeCompare(b)));
  });

  it("every STAT_OPTIONS field is one of SEASON_RECORD_FIELDS", () => {
    const fields = new Set(SEASON_RECORD_FIELDS);
    expect(STAT_OPTIONS.every((o) => fields.has(o.field))).toBe(true);
  });
});
