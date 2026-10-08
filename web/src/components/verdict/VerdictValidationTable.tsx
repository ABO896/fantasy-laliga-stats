import type { ValidationLabelRow, ValidationReport } from "../../api-client/verdict";

/** The forward claim each metric code reads as, in words — see
 * `core.verdict_harness.CLAIMS`. "" is a label with no forward claim
 * (Unavailable/Unproven/Fair price), reported by count only. */
const METRIC_WORDS: Record<string, string> = {
  points: "points",
  points_per_m: "points per €M",
  price_pct: "price change (%)",
  minutes: "minutes played",
  "": "no forward claim",
};

function metricWords(metric: string): string {
  return METRIC_WORDS[metric] ?? metric;
}

function num(value: number | null, digits = 2): string {
  return value === null ? "—" : value.toFixed(digits);
}

function pct(value: number | null): string {
  return value === null ? "—" : `${(value * 100).toFixed(1)}%`;
}

function momentum(row: ValidationLabelRow): string {
  const m = row.momentumBaseline;
  if (!m) return "—";
  return `${num(m.meanDiff)} (n ${m.n}, hit ${pct(m.hitRate)})`;
}

/**
 * The stored walk-forward report (Plan C's harness,
 * `storage/verdict_backtest.py`), one row per label: what it claims, how
 * many observations and players it was checked against, its hit rate
 * beside the same-position base rate, the mean difference with its 90%
 * bootstrap interval, and whether that interval clears zero. The price
 * labels also show the same claim over plain momentum (top / bottom 15%
 * 7-day movers) — a label that loses to it adds nothing a sorted column
 * would not.
 */
export default function VerdictValidationTable({ report }: { report: ValidationReport }) {
  if (report.generatedAt === null) {
    return (
      <p className="state-note">
        Run <code>uv run python -m storage.verdict_backtest --write</code> to refresh.
      </p>
    );
  }

  return (
    <div className="table-scroll">
      <table className="data-table compact">
        <thead>
          <tr>
            <th>Label</th>
            <th>Metric</th>
            <th className="num">n</th>
            <th className="num">Players</th>
            <th className="num">Hit rate</th>
            <th className="num">Base rate</th>
            <th className="num">Mean diff (90% CI)</th>
            <th className="num">Beats chance</th>
            <th className="num" title="Same claim over the top/bottom 15% 7-day movers">
              Mean diff vs momentum
            </th>
          </tr>
        </thead>
        <tbody>
          {report.labels.map((row) => (
            <tr key={row.label}>
              <td>{row.label}</td>
              <td>{metricWords(row.metric)}</td>
              <td className="num">{row.n}</td>
              <td className="num">{row.players}</td>
              <td className="num">{pct(row.hitRate)}</td>
              <td className="num">{pct(row.baseRate)}</td>
              <td className="num">
                {num(row.meanDiff)} ({num(row.ciLow)}, {num(row.ciHigh)})
              </td>
              <td className="num">{row.beatsChance ? "✓" : "✗"}</td>
              <td className="num">{momentum(row)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
