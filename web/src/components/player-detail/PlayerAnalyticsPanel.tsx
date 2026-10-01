import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { DEFAULT_WINDOWS, fetchPlayerAnalytics, type PlayerAnalytics } from "../../api-client/analytics";
import type { MarketPrediction } from "../../api-client/market-model";
import { formatEuroAbbreviated, formatPercent, formatShortDate } from "../../lib/format";

/** Momentum windows the owner can toggle (ANALYTICS-02's "configurable"). */
const WINDOW_PRESETS = [1, 3, 7, 14, 30, 60];

function num(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? "—" : value.toFixed(digits);
}

function signed(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}`;
}

function Card({ title, value, children }: { title: string; value: ReactNode; children: ReactNode }) {
  return (
    <div className="panel p-md">
      <div className="flex items-baseline justify-between gap-sm">
        <h3 className="subsection-title">{title}</h3>
        <span className="font-[family-name:var(--font-display)] text-[26px] font-bold leading-none tabular-nums">{value}</span>
      </div>
      <div className="pt-xs text-xs muted">{children}</div>
    </div>
  );
}

function PointsList({ points }: { points: number[] }) {
  return <span className="tabular">[{points.join(", ")}]</span>;
}

function PredictionSummary({ prediction }: { prediction: MarketPrediction }) {
  const i = prediction.inputs;
  const terms: string[] = [`last move ${formatPercent(i.lastMovePct)}`];
  if (i.accelerationTerm !== null) terms.push(`acceleration ${signed(i.accelerationTerm)}`);
  if (i.starterTerm) terms.push(`starter change ${signed(i.starterTerm)}`);
  if (i.availabilityTerm !== null)
    terms.push(`${i.availabilityChange} ${signed(i.availabilityTerm)}`);
  if (i.freshPointsTerm !== null) terms.push(`${i.freshPoints} fresh points ${signed(i.freshPointsTerm)}`);
  if (i.baseRateFallback) terms.push("no signal — base rate (most players fall)");
  return (
    <>
      <p>
        Next update: <strong className="capitalize">{prediction.direction}</strong>{" "}
        ({signed(prediction.predictedPct)}%), <strong>{prediction.confidence}</strong> confidence
        · made from the {formatShortDate(prediction.madeOn)} snapshot
        {prediction.retroactive ? " (retroactive)" : ""}
      </p>
      <p>Inputs: {terms.join("; ")}.</p>
      {prediction.outcome && (
        <p>
          Outcome ({prediction.outcome.scoring}, {prediction.outcome.gapDays}-day gap):{" "}
          {formatPercent(prediction.outcome.actualPct)} —{" "}
          <strong>{prediction.outcome.hit ? "hit" : "miss"}</strong>
        </p>
      )}
    </>
  );
}

function Panel({ data }: { data: PlayerAnalytics }) {
  const { form, consistency, power, valuation, economy } = data;
  return (
    <div className="grid gap-md sm:grid-cols-2">
      <Card title="Power Score" value={num(power?.score, 0)}>
        {power ? (
          <>
            <p>
              {power.calibration.a} × rate {num(power.rate, 2)} {signed(power.calibration.c, 3)} ={" "}
              {num(power.qualityPpg, 2)} pts/match; × {power.availabilityFactor} (
              {power.availability ?? "available"}) = {num(power.powerPpg, 2)}; {power.referencePpg} = 100.
            </p>
            <p>
              Rate: this season&apos;s {power.rateMatches} team matches, recency-weighted and shrunk
              toward {num(power.prior, 2)} ({power.priorSource === "last_season" ? "last season" : "position average"}).
            </p>
          </>
        ) : (
          <p>No jornada recorded yet.</p>
        )}
      </Card>
      <Card title="Economy Score" value={num(economy?.score ?? null, 0)}>
        {valuation?.gapPct !== null && valuation?.gapPct !== undefined && valuation.fit ? (
          <>
            <p>
              Priced {formatEuroAbbreviated(valuation.marketValue ?? 0)} against a fair value of{" "}
              {formatEuroAbbreviated(valuation.fairValue ?? 0)} for his points per match at his position (
              {signed(valuation.gapPct, 1)}%).
            </p>
            <p>
              Fair value = e^{valuation.fit.intercept} × (pts/match)^{valuation.fit.slope} (log-log), fitted on{" "}
              {valuation.fit.n} {valuation.fit.pooled ? "players (all positions pooled)" : "players at his position"}
              , R² {num(valuation.fit.rSquared, 2)}. Score = {economy?.basis}.
            </p>
          </>
        ) : (
          <p>No valuation: {valuation?.reason ?? "not enough data"}.</p>
        )}
      </Card>
      <Card title="Form" value={signed(form?.value)}>
        {form ? (
          <p>
            Last {form.formJornadas} jornadas avg {num(form.formAvg, 2)} <PointsList points={form.recentPoints} />{" "}
            vs the {form.baselineJornadas} before them (up to {form.baselineWindow}) avg{" "}
            {num(form.baselineAvg, 2)}. Missed jornadas count as 0.
          </p>
        ) : (
          <p>No jornada recorded yet.</p>
        )}
      </Card>
      <Card title="Consistency" value={num(consistency?.value ?? null, 0)}>
        {consistency && consistency.jornadas > 0 ? (
          <p>
            100 × mean / (mean + SD) over the last {consistency.jornadas} of {consistency.window}{" "}
            jornadas: mean {num(consistency.mean, 2)}, SD {num(consistency.sd, 2)}{" "}
            <PointsList points={consistency.points} />.
          </p>
        ) : (
          <p>No jornada recorded yet.</p>
        )}
      </Card>
    </div>
  );
}

export default function PlayerAnalyticsPanel({ playerId }: { playerId: number }) {
  const [windows, setWindows] = useState<number[]>(DEFAULT_WINDOWS);
  const { data, isLoading, isError } = useQuery({
    queryKey: ["player-analytics", playerId, windows],
    queryFn: () => fetchPlayerAnalytics(playerId, windows),
  });

  function toggle(w: number) {
    setWindows((current) => {
      const next = current.includes(w) ? current.filter((x) => x !== w) : [...current, w];
      return next.length === 0 ? current : next.sort((a, b) => a - b);
    });
  }

  return (
    <section aria-labelledby="analytics-heading" className="flex flex-col gap-md">
      <h2 id="analytics-heading" className="section-title">
        Analytics
      </h2>
      {isLoading && <p className="state-note">Loading analytics…</p>}
      {isError && <p className="state-error">Couldn't load analytics.</p>}
      {data && (
        <>
          <Panel data={data} />
          <div className="panel p-md">
            <div className="flex flex-wrap items-center justify-between gap-sm">
              <h3 className="subsection-title">Value momentum</h3>
              <div className="segmented" role="group" aria-label="Momentum windows">
                {WINDOW_PRESETS.map((w) => (
                  <button
                    key={w}
                    type="button"
                    aria-pressed={windows.includes(w)}
                    onClick={() => toggle(w)}
                    className="tabular"
                  >
                    {w}d
                  </button>
                ))}
              </div>
            </div>
            <div className="mt-sm overflow-x-auto">
            <table className="data-table compact">
              <thead>
                <tr>
                  <th>Window</th>
                  <th>From → to (actual days)</th>
                  <th className="num">Change</th>
                  <th className="num">Per day</th>
                  <th>Direction</th>
                </tr>
              </thead>
              <tbody>
                {data.momentum.map((m) => (
                  <tr key={m.windowDays}>
                    <td>{m.windowDays}d</td>
                    <td>
                      {m.fromDate && m.toDate
                        ? `${formatShortDate(m.fromDate)} → ${formatShortDate(m.toDate)} (${m.days})`
                        : "no snapshot that far back"}
                    </td>
                    <td className="num">{formatPercent(m.pct)}</td>
                    <td className="num">{formatPercent(m.ratePerDay)}</td>
                    <td>{m.direction ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
            <p className="pt-xs text-xs muted">
              From the latest snapshot at or before the window start; snapshots are irregular, so the
              per-day rate divides by the actual span.
            </p>
          </div>
          <div className="panel p-md text-xs">
            <h3 className="subsection-title pb-xs">Our market prediction</h3>
            {data.marketPrediction ? (
              <PredictionSummary prediction={data.marketPrediction} />
            ) : (
              <p className="muted">No prediction yet — run a refresh.</p>
            )}
          </div>
        </>
      )}
    </section>
  );
}
