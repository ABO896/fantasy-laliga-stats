import type { ReactNode } from "react";
import { bandFor, METRIC_COPY, rankText, type MetricKey } from "../../lib/metricCopy";
import type { Step } from "./StepTable";
import StepTable from "./StepTable";

export interface MetricRank {
  rank: number;
  of: number;
  percentile: number;
  position: string;
}

/** One metric's full self-explanation: value · plain word · within-position
 * rank, what it means, why it matters, and a collapsed step table ending
 * in the headline number (Plan D, Task 3). Every metric on the player page
 * renders through this one component so the layout never drifts between
 * them. */
export interface MetricCardProps {
  metric: MetricKey;
  /** The formatted headline ("71", "+1.8%", "Regular"); `null` when the
   * player has no value for this metric at all. */
  value: string | null;
  /** Overrides the percentile-band word with the metric's own vocabulary
   * (reliability's class, outlook's direction, verdict's label). Leave
   * unset to fall back to `bandFor`. */
  word?: string | null;
  rank: MetricRank | null;
  steps: Step[] | null;
  headline: Step | null;
  /** An optional typeset formula, shown above the step table. */
  formula?: ReactNode;
  /** Shown instead of the step table when `value` is null. */
  emptyReason?: string | null;
  /** Extras below everything else — the momentum window toggle, a
   * prediction outcome line — rendered regardless of whether `value` is
   * null, since controls like the toggle must stay usable either way. */
  children?: ReactNode;
}

export default function MetricCard({
  metric,
  value,
  word,
  rank,
  steps,
  headline,
  formula,
  emptyReason,
  children,
}: MetricCardProps) {
  const copy = METRIC_COPY[metric];
  const effectiveWord = word !== undefined ? word : bandFor(metric, rank?.percentile ?? null, rank?.of);
  const rankLabel = rankText(rank);

  return (
    <div className="panel p-md">
      <div className="flex items-baseline justify-between gap-sm">
        <h3 className="subsection-title">{copy.title}</h3>
        <span className="font-[family-name:var(--font-display)] text-[26px] font-bold leading-none tabular-nums">
          {value ?? "—"}
        </span>
      </div>
      {(effectiveWord !== null || rankLabel !== null) && (
        <div className="flex flex-wrap items-center gap-xs pt-xs text-xs">
          {effectiveWord !== null && (
            <span className="badge bg-[color:var(--color-surface-alt)]">{effectiveWord}</span>
          )}
          {rankLabel !== null && <span className="muted">{rankLabel}</span>}
        </div>
      )}
      <p className="pt-xs text-sm">{copy.meaning}</p>
      <p className="pt-xs text-xs muted">Why it matters: {copy.why}</p>
      {value === null ? (
        emptyReason && <p className="pt-xs text-xs muted">{emptyReason}</p>
      ) : (
        <div className="pt-xs">
          {formula && <div className="pb-xs">{formula}</div>}
          {steps && headline && <StepTable steps={steps} headline={headline} />}
        </div>
      )}
      {children}
    </div>
  );
}
