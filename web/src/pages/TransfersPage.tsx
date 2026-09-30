import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import {
  fetchBargains,
  fetchBest,
  fetchBids,
  fetchSuggestions,
  type Move,
  type Position,
  type PriceBasis,
  type TransferQuery,
} from "../api-client/transfers";
import {
  ConfidenceBadge,
  euro,
  FixtureDriver,
  FreshnessNotice,
  muted,
  num,
  PlayerLink,
} from "../components/transfers/shared";
import { formatPercent } from "../lib/format";
import PageHeader from "../components/ui/PageHeader";

/** Phase 11 — "who should I move?". Four sections, all server-computed:
 * suggested moves, bargains, best by position, and our own bids.
 *
 * The ceiling is BROWSE-05's, carried in the URL the same way (`max` in
 * euros, `basis`), and typed by the owner from the figure they read off
 * the official app. Nothing on this page derives a budget. */

const BASES: { value: PriceBasis; label: string }[] = [
  { value: "marketValue", label: "Market value" },
  { value: "idealBid", label: "Source ideal bid" },
  { value: "maxBid", label: "Source max bid" },
  { value: "ourIdealBid", label: "Our ideal bid" },
  { value: "ourMaxBid", label: "Our max bid" },
];
const POSITIONS: Position[] = ["POR", "DEF", "MED", "DEL"];
const WINDOWS = [1, 3, 5];

function parseMax(raw: string | null): number | null {
  if (raw === null || raw.trim() === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

function useTransferQuery() {
  const [params, setParams] = useSearchParams();
  const basisRaw = params.get("basis");
  const query: TransferQuery = {
    n: Number(params.get("n")) || 3,
    max: parseMax(params.get("max")),
    basis: BASES.some((b) => b.value === basisRaw) ? (basisRaw as PriceBasis) : "marketValue",
  };
  const position = (POSITIONS as string[]).includes(params.get("pos") ?? "")
    ? (params.get("pos") as Position)
    : "DEL";
  const anyPrice = params.get("any") === "1";
  function update(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v === null) next.delete(k);
      else next.set(k, v);
    }
    setParams(next, { replace: true });
  }
  return { query, position, anyPrice, update };
}

