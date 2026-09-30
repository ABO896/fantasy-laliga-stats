import { useQuery } from "@tanstack/react-query";
import { fetchSquad } from "../api-client/squad";
import { formatEuroAbbreviated } from "../lib/format";

const POSITIONS = ["POR", "DEF", "MED", "DEL"] as const;

/** One cache entry shared by the bar, the player browser and the squad page,
 * so every surface shows the same numbers the instant any of them mutates. */
export function useSquad() {
  return useQuery({ queryKey: ["squad"], queryFn: fetchSquad });
}

/**
 * Spec D-06: squad value, squad size and per-position counts stay in view
 * on both the player browser and the squad page — the numbers must be present
 * at the moment of the decision, not one page away.
 *
 * Two states are shown, deliberately distinct:
 *   incomplete  — no XI reachable yet. Not illegal (spec D-09).
 *   illegal     — an actual rule violation, with its remedy.
 */
export default function SquadBar() {
  const { data, isLoading, isError } = useSquad();

  // Loading briefly on every navigation is normal; showing nothing for it
  // avoids a bar that flashes in and out. A permanent failure below gets
  // its own message instead, so it isn't mistaken for this.
  if (isLoading) return null;

  if (isError) {
    return (
      <div role="alert" className="border-b border-line bg-surface">
        <p className="mx-auto max-w-[1600px] px-md py-sm text-sm font-semibold text-[color:var(--color-destructive)] sm:px-lg lg:px-xl">
          Squad unavailable — couldn&apos;t reach the API. Your squad is not being shown.
        </p>
      </div>
    );
  }
  if (!data) return null;
  const s = data.summary;
  const missing = Object.entries(s.missingForXi);
  return (
    <div className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-lg gap-y-xs px-md py-sm text-sm sm:px-lg lg:px-xl">
        <span className="whitespace-nowrap">
          <span className="muted">Squad value </span>
          <span className="tabular font-semibold">{formatEuroAbbreviated(s.squadValue)}</span>
        </span>
        <span className="whitespace-nowrap">
          <span className="muted">Squad </span>
          <span className="tabular font-semibold">
            {s.squadSize} / {s.maxSquadSize}
          </span>
        </span>
        <span className="flex gap-xs">
          {POSITIONS.map((position) => (
            <span
              key={position}
              data-testid={`slots-${position}`}
              data-pos={position}
              className="pos-badge gap-[3px]"
            >
              {position} <span className="tabular text-ink">{s.positionCounts[position] ?? 0}</span>
            </span>
          ))}
        </span>
        <span className="text-xs">
          {s.canFieldXi ? (
            <span className="muted">Formations available: {s.feasibleFormations.join(", ")}</span>
          ) : (
            <span className="font-semibold text-[color:var(--color-warning)]">
              No formation reachable yet — need{" "}
              {missing.map(([position, count]) => `${count} more ${position}`).join(", ")}
              {s.nearestFormation && ` to reach ${s.nearestFormation}`}
            </span>
          )}
        </span>
        {!s.isLegal && (
          <ul className="w-full text-xs text-[color:var(--color-destructive)]">
            {s.violations.map((violation) => (
              <li key={violation.rule}>{violation.message}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
