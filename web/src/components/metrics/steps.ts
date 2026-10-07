import { createElement as h, type ReactNode } from "react";
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
import type { VerdictLabel } from "../../api-client/verdict";
import { VERDICT_LABELS } from "../../api-client/verdict";
import { formatEuroAbbreviated, formatPercent, formatShortDate, signedNumber } from "../../lib/format";
import { describeBasis } from "../../api-client/expected-points";
import { Formula, Frac } from "./Formula";
import type { Step } from "./StepTable";

/** What a metric's builder hands back to `MetricCard`: the step rows, the
 * always-last headline row, and an optional typeset formula to show above
 * the table. Plain `.ts` (no JSX syntax) so the two or three formulas that
 * need `Formula`/`Frac` are built with `createElement`. */
export interface Built {
  steps: Step[];
  headline: Step;
  formula?: ReactNode;
}

function num(value: number | null | undefined, digits = 2): string {
  return value === null || value === undefined ? "—" : value.toFixed(digits);
}

function pct01(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${Math.round(value * 100)}%`;
}

/** 100000 -> "€100k" — the rules' cash-per-point constant is always a round
 * number of thousands; this is only ever used for that one value. */
function thousands(value: number): string {
  return `€${Math.round(value / 1000)}k`;
}

// ---------------------------------------------------------------------------
// power

export function buildPowerSteps(block: PowerBlock): Built {
  const steps: Step[] = [
    {
      step: "Rate this season",
      value: num(block.rate),
      meaning: `points per team match, recency-weighted, ${block.rateMatches} matches`,
    },
    {
      step: "Prior",
      value: num(block.prior),
      meaning: block.priorSource === "last_season" ? "last season average" : "position average",
    },
    {
      step: "Calibrated quality",
      value: num(block.qualityPpg),
      meaning: `${block.calibration.a} × rate ${signedNumber(block.calibration.c, 3)}`,
    },
    {
      step: "× availability",
      value: num(block.availabilityFactor),
      meaning: block.availability ?? "available",
    },
    {
      step: "Power ppg",
      value: num(block.powerPpg),
      meaning: "expected points per match, adjusted for availability",
    },
  ];
  const headline: Step = {
    step: "Score",
    value: Math.round(block.score).toString(),
    meaning: `against the ${num(block.referencePpg, 1)} ppg within-position benchmark`,
  };
  const formula = h(
    Formula,
    { label: "Power formula", children: null },
    "Power = ",
    h(Frac, { num: "quality × availability", den: "referencePpg" }),
    " × 100",
  );
  return { steps, headline, formula };
}

// ---------------------------------------------------------------------------
// pointsValue

export function buildPointsValueSteps(
  block: PointsValueBlock,
  fairValue: number | null = null,
): Built {
  const opponents =
    block.matches.length > 0
      ? block.matches.map((m) => `${m.isHome ? "vs" : "at"} ${m.opponent}`).join(", ")
      : "no fixtures in the window";
  const steps: Step[] = [
    {
      step: `Expected points next ${block.horizon}`,
      value: num(block.xpts),
      meaning: opponents,
    },
    {
      step: "Replacement level",
      value: num(block.replacement),
      meaning: "median of cheap regular starters at his position",
    },
    {
      step: "Above replacement",
      value:
        block.xpts !== null && block.replacement !== null
          ? num(block.xpts - block.replacement)
          : "—",
      meaning: "expected points above a cheap regular starter",
    },
    {
      step: "× €/point",
      value: thousands(block.cashPerPoint),
      meaning: "the cash value of a point, from the rules",
    },
    {
      step: "÷ price",
      value: block.price !== null ? formatEuroAbbreviated(block.price) : "—",
      meaning: "his market price",
    },
  ];
  if (fairValue !== null) {
    steps.push({
      step: "For reference",
      value: formatEuroAbbreviated(fairValue),
      meaning: "fair value by the price curve",
    });
  }
  const computed =
    block.xpts !== null && block.replacement !== null && block.price !== null
      ? ((block.xpts - block.replacement) * block.cashPerPoint) / block.price
      : block.value;
  const headline: Step = {
    step: "Points value",
    // The raw ratio is euro-of-extra-points per euro of price — a tiny
    // fraction (~0.01-0.1) that's unreadable at 2 decimals; ×100 reads as
    // "extra point value as a % of price", which is both intuitive and
    // gives the display the same precision every other percentage metric
    // on the page uses.
    value: computed !== null ? formatPercent(computed * 100) : "—",
    meaning: "points per € of price, above a replacement-level starter",
  };
  const formula = h(
    Formula,
    { label: "Points value formula", children: null },
    h(Frac, { num: "(xP − replacement) × €100k", den: "price" }),
  );
  return { steps, headline, formula };
}

// ---------------------------------------------------------------------------
// outlook

const OUTLOOK_FEATURE_LABELS: Record<string, string> = {
  r1: "1-day price move",
  r3: "3-day price move",
  r7: "7-day price move",
  pts_vs_exp: "points vs expected",
  minutes_trend: "minutes trend",
  avail_change: "availability change",
  days_to_match: "days to next match",
  price_level: "price level within position",
};

const OUTLOOK_TOP_TERMS = 5;

export function buildOutlookSteps(block: PriceOutlookBlock): Built {
  const entries = Object.entries(block.terms).filter(
    ([, v]) => typeof v === "number",
  ) as [string, number][];
  const intercept = entries.find(([k]) => k === "intercept")?.[1] ?? null;
  const rest = entries
    .filter(([k]) => k !== "intercept")
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
  const top = rest.slice(0, OUTLOOK_TOP_TERMS);
  const other = rest.slice(OUTLOOK_TOP_TERMS);

  const steps: Step[] = top.map(([key, value]) => ({
    step: OUTLOOK_FEATURE_LABELS[key] ?? key,
    value: signedNumber(value, 2),
    meaning: "contribution to the expected % change this week",
  }));
  if (other.length > 0) {
    steps.push({
      step: "Other terms",
      value: signedNumber(other.reduce((sum, [, v]) => sum + v, 0), 2),
      meaning: `${other.length} smaller term${other.length === 1 ? "" : "s"} combined`,
    });
  }
  if (intercept !== null) {
    steps.push({
      step: "Intercept",
      value: signedNumber(intercept, 2),
      meaning: "the position's baseline expected change",
    });
  }
  const headline: Step = {
    step: "Expected change",
    value: formatPercent(block.expectedPct),
    meaning:
      `range ${formatPercent(block.lower)} to ${formatPercent(block.upper)}` +
      (block.dropRisk ? " — real risk of a larger drop" : ""),
  };
  return { steps, headline };
}

// ---------------------------------------------------------------------------
// reliability

export function buildReliabilitySteps(block: ReliabilityBlock): Built {
  const shares =
    block.startShare !== null && block.playShare !== null && block.subShare !== null
      ? `start ${pct01(block.startShare)} · play ${pct01(block.playShare)} · sub ${pct01(block.subShare)}`
      : "no club matches yet";
  const steps: Step[] = [
    {
      step: "Shares",
      value: shares,
      meaning: "recency-weighted over his club's matches this season",
    },
    {
      step: "Shrunk toward prior",
      value: pct01(block.shrunkStart),
      meaning: `blended toward the position prior at ${block.priorWeight} pseudo-matches`,
    },
    {
      step: "Blend with source",
      value: block.sourceStarter !== null ? pct01(block.sourceStarter) : "no source estimate",
      meaning: `blended in at weight ${block.sourceBlend}`,
    },
    {
      step: "× availability",
      value: num(block.availabilityFactor),
      meaning: block.availability ?? "available",
    },
  ];
  const headline: Step = {
    step: "Start probability",
    value: pct01(block.pStart),
    meaning: `play probability ${pct01(block.pPlay)} · ${block.class.toLowerCase()} class`,
  };
  return { steps, headline };
}

// ---------------------------------------------------------------------------
// xp

const XP_TERM_LABELS: Record<string, string> = {
  rate: "points rate",
  rateXStarter: "rate × starter",
  starter: "starter",
  intercept: "baseline",
  attack: "team goals",
  cleanSheet: "clean sheet",
};

export function buildXpSteps(block: XpCardBlock): Built {
  const terms = block.terms ?? {};
  const steps: Step[] = Object.entries(terms).map(([key, value]) => ({
    step: XP_TERM_LABELS[key] ?? key,
    value: signedNumber(value, 2),
    meaning: "contribution to expected points",
  }));
  if (block.rate) {
    steps.unshift({
      step: "Scoring rate",
      value: num(block.rate.value),
      meaning: `recency-weighted over ${block.rate.matches} matches, shrunk toward ${num(block.rate.prior)} (${block.rate.priorSource === "last_season" ? "last season" : "position average"})`,
    });
  }
  const headline: Step = {
    step: "Expected points",
    value: num(block.value, 1),
    meaning: describeBasis(block.basis),
  };
  return { steps, headline };
}

// ---------------------------------------------------------------------------
// form

export function buildFormSteps(block: FormBlock): Built {
  const steps: Step[] = [
    {
      step: `Last ${block.formJornadas} jornadas avg`,
      value: num(block.formAvg),
      meaning: `points [${block.recentPoints.join(", ")}]`,
    },
    {
      step: "Baseline avg",
      value: num(block.baselineAvg),
      meaning: `the ${block.baselineJornadas} jornadas before them (window ${block.baselineWindow})`,
    },
  ];
  const headline: Step = {
    step: "Form",
    value: block.value !== null ? signedNumber(block.value, 2) : "—",
    meaning: "difference from his baseline average",
  };
  return { steps, headline };
}

// ---------------------------------------------------------------------------
// consistency

export function buildConsistencySteps(block: ConsistencyBlock): Built {
  const steps: Step[] = [
    {
      step: "Mean",
      value: num(block.mean),
      meaning: `over the last ${block.jornadas} of ${block.window} jornadas, points [${block.points.join(", ")}]`,
    },
    {
      step: "SD",
      value: num(block.sd),
      meaning: "standard deviation of those points",
    },
  ];
  const headline: Step = {
    step: "Consistency",
    value: block.value !== null ? Math.round(block.value).toString() : "—",
    meaning: "higher = steadier scoring, lower = boom or bust",
  };
  const formula = h(
    Formula,
    { label: "Consistency formula", children: null },
    h(Frac, { num: "100 × mean", den: "mean + SD" }),
  );
  return { steps, headline, formula };
}

// ---------------------------------------------------------------------------
// momentum

export function buildMomentumSteps(blocks: MomentumBlock[]): Built {
  const steps: Step[] = blocks.map((m) => ({
    step: `${m.windowDays}d`,
    value: formatPercent(m.pct),
    meaning:
      m.fromDate && m.toDate
        ? `${formatShortDate(m.fromDate)} → ${formatShortDate(m.toDate)} (${m.days} actual days)`
        : "no snapshot that far back",
  }));
  const sevenDay = blocks.find((m) => m.windowDays === 7) ?? null;
  const headline: Step = {
    step: "7-day change",
    value: sevenDay ? formatPercent(sevenDay.pct) : "—",
    meaning:
      sevenDay && sevenDay.fromDate && sevenDay.toDate
        ? `${formatShortDate(sevenDay.fromDate)} → ${formatShortDate(sevenDay.toDate)}`
        : "enable the 7-day window below to see this",
  };
  return { steps, headline };
}

// ---------------------------------------------------------------------------
// verdict

const DECIDING_LABELS: Record<string, string> = {
  qualityPct: "Power percentile",
  valuePct: "Points-value percentile",
  outlookPct: "7-day outlook percentile",
  class: "Reliability class",
  medianPrice: "Position median price",
  price: "His price",
  availability: "Availability",
  confidence: "Confidence",
};

const EUR_KEYS = new Set(["medianPrice", "price"]);
const PCT_KEYS = new Set(["qualityPct", "valuePct", "outlookPct"]);

function decidingValue(key: string, value: number | string | null): string {
  if (value === null) return "—";
  if (typeof value === "number") {
    if (EUR_KEYS.has(key)) return formatEuroAbbreviated(value);
    if (PCT_KEYS.has(key)) return `${Math.round(value)}th percentile`;
    return num(value);
  }
  return value;
}

export function buildVerdictSteps(
  label: VerdictLabel,
  deciding: Record<string, number | string | null>,
  reason: string,
): Built {
  const steps: Step[] = Object.entries(deciding).map(([key, value]) => ({
    step: DECIDING_LABELS[key] ?? key,
    value: decidingValue(key, value),
    meaning: "read by the rule that decided this label",
  }));
  const idx = VERDICT_LABELS.indexOf(label);
  if (idx > 0) {
    steps.push({
      step: "Checked first",
      value: "—",
      meaning: `${VERDICT_LABELS.slice(0, idx).join(", ")} — none applied`,
    });
  }
  const headline: Step = { step: "Verdict", value: label, meaning: reason };
  return { steps, headline };
}
