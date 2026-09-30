import { describe, expect, it } from "vitest";
import { seasonLabel } from "./seasons";

describe("seasonLabel", () => {
  it("renders a season year as the span it covers", () => {
    expect(seasonLabel(2026)).toBe("2026/27");
    expect(seasonLabel(2025)).toBe("2025/26");
  });

  it("pads the century rollover", () => {
    expect(seasonLabel(2099)).toBe("2099/00");
  });
});
