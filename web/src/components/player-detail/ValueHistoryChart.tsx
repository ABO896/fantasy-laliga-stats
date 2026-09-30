import { CartesianGrid, Line, LineChart, Tooltip, XAxis, YAxis } from "recharts";
import type { ValuePoint } from "../../api-client/player-detail";
import { formatEuroAbbreviated, formatShortDate, pluralize } from "../../lib/format";
import { useContainerWidth } from "../../lib/useContainerWidth";

interface ValueHistoryChartProps {
  points: ValuePoint[];
  /** Explicit dimensions rather than ResponsiveContainer: it measures zero
   * width under jsdom and renders nothing, which would make this component
   * untestable in a suite that tests everything else. */
  width: number;
  height: number;
  /** Overrides the caption's leading label — this chart is also reused for
   * the squad's own value history (SQUAD-04), where "Market value" would
   * misdescribe a sum across several players. Defaults to the player-page
   * wording so every existing call site is unaffected. */
  caption?: string;
  emptyMessage?: string;
}

/** A data point plus its epoch-millis form, so the X axis can be numeric
 * (spaced by real elapsed time) rather than categorical (every step drawn
 * at equal width regardless of the calendar gap between snapshots). */
interface PlottedPoint extends ValuePoint {
  t: number;
}

/** `XAxis` ticks arrive as the numeric `t` value; format them the same way
 * the caption does, via the ISO date it came from. */
function formatTick(t: number): string {
  return formatShortDate(new Date(t).toISOString());
}

const MAX_TICKS = 8;

/**
 * Recharts' default numeric-axis behaviour spaces ticks evenly across the
 * domain, not at the actual data points. Over a short span that produces
 * several ticks that round to the same calendar day under `formatShortDate`
 * (e.g. four "6 Aug" ticks for two snapshots a day apart) — several ticks
 * repeating the same label with nothing between them to distinguish.
 *
 * Deriving ticks from the real snapshot timestamps instead fixes that and is
 * more honest: every tick marks an actual observation rather than a
 * synthetic, interpolated instant. Thinned to an even spread when there are
 * many snapshots, always keeping the first and last.
 */
export function pickTicks(values: number[], maxTicks: number): number[] {
  if (values.length <= maxTicks) return values;
  const step = (values.length - 1) / (maxTicks - 1);
  const picked: number[] = [];
  const seen = new Set<number>();
  for (let i = 0; i < maxTicks; i += 1) {
    const index = Math.round(i * step);
    const value = values[index]!;
    if (!seen.has(index)) {
      seen.add(index);
      picked.push(value);
    }
  }
  return picked;
}

/**
 * DETAIL-02. The series is our own daily snapshots and nobody else recorded
 * it, so it cannot be backfilled — it started on 2026-08-06 and grows one
 * point a day, only on days the owner refreshes. Snapshots have gaps (the
 * scrape schedule was removed in an earlier phase), so the chart states its
 * real calendar span and sample count rather than a count of points
 * mislabelled "days", and spaces points by actual elapsed time rather than
 * drawing a five-day gap the same width as a one-day step.
 */
export default function ValueHistoryChart({
  points,
  width,
  height,
  caption = "Market value",
  emptyMessage = "No market value history for this player yet.",
}: ValueHistoryChartProps) {
  const [frameRef, measuredWidth] = useContainerWidth(width);
  if (points.length === 0) {
    return <p className="state-note">{emptyMessage}</p>;
  }

  if (points.length === 1) {
    return (
      <p className="state-note">
        {formatEuroAbbreviated(points[0]!.marketValue)} — one day of history so far, so there is no
        trend to plot yet.
      </p>
    );
  }

  const data: PlottedPoint[] = points.map((p) => ({ ...p, t: new Date(p.asOf).getTime() }));
  const span = `${formatShortDate(points[0]!.asOf)} – ${formatShortDate(points[points.length - 1]!.asOf)}`;
  const ticks = pickTicks(
    data.map((d) => d.t),
    MAX_TICKS,
  );

  return (
    <figure ref={frameRef} className="flex min-w-0 flex-col gap-xs">
      <figcaption className="subsection-title">
        {caption} · {span} · {pluralize(points.length, "snapshot")}
      </figcaption>
      <LineChart width={measuredWidth} height={height} data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="2 4" vertical={false} />
        <XAxis
          dataKey="t"
          type="number"
          domain={["dataMin", "dataMax"]}
          ticks={ticks}
          tickFormatter={formatTick}
          tick={{ fontSize: 11 }}
        />
        <YAxis tickFormatter={(v: number) => formatEuroAbbreviated(v)} tick={{ fontSize: 11 }} width={56} />
        <Tooltip
          labelFormatter={(_label, payload) => {
            const asOf = (payload?.[0]?.payload as PlottedPoint | undefined)?.asOf;
            return asOf ? formatShortDate(asOf) : "";
          }}
          formatter={(v) =>
            // Recharts types `v` as `ValueType | undefined` since a Tooltip's
            // formatter is generic over any series; `marketValue` is always a
            // plain number here, but we narrow rather than assert so the
            // (never-hit-in-practice) other cases still render something
            // sane instead of relying on an unsound cast.
            typeof v === "number" ? formatEuroAbbreviated(v) : String(v ?? "")
          }
        />
        <Line
          type="monotone"
          dataKey="marketValue"
          stroke="var(--color-chart-1)"
          dot={{ r: 2.5, fill: "var(--color-chart-1)", stroke: "var(--color-chart-1)" }}
          activeDot={{ r: 5, fill: "var(--color-chart-1)", stroke: "var(--color-surface)", strokeWidth: 2 }}
          strokeWidth={2}
        />
      </LineChart>
    </figure>
  );
}
