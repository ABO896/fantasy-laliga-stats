import { Bar, BarChart, Cell, CartesianGrid, ReferenceLine, Tooltip, XAxis, YAxis } from "recharts";
import type { GameweekPointsRow } from "../../api-client/player-detail";
import { seasonLabel } from "../../lib/seasons";
import { useContainerWidth } from "../../lib/useContainerWidth";

export interface JornadaSlot {
  seasonYear: number;
  week: number;
  label: string;
  /** `null` means no score is recorded for this week — which is not the same
   * claim as zero, and must not look like it. */
  points: number | null;
  recorded: boolean;
  isProvisional: boolean;
}

/**
 * One slot per league week per season, oldest first.
 *
 * The axis comes from `seasonWeekRanges` (the highest stored week per season
 * across all players) rather than from this player's own rows, because a
 * player's record cannot reveal a week they did not play: a mid-season
 * signing and an un-backfilled week look identical from inside it. Both are
 * genuinely unknown to us, and both render as gaps.
 *
 * Dropping absent weeks instead would stand week 29 next to week 31 and
 * silently assert a continuity that is not there — 2025/26 is missing weeks
 * 30 and 35 from the backfill, so this is the live case, not a hypothetical.
 */
export function buildJornadaSlots(
  rows: GameweekPointsRow[],
  seasonWeekRanges: Record<string, number>,
): JornadaSlot[] {
  const byKey = new Map(rows.map((r) => [`${r.seasonYear}-${r.week}`, r]));
  const seasons = Object.keys(seasonWeekRanges)
    .map(Number)
    .sort((a, b) => a - b);

  const slots: JornadaSlot[] = [];
  for (const seasonYear of seasons) {
    const maxWeek = seasonWeekRanges[String(seasonYear)] ?? 0;
    for (let week = 1; week <= maxWeek; week += 1) {
      const row = byKey.get(`${seasonYear}-${week}`);
      slots.push({
        seasonYear,
        week,
        label: `${seasonLabel(seasonYear)} J${week}`,
        points: row ? row.points : null,
        recorded: row !== undefined,
        isProvisional: row?.isProvisional ?? false,
      });
    }
  }
  return slots;
}

interface PointsPerJornadaChartProps {
  rows: GameweekPointsRow[];
  seasonWeekRanges: Record<string, number>;
  width: number;
  height: number;
  /** Overrides the caption — reused for the squad's own points history
   * (SQUAD-04), where the wording also carries the caveat that it sums the
   * *current* squad rather than the roster as it actually changed over
   * time. Defaults to the player-page wording so existing callers are
   * unaffected. */
  caption?: string;
  emptyMessage?: string;
}

/**
 * DETAIL-03. Both seasons on one axis with a labelled divider (spec D-03):
 * with two jornadas played, a current-season-only chart is two bars and says
 * nothing, and early season is exactly when last year's shape carries the
 * signal. The divider is what stops the chart claiming the two seasons are
 * one continuous run of form.
 */
export default function PointsPerJornadaChart({
  rows,
  seasonWeekRanges,
  width,
  height,
  caption = "Points per jornada",
  emptyMessage = "No jornada scores recorded for this player.",
}: PointsPerJornadaChartProps) {
  const [frameRef, measuredWidth] = useContainerWidth(width);
  const slots = buildJornadaSlots(rows, seasonWeekRanges);

  if (rows.length === 0) {
    return <p className="state-note">{emptyMessage}</p>;
  }

  // The first slot of each season after the first — where a divider goes,
  // labelled with the season it introduces (spec D-03 / "Seasons are
  // labelled, always") so a bare dashed line never has to be decoded from
  // X-axis tick text that `interval="preserveStartEnd"` mostly hides.
  const dividers = slots
    .map((slot, index) => ({ slot, index }))
    .filter(({ slot, index }) => index > 0 && slot.week === 1)
    .map(({ slot }) => ({ x: slot.label, seasonLabel: seasonLabel(slot.seasonYear) }));

  const provisional = slots.some((s) => s.isProvisional);

  return (
    <figure ref={frameRef} className="flex min-w-0 flex-col gap-xs">
      <figcaption className="subsection-title">
        {caption}
      </figcaption>
      <BarChart width={measuredWidth} height={height} data={slots} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="2 4" vertical={false} />
        <XAxis dataKey="label" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
        <YAxis tick={{ fontSize: 11 }} allowDecimals={false} width={32} />
        <Tooltip
          formatter={(value, _name, item) => {
            // Recharts types `value` as `ValueType | undefined` because a
            // Tooltip's formatter is generic over any series, not just this
            // chart's `points: number | null`. The distinction this chart
            // actually cares about — never-recorded vs. provisional vs.
            // settled — lives on the slot itself (`item.payload`), not on
            // `value`'s type, so widening here doesn't touch that logic.
            const slot = item?.payload as JornadaSlot | undefined;
            if (!slot?.recorded) return ["not recorded", "Points"];
            return [slot.isProvisional ? `${value} (provisional)` : String(value), "Points"];
          }}
        />
        {dividers.map((divider) => (
          <ReferenceLine
            key={divider.x}
            x={divider.x}
            stroke="var(--color-neutral)"
            strokeDasharray="4 4"
            label={{ value: divider.seasonLabel, position: "insideTopRight", fontSize: 10 }}
          />
        ))}
        {/* Recharts renders no rectangle at all for a value of 0 — identical
            to how it treats null — so without `minPointSize` a recorded
            zero and an absent week both render as nothing. `minPointSize`
            forces a visible sliver for 0 while leaving null (an absent
            week) still rendering no bar, which is the distinction this
            chart exists to preserve. Verified directly: rendering isolated
            Bar+Cell data of [4, 0, 6, null] with isAnimationActive={false}
            produced 2 rectangles (skipping both 0 and null) without
            minPointSize, and 3 rectangles (skipping only null) with
            minPointSize={3}. */}
        <Bar dataKey="points" minPointSize={3} fill="var(--color-chart-1)" radius={[2, 2, 0, 0]}>
          {slots.map((slot) => (
            <Cell
              key={`${slot.seasonYear}-${slot.week}`}
              fillOpacity={slot.isProvisional ? 0.45 : 1}
            />
          ))}
        </Bar>
      </BarChart>
      <p className="text-xs muted">
        Seasons are separated by a dashed line. A week with no bar has no recorded score, which is
        not the same as a score of zero.
        {provisional && " The lighter bar is provisional and will change."}
      </p>
    </figure>
  );
}
