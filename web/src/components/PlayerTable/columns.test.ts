import { describe, expect, it } from "vitest";
import { maxPriceFilter } from "./columns";

/** `maxPriceFilter` only ever calls `row.getValue(columnId)` — this fake
 * supplies just that, cast to the TanStack `Row` type the real column defs
 * pass in, the same minimal-fake approach `sorting.test.ts` uses for its
 * own row-shaped fixtures. */
function fakeRow(value: number | null) {
  return { getValue: () => value } as unknown as Parameters<typeof maxPriceFilter>[0];
}

describe("maxPriceFilter", () => {
  it("keeps every row when no filter value is active", () => {
    expect(maxPriceFilter(fakeRow(50_000_000), "marketValue", undefined)).toBe(true);
    expect(maxPriceFilter(fakeRow(null), "marketValue", undefined)).toBe(true);
  });

  it("keeps a row whose price is at or below the ceiling", () => {
    expect(maxPriceFilter(fakeRow(40_000_000), "marketValue", 40_000_000)).toBe(true);
    expect(maxPriceFilter(fakeRow(30_000_000), "marketValue", 40_000_000)).toBe(true);
  });

  it("excludes a row whose price is above the ceiling", () => {
    expect(maxPriceFilter(fakeRow(45_000_000), "marketValue", 40_000_000)).toBe(false);
  });

  it("excludes a row with an unknown (null) price once a ceiling is active", () => {
    // A scrape that yields a null price must not silently slip past a
    // budget ceiling — an unknown price is never provably "within budget".
    expect(maxPriceFilter(fakeRow(null), "idealBid", 40_000_000)).toBe(false);
  });
});
