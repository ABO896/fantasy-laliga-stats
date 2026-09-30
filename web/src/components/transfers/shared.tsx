import { Link } from "react-router-dom";
import type {
  ConfidenceLabel,
  Freshness,
  TransferFixture,
  TransferPlayer,
} from "../../api-client/transfers";
import { formatEuroAbbreviated } from "../../lib/format";

export const muted = "text-xs muted";

const CONFIDENCE_CLASS: Record<ConfidenceLabel, string> = {
  high: "bg-[color:var(--color-accent)]/10 text-[color:var(--color-accent)]",
  medium: "bg-[color:var(--color-warning)]/10 text-[color:var(--color-warning)]",
  low: "bg-[color:var(--color-destructive)]/10 text-[color:var(--color-destructive)]",
};

/** Transfer confidence — its own vocabulary (high/medium/low), deliberately
 * not the market model's strong/moderate/weak. */
export function ConfidenceBadge({ label, value }: { label: ConfidenceLabel; value: number }) {
  return (
    <span
      className={`badge ${CONFIDENCE_CLASS[label]}`}
      title={`Confidence ${Math.round(value * 100)}%`}
    >
      {label} confidence · {Math.round(value * 100)}%
    </span>
  );
}

export function PlayerLink({ player }: { player: Pick<TransferPlayer, "playerId" | "name"> }) {
  return (
    <Link
      to={`/players/${player.playerId}`}
      className="link font-semibold"
    >
      {player.name}
    </Link>
  );
}

export function euro(value: number | null): string {
  return value === null ? "—" : formatEuroAbbreviated(value);
}

export function num(value: number | null, digits = 1): string {
  return value === null ? "—" : value.toFixed(digits);
}

export function FixtureDriver({ player }: { player: TransferPlayer }) {
  if (!player.fixtureDataAvailable) return <span className={muted}>no fixture data</span>;
  const d: TransferFixture | null = player.fixtureDriver;
  if (!d) return <span className={muted}>no match in window</span>;
  return (
    <span title={player.fixtures.map((f) => `J${f.matchday} ${f.label}`).join(", ")}>
      {d.label}
    </span>
  );
}

/** TRANSFER-04: every section carries this. When the data is stale the
 * page says so and why, rather than presenting a confident list. */
export function FreshnessNotice({ freshness }: { freshness: Freshness }) {
  if (freshness.reasons.length === 0) {
    return (
      <p className={muted} data-testid="freshness-ok">
        Data is current — confidence is limited only by each player's own evidence.
      </p>
    );
  }
  const tone =
    freshness.label === "low"
      ? "border-[color:var(--color-destructive)] bg-[color:var(--color-destructive)]/5"
      : "border-[color:var(--color-warning)] bg-[color:var(--color-warning)]/5";
  return (
    <div role="status" className={`rounded-[var(--radius-md)] border border-l-4 px-md py-sm text-sm ${tone}`}>
      <p className="font-semibold">
        Suggestions are less certain than they look — data confidence{" "}
        {Math.round(freshness.confidence * 100)}% ({freshness.label}).
      </p>
      <ul className="list-disc pl-lg">
        {freshness.reasons.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
    </div>
  );
}