function Controls({
  query,
  update,
}: {
  query: TransferQuery;
  update: (c: Record<string, string | null>) => void;
}) {
  return (
    <div className="panel flex flex-wrap items-end gap-md px-md py-sm">
      <label className="flex flex-col gap-xs field-label">
        Price ceiling (€M)
        <input
          aria-label="Price ceiling in millions"
          type="number"
          min={0}
          step={0.1}
          className="field w-[120px] tabular"
          value={query.max === null ? "" : query.max / 1_000_000}
          onChange={(e) =>
            update({
              max: e.target.value === "" ? null : String(Math.round(Number(e.target.value) * 1_000_000)),
            })
          }
        />
      </label>
      <label className="flex flex-col gap-xs field-label">
        Against
        <select
          aria-label="Price basis"
          className="field"
          value={query.basis}
          onChange={(e) => update({ basis: e.target.value })}
        >
          {BASES.map((b) => (
            <option key={b.value} value={b.value}>
              {b.label}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-xs field-label">
        Look ahead
        <select
          aria-label="Jornadas ahead"
          className="field"
          value={query.n}
          onChange={(e) => update({ n: e.target.value })}
        >
          {WINDOWS.map((w) => (
            <option key={w} value={w}>
              {w} jornada{w === 1 ? "" : "s"}
            </option>
          ))}
        </select>
      </label>
      <p className={`${muted} max-w-[420px] pb-[6px]`}>
        Type the figure you can spend, read off the official app. It is never derived — with no
        ceiling, moves ignore price.
      </p>
    </div>
  );
}

function MoveCard({ move, rank }: { move: Move; rank: number }) {
  const { sell, buy } = move;
  return (
    <li className="panel flex flex-col gap-xs px-md py-sm">
      <div className="flex flex-wrap items-center gap-sm text-sm">
        <span className="font-[family-name:var(--font-display)] text-[20px] font-bold leading-none muted tabular-nums">{rank}</span>
        {sell ? (
          <>
            <span className="badge bg-[color:var(--color-destructive)]/12 text-[color:var(--color-destructive)]">Sell</span> <PlayerLink player={sell} />
            <span className={muted}>
              {sell.position} · {euro(sell.marketValue)}
            </span>
            <span aria-hidden className="muted">→</span>
          </>
        ) : (
          <span className="font-semibold">Fill a free slot:</span>
        )}
        <span className="badge bg-[color:var(--color-accent)]/12 text-[color:var(--color-accent)]">buy</span> <PlayerLink player={buy} />
        <span className={muted}>
          {buy.position} · {buy.team} · {euro(buy.marketValue)} · our bid {euro(buy.bids.ourIdeal)}
          –{euro(buy.bids.ourMax)}
        </span>
        <span className="ml-auto font-[family-name:var(--font-display)] text-[20px] font-bold leading-none tabular-nums text-[color:var(--color-accent)]">+{num(move.gain)} pts-eq</span>
        <ConfidenceBadge label={move.confidenceLabel} value={move.confidence} />
      </div>
      <ul className="flex flex-col gap-[2px] border-t border-line pt-xs text-xs">
        {move.signals.map((s) => (
          <li key={s.name}>
            <span className="font-semibold capitalize">{s.name}</span>
            {s.contribution !== null && (
              <span className="tabular"> ({s.contribution >= 0 ? "+" : ""}{num(s.contribution)})</span>
            )}
            : {s.text}
          </li>
        ))}
      </ul>
      {move.confidenceReasons.length > 0 && (
        <p className={muted}>Why not more confident: {move.confidenceReasons.join(" ")}</p>
      )}
      <p className={muted}>Still fields: {move.feasibleFormations.join(", ")}</p>
    </li>
  );
}

function SuggestedMoves({ query }: { query: TransferQuery }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["transfers", "suggestions", query],
    queryFn: () => fetchSuggestions(query),
  });
  return (
    <section className="flex flex-col gap-sm" aria-labelledby="moves-heading">
      <h3 id="moves-heading" className="section-title">
        Suggested moves
      </h3>
      {isLoading && <p className={muted}>Working out moves…</p>}
      {isError && <p className="state-error">Couldn't load suggestions.</p>}
      {data && (
        <>
          <FreshnessNotice freshness={data.freshness} />
          <p className={muted}>
            Squad {data.squadSize}/{data.maxSquadSize}. Gain = change in your best XI's expected
            points over {data.jornadas.spreadOver} jornada
            {data.jornadas.spreadOver === 1 ? "" : "s"}
            {data.jornadas.window.length > 0 && ` (J${data.jornadas.window.join(", J")})`} plus
            the predicted next market move, at the game's cash-per-point rate. Every move keeps
            the squad legal on the squad cap and a fieldable XI.
            {data.expectedPointsUsed ? " Expected points (MODEL-02) are blended in." : ""}
          </p>
          {data.unassessedMembers.length > 0 && (
            <p className={muted}>No expected return for: {data.unassessedMembers.join(", ")}.</p>
          )}
          {data.moves.length === 0 ? (
            <p className="text-sm">
              {data.squadSize === 0
                ? "Add your squad on My Squad first — moves are suggested against it."
                : "No move improves the squad by enough to suggest."}
            </p>
          ) : (
            <ol className="flex flex-col gap-sm">
              {data.moves.map((m, i) => (
                <MoveCard key={`${m.sell?.playerId ?? "add"}-${m.buy.playerId}`} move={m} rank={i + 1} />
              ))}
            </ol>
          )}
        </>
      )}
    </section>
  );
}

function Bargains({ query }: { query: TransferQuery }) {
  const affordableOnly = query.max !== null;
  const { data, isLoading, isError } = useQuery({
    queryKey: ["transfers", "bargains", query],
    queryFn: () => fetchBargains(query, affordableOnly),
  });
  return (
    <section className="flex flex-col gap-sm" aria-labelledby="bargains-heading">
      <h3 id="bargains-heading" className="section-title">
        Bargains
      </h3>
      <p className={muted}>
        Top-quarter expected return for their position, priced below what that return usually
        costs.{affordableOnly ? " Within your ceiling." : ""}
      </p>
      {isLoading && <p className={muted}>Loading bargains…</p>}
      {isError && <p className="state-error">Couldn't load bargains.</p>}
      {data && data.players.length === 0 && <p className="text-sm">No bargains right now.</p>}
      {data && data.players.length > 0 && (
        <div className="table-scroll">
        <table className="data-table compact">
          <thead>
            <tr>
              <th>Player</th>
              <th className="num">Price</th>
              <th className="num">Exp. pts/j</th>
              <th className="num">Usual price for that</th>
              <th className="num">Under by</th>
              <th>Fixture driver</th>
              <th className="num">Our bid</th>
            </tr>
          </thead>
          <tbody>
            {data.players.map((p) => (
              <tr key={p.playerId}>
                <td>
                  <PlayerLink player={p} /> <span className={muted}>{p.position} · {p.team}</span>
                </td>
                <td className="num">{euro(p.marketValue)}</td>
                <td className="num">{num(p.expectedReturn)}</td>
                <td className="num">{euro(p.forwardFairValue)}</td>
                <td className="num">{formatPercent(p.forwardGapPct)}</td>
                <td>
                  <FixtureDriver player={p} />
                </td>
                <td className="num">
                  {euro(p.bids.ourIdeal)}–{euro(p.bids.ourMax)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
    </section>
  );
}

function BestByPosition({
  query,
  position,
  anyPrice,
  update,
}: {
  query: TransferQuery;
  position: Position;
  anyPrice: boolean;
  update: (c: Record<string, string | null>) => void;
}) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["transfers", "best", query, position, anyPrice],
    queryFn: () => fetchBest(query, position, !anyPrice),
  });
  return (
    <section className="flex flex-col gap-sm" aria-labelledby="best-heading">
      <h3 id="best-heading" className="section-title">
        Best by position
      </h3>
      <div className="flex flex-wrap items-center gap-md text-sm">
        <div role="group" aria-label="Position" className="segmented">
          {POSITIONS.map((p) => (
            <button
              key={p}
              type="button"
              aria-pressed={p === position}
              onClick={() => update({ pos: p })}
              data-pos={p}
            >
              {p}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-sm text-sm">
          <input
            type="checkbox"
            checked={!anyPrice}
            onChange={(e) => update({ any: e.target.checked ? null : "1" })}
          />
          Within budget only
        </label>
      </div>
      {isLoading && <p className={muted}>Loading…</p>}
      {isError && <p className="state-error">Couldn't load the ranking.</p>}
      {data?.ceilingMissing && (
        <p className="text-sm font-semibold text-[color:var(--color-warning)]">
          No price ceiling entered, so this shows the best regardless of price — type your figure
          above to filter.
        </p>
      )}
      {data && data.players.length === 0 && (
        <p className="text-sm">Nobody at this position{data.affordableOnly ? " within your ceiling" : ""}.</p>
      )}
      {data && data.players.length > 0 && (
        <div className="table-scroll">
        <table className="data-table compact">
          <thead>
            <tr>
              <th className="num">#</th>
              <th>Player</th>
              <th className="num">Exp. pts/j</th>
              <th className="num">Power</th>
              <th className="num">Price</th>
              <th className="num">pts/j per €1M</th>
              <th>Fixture driver</th>
              <th className="num">Next move</th>
            </tr>
          </thead>
          <tbody>
            {data.players.map((p, i) => (
              <tr key={p.playerId}>
                <td className="num muted">{i + 1}</td>
                <td>
                  <PlayerLink player={p} /> <span className={muted}>{p.team}</span>
                  {p.owned && <span className="badge ml-xs bg-[color:var(--color-accent)]/12 text-[color:var(--color-accent)]">(yours)</span>}
                </td>
                <td className="num">{num(p.expectedReturn)}</td>
                <td className="num">{num(p.powerScore)}</td>
                <td className="num">{euro(p.marketValue)}</td>
                <td className="num">{num(p.efficiency, 2)}</td>
                <td>
                  <FixtureDriver player={p} />
                </td>
                <td className="num">{formatPercent(p.predictedPct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
    </section>
  );
}

function OurBids({ position }: { position: Position }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["transfers", "bids", position],
    queryFn: () => fetchBids(position),
  });
  const rows = useMemo(() => data?.players.slice(0, 25) ?? [], [data]);
  const inputs = rows[0]?.inputs;
  return (
    <section className="flex flex-col gap-sm" aria-labelledby="bids-heading">
      <h3 id="bids-heading" className="section-title">
        Our bids — {position}
      </h3>
      <p className={muted}>
        Ideal = the value we predict after the next market update (never below market value). Max
        = {inputs ? `${inputs.horizonUpdates} updates` : "several updates"} of a predicted rise
        plus {inputs ? `${Number(inputs.surplusShare) * 100}%` : "a share"} of our valuation gap,
        capped at +{inputs ? `${Number(inputs.maxPremium) * 100}%` : "a fixed premium"}. The
        source's numbers are shown for reference only.
      </p>
      {isLoading && <p className={muted}>Loading bids…</p>}
      {isError && <p className="state-error">Couldn't load bids.</p>}
      {rows.length > 0 && (
        <div className="table-scroll">
        <table className="data-table compact">
          <thead>
            <tr>
              <th>Player</th>
              <th className="num">Market value</th>
              <th className="num">Our ideal</th>
              <th className="num">Our max</th>
              <th className="num">Source ideal</th>
              <th className="num">Source max</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((b) => (
              <tr key={b.playerId}>
                <td>
                  <PlayerLink player={b} /> <span className={muted}>{b.team}</span>
                </td>
                <td className="num">{euro(b.marketValue)}</td>
                <td className="num font-semibold">{euro(b.ourIdeal)}</td>
                <td className="num font-semibold">{euro(b.ourMax)}</td>
                <td className="num">{euro(b.sourceIdeal)}</td>
                <td className="num">{euro(b.sourceMax)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
    </section>
  );
}

export default function TransfersPage() {
  const { query, position, anyPrice, update } = useTransferQuery();
  return (
    <div className="flex flex-col gap-xl">
      <PageHeader
        title="Transfers"
        subtitle="Who to move, who is cheap for what they return, and what to bid. Every number is ours, computed from the data held right now."
      />
      <Controls query={query} update={update} />
      <SuggestedMoves query={query} />
      <Bargains query={query} />
      <BestByPosition query={query} position={position} anyPrice={anyPrice} update={update} />
      <OurBids position={position} />
    </div>
  );
}
