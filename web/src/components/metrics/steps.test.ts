import { describe, expect, it } from "vitest";
import type {
  ConsistencyBlock,
  FormBlock,
  MomentumBlock,
  PointsValueBlock,
  PowerBlock,
  PriceOutlookBlock,
  ReliabilityBlock,
  XpCardBlock,
} from "../../api-client/analytics";
import {
  buildConsistencySteps,
  buildFormSteps,
  buildMomentumSteps,
  buildOutlookSteps,
  buildPointsValueSteps,
  buildPowerSteps,
  buildReliabilitySteps,
  buildVerdictSteps,
  buildXpSteps,
} from "./steps";

const POWER: PowerBlock = {
  score: 62.4,
  powerPpg: 0.77,
  qualityPpg: 5.1,
  rate: 4.6,
  rateMatches: 6,
  prior: 4.2,
  priorSource: "last_season",
  calibration: { a: 1.328, c: -0.839 },
  availability: "injured",
  availabilityFactor: 0.15,
  recentJornadas: 10,
  referencePpg: 10,
};

describe("buildPowerSteps", () => {
  it("ends with a headline equal to the score", () => {
    const { steps, headline } = buildPowerSteps(POWER);
    expect(Number(headline.value)).toBeCloseTo(Math.round(POWER.score), 6);
    expect(steps.length).toBeGreaterThan(0);
    expect(steps.every((s) => typeof s.step === "string" && s.step.length > 0)).toBe(true);
  });

  it("never prints a raw formula string in its prose", () => {
    const { steps } = buildPowerSteps(POWER);
    const text = steps.map((s) => `${s.value} ${s.meaning}`).join(" ");
    expect(text).not.toMatch(/\^|e\^|\*|sqrt\(/);
  });
});

const POINTS_VALUE: PointsValueBlock = {
  value: 1.84,
  xpts: 9.2,
  replacement: 4.4,
  price: 26_000_000,
  cashPerPoint: 100_000,
  horizon: 3,
  matches: [
    { opponent: "Betis", isHome: true, xp: 3.1 },
    { opponent: "Girona", isHome: false, xp: 3.0 },
  ],
  reason: null,
  rank: { rank: 5, of: 190, percentile: 97 },
};

describe("buildPointsValueSteps", () => {
  it("headline equals (xP - replacement) * cashPerPoint / price, as a %", () => {
    const expected =
      (((POINTS_VALUE.xpts as number) - (POINTS_VALUE.replacement as number)) *
        POINTS_VALUE.cashPerPoint) /
      (POINTS_VALUE.price as number);
    const { headline } = buildPointsValueSteps(POINTS_VALUE);
    expect(parseFloat(headline.value as string)).toBeCloseTo(expected * 100, 2);
  });

  it("adds a 'for reference' fair-value row only when given one", () => {
    const withFair = buildPointsValueSteps(POINTS_VALUE, 30_000_000);
    expect(withFair.steps.some((s) => s.step === "For reference")).toBe(true);
    const withoutFair = buildPointsValueSteps(POINTS_VALUE, null);
    expect(withoutFair.steps.some((s) => s.step === "For reference")).toBe(false);
  });
});

describe("buildOutlookSteps", () => {
  it("orders terms by |value| desc, caps at 5 plus other terms, then intercept", () => {
    const block: PriceOutlookBlock = {
      expectedPct: 1.8,
      direction: "rise",
      lower: -0.5,
      upper: 4.1,
      dropRisk: false,
      basis: "ridge",
      confidence: "moderate",
      terms: {
        intercept: 0.2,
        r1: 0.1,
        r3: -0.3,
        r7: 1.5,
        pts_vs_exp: -0.9,
        minutes_trend: 0.05,
        avail_change: 0.0,
        days_to_match: -0.02,
        price_level: 0.4,
      },
      madeOn: "2026-10-01",
      rank: null,
    };
    const { steps, headline } = buildOutlookSteps(block);
    expect(steps[0].step).toBe("7-day price move");
    expect(steps.some((s) => s.step === "Other terms")).toBe(true);
    expect(steps[steps.length - 1].step).toBe("Intercept");
    expect(headline.value).toBe("+1.80%");
    expect(headline.meaning).toMatch(/-0\.50%.*4\.10%/);
  });
});

describe("buildReliabilitySteps", () => {
  it("ends with a headline carrying pStart, pPlay and the class", () => {
    const block: ReliabilityBlock = {
      class: "Regular",
      pStart: 0.62,
      pPlay: 0.78,
      startShare: 0.6,
      playShare: 0.75,
      subShare: 0.15,
      minutesShare: 0.7,
      shrunkStart: 0.58,
      sourceStarter: 0.7,
      sourceBlend: 0.3,
      availability: null,
      availabilityFactor: 1,
      minutesTrend: null,
      matches: 8,
      appearances: 7,
      halfLife: 5,
      priorWeight: 3,
      prior: { start: 0.45, play: 0.6 },
      confidence: "high",
      basis: "matches",
      rank: null,
    };
    const { headline } = buildReliabilitySteps(block);
    expect(headline.value).toBe("62%");
    expect(headline.meaning).toMatch(/78%/);
    expect(headline.meaning).toMatch(/regular/);
  });
});

describe("buildXpSteps", () => {
  it("puts the basis in the headline's meaning row", () => {
    const block: XpCardBlock = {
      value: 4.1,
      basis: "form+starter+odds",
      jornada: 7,
      opponent: "Betis",
      isHome: true,
      terms: { rate: 2.2, rateXStarter: 1.0, starter: 0.5, attack: 0.3, cleanSheet: 0.1 },
      coefficients: null,
      rate: {
        value: 4.6,
        matches: 6,
        recentPoints: [4, 5, 6],
        halfLife: 5,
        prior: 4.2,
        priorSource: "last_season",
        priorWeight: 3,
      },
    };
    const { headline, steps } = buildXpSteps(block);
    expect(headline.meaning).toMatch(/recent points \+ starter probability \+ match odds/);
    expect(steps.length).toBeGreaterThan(0);
  });
});

describe("buildFormSteps", () => {
  it("builds a headline difference from baseline", () => {
    const block: FormBlock = {
      value: 1.5, formAvg: 6, baselineAvg: 4.5, window: 5, baselineWindow: 38,
      formJornadas: 5, baselineJornadas: 30, recentPoints: [6, 6, 6, 6, 6],
    };
    const { headline } = buildFormSteps(block);
    expect(headline.value).toBe("+1.50");
  });
});

describe("buildConsistencySteps", () => {
  it("headline equals 100 * mean / (mean + SD)", () => {
    const block: ConsistencyBlock = { value: 80, mean: 5, sd: 1.25, window: 10, jornadas: 10, points: [5, 5] };
    const { headline } = buildConsistencySteps(block);
    expect(Number(headline.value)).toBeCloseTo((100 * block.mean!) / (block.mean! + block.sd!), 0);
  });
});

describe("buildMomentumSteps", () => {
  it("headlines the 7-day window specifically", () => {
    const blocks: MomentumBlock[] = [
      { windowDays: 1, fromDate: "2026-09-15", toDate: "2026-09-16", fromValue: 10, toValue: 11,
        days: 1, pct: 10, ratePerDay: 10, direction: "up" },
      { windowDays: 7, fromDate: "2026-09-09", toDate: "2026-09-16", fromValue: 10, toValue: 11.5,
        days: 7, pct: 15, ratePerDay: 2.1, direction: "up" },
      { windowDays: 30, fromDate: null, toDate: "2026-09-16", fromValue: null, toValue: 11,
        days: null, pct: null, ratePerDay: null, direction: null },
    ];
    const { headline, steps } = buildMomentumSteps(blocks);
    expect(headline.value).toBe("+15.00%");
    expect(steps).toHaveLength(3);
  });

  it("falls back gracefully when the 7-day window isn't selected", () => {
    const { headline } = buildMomentumSteps([
      { windowDays: 1, fromDate: "2026-09-15", toDate: "2026-09-16", fromValue: 10, toValue: 11,
        days: 1, pct: 10, ratePerDay: 10, direction: "up" },
    ]);
    expect(headline.value).toBe("—");
  });
});

describe("buildVerdictSteps", () => {
  it("lists the rules checked before the one that fired", () => {
    const { steps, headline } = buildVerdictSteps(
      "Elite",
      { qualityPct: 95, valuePct: 70, outlookPct: 50, class: "Nailed", medianPrice: 5_000_000, price: 30_000_000, availability: "available", confidence: "high" },
      "Top output, nailed starter.",
    );
    expect(headline.value).toBe("Elite");
    const checked = steps.find((s) => s.step === "Checked first");
    expect(checked?.meaning).toBe("Unavailable, Unproven, Sell high — none applied");
  });

  it("omits the checked-first row for the first rule in priority order", () => {
    const { steps } = buildVerdictSteps("Unavailable", { availability: "injured" }, "Injured.");
    expect(steps.some((s) => s.step === "Checked first")).toBe(false);
  });
});
