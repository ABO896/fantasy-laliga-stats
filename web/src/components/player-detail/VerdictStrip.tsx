import type { ReactNode } from "react";
import type { LatestSnapshot, SquadHolding } from "../../api-client/player-detail";
import { formatEuroAbbreviated, formatNullable, formatProbability } from "../../lib/format";

interface VerdictStripProps {
  latest: LatestSnapshot | null;
  squad: SquadHolding | null;
  predictions: Record<string, number>;
}

function Cell({ label, children, testId }: {
  label: string;
  children: ReactNode;
  testId?: string;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-[2px] px-md py-sm shadow-[inset_-1px_-1px_0_var(--color-line)]" data-testid={testId}>
      <span className="text-xs font-semibold muted">{label}</span>
      <span className="font-[family-name:var(--font-display)] text-[22px] font-bold leading-tight tabular-nums">
        {children}
      </span>
    </div>
  );
}

/**
 * The decision-first strip (spec D-02). It answers "should I be holding this
 * player" before anything is scrolled; the charts below explain the answer.
 *
 * Every value here can legitimately be absent, and each absence is rendered
 * as an absence rather than as a zero — a player with no points has no
 * price-per-point, and printing `0` there would read as *free*, the exact
 * opposite of the truth.
 */
export default function VerdictStrip({ latest, squad, predictions }: VerdictStripProps) {
  if (!latest) {
    return (
      <p className="panel px-md py-sm state-note">
        No market data for this player yet — they have never appeared in a scrape.
      </p>
    );
  }

  const rising = (latest.priceChangeAbs ?? 0) > 0;
  const falling = (latest.priceChangeAbs ?? 0) < 0;

  return (
    <section
      aria-label="Player summary"
      className="panel overflow-hidden"
    >
      <div className="-mb-px -mr-px grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))]">
        <Cell label="Market value">
          {formatEuroAbbreviated(latest.marketValue)}{" "}
          {latest.priceChangeAbs !== null && (
            <span
              className={`text-sm font-semibold ${
                rising
                  ? "text-[color:var(--color-accent)]"
                  : falling
                    ? "text-[color:var(--color-destructive)]"
                    : "muted"
              }`}
            >
              {rising ? "▲" : falling ? "▼" : "–"}
              {formatEuroAbbreviated(Math.abs(latest.priceChangeAbs))}
            </span>
          )}
        </Cell>
        <Cell label="Points">{latest.points}</Cell>
        <Cell label="Price / point" testId="price-per-point">
          {formatNullable(latest.pricePerPoint, (v) => formatEuroAbbreviated(v))}
        </Cell>
        <Cell label="Starter">{formatProbability(latest.starterProbability)}</Cell>
        <Cell label="Availability">
          <span className="capitalize">{latest.availabilityStatus}</span>
        </Cell>
        <Cell label="Next">{latest.nextOpponent ?? "—"}</Cell>
        {predictions.points !== undefined && (
          <Cell label="Predicted (source)">{predictions.points.toFixed(1)}</Cell>
        )}
      </div>
      {squad && (
        <p className="border-t border-line bg-[color:var(--color-accent)]/8 px-md py-sm text-sm">
          <strong>Owned</strong> — bought {formatEuroAbbreviated(squad.purchasePrice)} on{" "}
          {squad.acquiredOn}
        </p>
      )}
    </section>
  );
}
