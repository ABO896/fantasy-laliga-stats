import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  fetchDivergence,
  fetchMarketPredictions,
  fetchTrackRecord,
  type MarketConfidence,
  type MarketModelVersion,
  type MarketPredictionRow,
  type RecordBucket,
  type TrackRecordResponse,
  type V1TrackRecordResponse,
} from "../../api-client/market-model";
import { fetchVerdictValidation } from "../../api-client/verdict";
import { formatEuroAbbreviated, formatPercent, formatShortDate } from "../../lib/format";
import { formatRate, tierRecord } from "../../lib/marketRecord";
import VerdictValidationTable from "../verdict/VerdictValidationTable";

const TIERS: MarketConfidence[] = ["strong", "moderate", "weak"];
const LIST_LENGTH = 15;

const CONFIDENCE_CLASS: Record<MarketConfidence, string> = {
  strong: "bg-[color:var(--color-accent)]/10 text-[color:var(--color-accent)]",
  moderate: "bg-[color:var(--color-warning)]/10 text-[color:var(--color-warning)]",
  weak: "bg-[color:var(--color-neutral)]/10 muted",
};

function Confidence({ tier }: { tier: MarketConfidence }) {
  return (
    <span className={`badge ${CONFIDENCE_CLASS[tier]}`}>
      {tier}
    </span>
  );
}

