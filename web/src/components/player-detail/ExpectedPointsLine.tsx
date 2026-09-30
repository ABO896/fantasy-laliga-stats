import { useQuery } from "@tanstack/react-query";
import {
  describeBasis,
  fetchPlayerExpectedPoints,
  type ExpectedPointsPrediction,
} from "../../api-client/expected-points";

const TERM_LABELS: Record<string, string> = {
  rate: "points rate",
  rateXStarter: "rate × starter",
  starter: "starter",
  intercept: "baseline",
  attack: "team goals",
  cleanSheet: "clean sheet",
};

function signed(v: number): string {
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}`;
}

function Inputs({ p }: { p: ExpectedPointsPrediction }) {
  const i = p.inputs;
  const parts: string[] = [];
  if (i.rate) {
    parts.push(
      `points rate ${i.rate.value.toFixed(2)} over ${i.rate.matches} team matches ` +
        `(recent ${i.rate.recentPoints.join(", ") || "none"}; prior ${i.rate.prior.toFixed(2)} ` +
        `from ${i.rate.priorSource === "last_season" ? "last season" : "position average"})`,
    );
  }
  if (i.starterProbability !== null && i.starterProbability !== undefined) {
    parts.push(`starter ${Math.round(i.starterProbability)}%`);
  }
  if (i.fixture?.teamGoals !== null && i.fixture?.teamGoals !== undefined) {
    parts.push(
      `team expected goals ${i.fixture.teamGoals.toFixed(2)}, clean sheet ` +
        `${Math.round((i.fixture.cleanSheet ?? 0) * 100)}% (odds, ${i.fixture.oddsSource})`,
    );
  }
  const terms = Object.entries(i.terms ?? {}).map(
    ([k, v]) => `${TERM_LABELS[k] ?? k} ${signed(v)}`,
  );
  return (
    <>
      {parts.length > 0 && <p>Inputs: {parts.join("; ")}.</p>}
      {terms.length > 0 && <p>Terms: {terms.join(", ")}.</p>}
    </>
  );
}

/** MODEL-02 on the player page: the next jornada's expected points, its
 * basis, and every input it was built from. */
export default function ExpectedPointsLine({ playerId }: { playerId: number }) {
  const { data, isPending, isError } = useQuery({
    queryKey: ["player-expected-points", playerId],
    queryFn: () => fetchPlayerExpectedPoints(playerId),
  });
  if (isPending) return null;
  if (isError) {
    return (
      <p className="state-note">Expected points unavailable.</p>
    );
  }
  const p = data.prediction;
  return (
    <section
      aria-label="Expected points"
      className="panel p-md"
    >
      <div className="flex items-baseline justify-between gap-sm">
        <h2 className="subsection-title">
          Expected points{p ? ` · jornada ${p.jornada}` : ""}
          {p?.opponent ? ` · ${p.isHome ? "vs" : "at"} ${p.opponent}` : ""}
        </h2>
        <span className="font-[family-name:var(--font-display)] text-[26px] font-bold leading-none tabular-nums text-[color:var(--color-accent)]">
          {p ? `${p.expectedPoints.toFixed(1)} xP` : "—"}
        </span>
      </div>
      <div className="pt-xs text-xs muted">
        {p ? (
          <>
            <p>Basis: {describeBasis(p.basis)}.</p>
            <Inputs p={p} />
          </>
        ) : (
          <p>No prediction stored yet — it is made on the next refresh.</p>
        )}
      </div>
    </section>
  );
}
