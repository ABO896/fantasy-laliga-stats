/** Formatting helpers for the player table — abbreviated euro notation,
 * signed percentages, rounded probabilities, and a uniform em-dash for
 * every nullable value (never the string "null", never an empty cell). */

function trimTrailingZeros(value: string): string {
  if (!value.includes(".")) return value;
  return value.replace(/0+$/, "").replace(/\.$/, "");
}

/** 12_500_000 -> "€12.5M"; 950_000 -> "€0.95M"; -820_000 -> "-€0.82M".
 *
 * The sign goes outside the symbol. Formatting the signed number directly
 * produces "€-0.82M", which puts the minus where no reader looks for it —
 * and a price *fall* is the half of the market worth noticing. */
export function formatEuroAbbreviated(value: number): string {
  const millions = Math.abs(value) / 1_000_000;
  const trimmed = trimTrailingZeros(millions.toFixed(2));
  const sign = value < 0 ? "-" : "";
  return `${sign}€${trimmed}M`;
}

/** 4.59 -> "+4.59%"; -25 -> "-25.00%"; null -> "—". */
export function formatPercent(value: number | null): string {
  if (value === null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

/**
 * `starterProbability` is scraped from the site's own "chance" field, which
 * is already a 0-100 percentage (e.g. `50.0`, `80.0`), not a 0-1 fraction —
 * confirmed directly against the live `/api/players` response during this
 * plan's implementation (see SUMMARY Deviations). 50 -> "50%"; null -> "—".
 */
export function formatProbability(value: number | null): string {
  if (value === null) return "—";
  return `${Math.round(value)}%`;
}

/** Renders any nullable value through `fmt`, or the em dash when null. */
export function formatNullable<T>(value: T | null, fmt: (v: T) => string): string {
  if (value === null) return "—";
  return fmt(value);
}

/** "1 day", "3 days", "0 transactions" — the count and its noun, agreeing.
 * Only exactly one takes the singular; zero is plural, as English wants. */
export function pluralize(count: number, singular: string): string {
  return `${count} ${singular}${count === 1 ? "" : "s"}`;
}

/** 4.2 -> "+4.2"; -1.8 -> "−1.8" — a real minus sign (U+2212), not the ASCII
 * hyphen, so a negative step value in a formula or step table doesn't read
 * as a dash or a typo. 0 -> "0.0", unsigned. */
export function signedNumber(value: number, decimals = 1): string {
  if (value === 0) return value.toFixed(decimals);
  const sign = value > 0 ? "+" : "−";
  return `${sign}${Math.abs(value).toFixed(decimals)}`;
}

/** "2026-08-06" -> "6 Aug" — a compact date for chart axes/captions. Always
 * read as UTC: `asOf` values are UTC-midnight ISO dates, and formatting
 * them in the viewer's local timezone can roll the displayed day backward
 * or forward depending where the browser sits. */
export function formatShortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}