function PredictionList({ title, rows }: { title: string; rows: MarketPredictionRow[] }) {
  return (
    <div>
      <h4 className="subsection-title pb-xs">{title}</h4>
      {rows.length === 0 ? (
        <p className="text-xs muted">None.</p>
      ) : (
        <div className="table-scroll">
        <table className="data-table compact">
          <tbody>
            {rows.map((r) => (
              <tr key={r.playerId}>
                <td>
                  <Link to={`/players/${r.playerId}`} className="link">
                    {r.name}
                  </Link>{" "}
                  <span className="muted">{r.position}</span>
                </td>
                <td className="num">
                  {r.marketValue === null ? "—" : formatEuroAbbreviated(r.marketValue)}
                </td>
                <td className="num">{formatPercent(r.predictedPct)}</td>
                <td className="num">
                  <Confidence tier={r.confidence} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
    </div>
  );
}

function Predictions({ record }: { record: TrackRecordResponse | undefined }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["market-predictions"],
    queryFn: fetchMarketPredictions,
  });
  if (isLoading) return <p className="state-note">Loading predictions…</p>;
  if (isError || !data) return <p className="text-sm">Couldn't load predictions.</p>;
  if (data.madeOn === null)
    return <p className="text-sm">No predictions yet — they are generated on every refresh.</p>;

  const risers = data.predictions.filter((p) => p.direction === "rise").slice(0, LIST_LENGTH);
  const fallers = [...data.predictions]
    .filter((p) => p.direction === "fall")
    .sort((a, b) => a.predictedPct - b.predictedPct)
    .slice(0, LIST_LENGTH);
  const { label, bucket } = tierRecord(record);

  return (
    <section className="flex flex-col gap-sm">
      <h3 className="section-title">
        Next market update — from the {formatShortDate(data.madeOn)} snapshot
      </h3>
      <p className="text-xs muted">
        {data.predictions.length} players predicted ({data.modelVersion}). Confidence words and
        their {label} hit rates:{" "}
        {TIERS.map((t) => `${t} ${formatRate(bucket?.byConfidence[t])}`).join(" · ")}.
      </p>
      <div className="grid gap-lg md:grid-cols-2">
        <PredictionList title="Likely risers" rows={risers} />
        <PredictionList title="Likely fallers" rows={fallers} />
      </div>
    </section>
  );
}

function BucketRow({ name, bucket }: { name: string; bucket: RecordBucket }) {
  return (
    <tr>
      <th scope="row">{name}</th>
      <td className="num">{formatRate(bucket)}</td>
      {TIERS.map((t) => (
        <td key={t} className="tabular text-right">
          {formatRate(bucket.byConfidence[t])}
        </td>
      ))}
      <td className="num">{formatRate(bucket.byScoring.exact)}</td>
      <td className="num">{formatRate(bucket.byScoring.interval)}</td>
      <td className="num">{bucket.pending}</td>
    </tr>
  );
}

function TrackRecord({ record }: { record: V1TrackRecordResponse }) {
  return (
    <section className="flex flex-col gap-sm">
      <h3 className="section-title">Track record</h3>
      <p className="text-xs muted">
        Every prediction is scored against the next captured snapshot. One day later, that
        snapshot's published move <em>is</em> the predicted update (<strong>exact</strong>). Longer
        gaps only show the net change across them (<strong>interval</strong>), which can hide a
        reversal. Live calls were made before the update they predict; the backtest was computed
        afterwards from the same history and is never merged into the live record.
      </p>
      <div className="table-scroll">
      <table className="data-table compact">
        <thead>
          <tr>
            <th />
            <th className="num">All</th>
            {TIERS.map((t) => (
              <th key={t} className="num capitalize">
                {t}
              </th>
            ))}
            <th className="num">Exact</th>
            <th className="num">Interval</th>
            <th className="num">Pending</th>
          </tr>
        </thead>
        <tbody>
          <BucketRow name="Live" bucket={record.ours.live} />
          <BucketRow name="Backtest" bucket={record.ours.retroactive} />
        </tbody>
      </table>
      </div>
      <p className="text-xs muted">
        The source's published lists, scored the same way: {formatRate(record.source)}; ours on
        the same player-days: {formatRate(record.source.oursOnSamePlayers)}.
        {record.source.scored < 100 && " Small sample — read it as an anecdote, not a verdict."}
      </p>
      <details className="text-xs">
        <summary className="cursor-pointer text-sm font-semibold text-[color:var(--color-accent)]">By day</summary>
        <div className="table-scroll mt-sm">
        <table className="data-table compact">
          <thead>
            <tr>
              <th>Made on</th>
              <th className="num">Predicted</th>
              <th className="num">Hit rate</th>
              <th>Scored against</th>
            </tr>
          </thead>
          <tbody>
            {record.days.map((d) => (
              <tr key={d.madeOn}>
                <td>
                  {formatShortDate(d.madeOn)}
                  {d.retroactive ? " (backtest)" : ""}
                </td>
                <td className="num">{d.predictions}</td>
                <td className="num">{formatRate(d)}</td>
                <td>{d.scoring ? `${d.scoring}, ${d.gapDays}-day gap` : "pending"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </details>
    </section>
  );
}

/** market-v2's track record: our hit rate (live/retroactive) beside the
 * naive baseline's, and MAE/interval-coverage — a different report from
 * v1's exact/interval confidence table, not a variant of it. */
function V2TrackRecord({ record }: { record: TrackRecordResponse }) {
  const mae = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(2));
  const pct = (v: number | null | undefined) => (v == null ? "—" : `${(v * 100).toFixed(1)}%`);
  return (
    <section className="flex flex-col gap-sm">
      <h3 className="section-title">Track record — v2 (7-day)</h3>
      <p className="text-xs muted">
        v2 predicts the change over the next 7 days; the naive baseline assumes next week repeats
        last week.
      </p>
      <div className="table-scroll">
        <table className="data-table compact">
          <thead>
            <tr>
              <th />
              <th className="num">Hit rate</th>
              <th className="num">MAE</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">Ours (live)</th>
              <td className="num">{formatRate(record.ours.live)}</td>
              <td className="num">{mae(record.mae)}</td>
            </tr>
            <tr>
              <th scope="row">Ours (backtest)</th>
              <td className="num">{formatRate(record.ours.retroactive)}</td>
              <td className="num">{mae(record.mae)}</td>
            </tr>
            <tr>
              <th scope="row">Naive — {record.naive?.rule ?? "next week repeats last week"}</th>
              <td className="num">{pct(record.naive?.hitRate)}</td>
              <td className="num">{mae(record.naive?.mae)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p className="text-xs muted">Interval coverage: {pct(record.intervalCoverage)}</p>
    </section>
  );
}

function Divergence() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["market-divergence"],
    queryFn: fetchDivergence,
  });
  if (isLoading) return <p className="state-note">Loading divergence…</p>;
  if (isError || !data) return <p className="text-sm">Couldn't load the divergence view.</p>;
  return (
    <section className="flex flex-col gap-sm">
      <h3 className="section-title">Where we disagree with the source</h3>
      {data.asOf === null ? (
        <p className="text-sm">The source has published no market lists yet.</p>
      ) : (
        <>
          <p className="text-xs muted">
            {formatShortDate(data.asOf)}: of the {data.rows.length} players the source listed, we
            disagree on {data.disagree} and agree on {data.agree}
            {data.ourCallMissing ? `; ${data.ourCallMissing} have no call from us` : ""}.
          </p>
          <div className="table-scroll">
      <table className="data-table compact">
            <thead>
              <tr>
                <th>Player</th>
                <th>Source says</th>
                <th>We say</th>
                <th>Status</th>
                <th>Outcome</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <tr key={`${r.playerId}-${r.sourceList}`}>
                  <td>
                    <Link to={`/players/${r.playerId}`} className="link">
                      {r.name}
                    </Link>
                  </td>
                  <td>
                    {r.sourceDirection}{" "}
                    <span className="muted">
                      ({r.sourceList.replace("market_", "").replace("_", " ")})
                    </span>
                  </td>
                  <td>
                    {r.ours ? (
                      <>
                        {r.ours.direction} ({formatPercent(r.ours.predictedPct)}){" "}
                        <Confidence tier={r.ours.confidence} />
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className={r.status === "disagree" ? "font-semibold" : ""}>{r.status}</td>
                  <td>
                    {r.ours?.outcome
                      ? `${r.ours.outcome.actualDirection} ${formatPercent(r.ours.outcome.actualPct)}`
                      : "pending"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </>
      )}
    </section>
  );
}

/** Plan C Task 6 — the stored walk-forward report (`storage/verdict_backtest.py`),
 * directly below the track record block: both answer "has this number
 * earned our trust", one for market moves, one for verdict labels. */
function VerdictValidation() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["verdict-validation"],
    queryFn: fetchVerdictValidation,
  });
  return (
    <section className="flex flex-col gap-sm" aria-labelledby="verdict-validation-heading">
      <h3 id="verdict-validation-heading" className="section-title">
        Verdict validation
      </h3>
      <p className="text-xs muted">
        Each label that makes a forward claim, scored against what an average eligible
        same-position player (available, past the evidence floor) did on the same day — a label
        beats chance only when its 90% interval clears zero.
      </p>
      {isLoading && <p className="state-note">Loading the validation report…</p>}
      {isError && <p className="state-error">Couldn't load the validation report.</p>}
      {data && <VerdictValidationTable report={data} />}
    </section>
  );
}

const VERSION_LABEL: Record<MarketModelVersion, string> = {
  "market-v1": "v1 · next update",
  "market-v2": "v2 · 7-day",
};

function VersionToggle({
  version,
  onChange,
}: {
  version: MarketModelVersion;
  onChange: (v: MarketModelVersion) => void;
}) {
  return (
    <div className="segmented" role="group" aria-label="Track record model version">
      {(Object.keys(VERSION_LABEL) as MarketModelVersion[]).map((v) => (
        <button
          key={v}
          type="button"
          aria-pressed={version === v}
          className={`badge ${version === v ? "bg-[color:var(--color-accent)]/10 text-[color:var(--color-accent)]" : "muted"}`}
          onClick={() => onChange(v)}
        >
          {VERSION_LABEL[v]}
        </button>
      ))}
    </div>
  );
}

/** MODEL-01/03/04 on one tab: our predictions, how right they have been,
 * and where they part ways with the source's. The track record's version
 * toggle switches between v1's next-update record and v2's 7-day one. */
export default function MarketModelTab() {
  const [version, setVersion] = useState<MarketModelVersion>("market-v1");
  const { data: record } = useQuery({
    queryKey: ["market-track-record", version],
    queryFn: () => fetchTrackRecord(version),
  });
  return (
    <div className="flex flex-col gap-xl">
      <p className="state-note max-w-[70ch]">
        Market prediction is inference under partial observation: who is buying is invisible, so
        this model works from the last published move, its acceleration, starter and availability
        changes, and fresh points. Prices are highly persistent, and this model is essentially
        persistence plus a nudge — what it adds is an honest confidence tier, not magic.
      </p>
      <Predictions record={version === "market-v1" ? record : undefined} />
      <VersionToggle version={version} onChange={setVersion} />
      {record && (version === "market-v1" ? (
        <TrackRecord record={record as V1TrackRecordResponse} />
      ) : (
        <V2TrackRecord record={record} />
      ))}
      <VerdictValidation />
      <Divergence />
    </div>
  );
}
