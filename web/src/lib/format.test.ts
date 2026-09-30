import { describe, expect, it } from "vitest";
import {
  formatEuroAbbreviated,
  formatNullable,
  formatPercent,
  formatProbability,
  pluralize,
} from "./format";

describe("formatEuroAbbreviated", () => {
  it("abbreviates millions with trimmed decimals", () => {
    expect(formatEuroAbbreviated(12_500_000)).toBe("€12.5M");
    expect(formatEuroAbbreviated(950_000)).toBe("€0.95M");
  });

  // A price fall is the interesting half of the market. It read "€-0.82M",
  // putting the minus between the symbol and the number, where no reader
  // expects it.
  it("puts the minus sign before the currency symbol", () => {
    expect(formatEuroAbbreviated(-820_000)).toBe("-€0.82M");
    expect(formatEuroAbbreviated(-1_380_000)).toBe("-€1.38M");
  });

  it("leaves zero unsigned", () => {
    expect(formatEuroAbbreviated(0)).toBe("€0M");
  });
});

describe("formatPercent", () => {
  it("signs positive values and always shows two decimals", () => {
    expect(formatPercent(4.59)).toBe("+4.59%");
    expect(formatPercent(-25)).toBe("-25.00%");
  });

  it("renders null as an em dash, never the string null or an empty string", () => {
    const result = formatPercent(null);
    expect(result).toBe("—");
    expect(result).not.toBe("null");
    expect(result).not.toBe("");
  });
});

describe("formatProbability", () => {
  it("rounds the already-0-100-scale starter probability to a whole percent", () => {
    // starterProbability is scraped as a 0-100 value (e.g. 50.0, 80.0), not
    // a 0-1 fraction — confirmed against the live /api/players response.
    expect(formatProbability(82)).toBe("82%");
    expect(formatProbability(50)).toBe("50%");
  });

  it("renders null as an em dash, never the string null or an empty string", () => {
    const result = formatProbability(null);
    expect(result).toBe("—");
    expect(result).not.toBe("null");
    expect(result).not.toBe("");
  });
});

describe("formatNullable", () => {
  it("formats a present value through the given formatter", () => {
    expect(formatNullable(42, (v) => `#${v}`)).toBe("#42");
  });

  it("renders null as an em dash, never the string null or an empty string", () => {
    const result = formatNullable<number>(null, (v) => `#${v}`);
    expect(result).toBe("—");
    expect(result).not.toBe("null");
    expect(result).not.toBe("");
  });
});

describe("pluralize", () => {
  it("uses the singular form for exactly one", () => {
    expect(pluralize(1, "day")).toBe("1 day");
    expect(pluralize(1, "transaction")).toBe("1 transaction");
  });

  it("uses the plural form for none and for many", () => {
    expect(pluralize(0, "transaction")).toBe("0 transactions");
    expect(pluralize(3, "day")).toBe("3 days");
  });
});
