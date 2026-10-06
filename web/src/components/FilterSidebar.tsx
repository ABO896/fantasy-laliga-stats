import type { PlayerRow } from "../api-client/players";
import { VERDICT_LABELS } from "../api-client/verdict";
import { formatEuroAbbreviated } from "../lib/format";
import PosBadge from "./ui/PosBadge";

export type PriceBasis = "marketValue" | "idealBid" | "maxBid";

export interface PlayerFilters {
  positions: string[];
  teams: string[];
  availability: string[];
  /** Plan C Task 6 — which verdict labels to keep; empty means no
   * constraint, same semantics as every other facet here. */
  verdict: string[];
  /** Euros, not millions — the input takes millions and converts. Null means
   * no ceiling at all, which is not the same as zero. */
  maxPrice: number | null;
  priceBasis: PriceBasis;
  /** DETAIL-04. Optional so a caller that predates the watchlist (or a test
   * literal) needn't name it; absent means off. */
  watchlistOnly?: boolean;
}

const POSITIONS: PlayerRow["position"][] = ["POR", "DEF", "MED", "DEL"];
const AVAILABILITY: PlayerRow["availabilityStatus"][] = [
  "available",
  "injured",
  "doubtful",
  "suspended",
];

const PRICE_BASES: { value: PriceBasis; label: string }[] = [
  { value: "marketValue", label: "Market value" },
  // Labelled as the source's numbers, deliberately. They are
  // analiticafantasy's proprietary model outputs, stored as reference
  // fields (INGEST-07) — the app's own default stays on the game's
  // published valuation, and choosing theirs is a visible act.
  { value: "idealBid", label: "Ideal bid (Analítica)" },
  { value: "maxBid", label: "Max bid (Analítica)" },
];

interface FilterSidebarProps {
  value: PlayerFilters;
  onChange: (next: PlayerFilters) => void;
  players: PlayerRow[];
  /** How many players are watchlisted. `undefined` while the watchlist is
   * unknown (loading or failed) — the filter is then omitted rather than
   * offered against a list that might be wrong. */
  watchlistCount?: number;
}

function toggle(list: string[], item: string): string[] {
  return list.includes(item) ? list.filter((v) => v !== item) : [...list, item];
}

type ChipFacet = "positions" | "teams" | "availability" | "verdict";

interface Chip {
  facet: ChipFacet;
  value: string;
}

function basisLabel(basis: PriceBasis): string {
  return PRICE_BASES.find((b) => b.value === basis)?.label ?? basis;
}

/** 4.1 -> 4_100_000 exactly. `millions * 1_000_000` alone is not exact in
 * floating point (4.1 * 1_000_000 === 4099999.9999999995), which would
 * exclude a player priced at precisely the typed ceiling. */
function millionsToEuros(millions: number): number {
  return Math.round(millions * 1_000_000);
}

/**
 * Combination semantics (pinned here since no source artifact specifies
 * them — see this plan's flagged assumption): selections within one facet
 * combine as OR, facets combine with each other as AND, and a facet with
 * nothing selected imposes no constraint at all. Deselecting everything in
 * a facet restores "show all" for that facet rather than collapsing to zero
 * matches.
 */
export default function FilterSidebar({
  value,
  onChange,
  players,
  watchlistCount,
}: FilterSidebarProps) {
  const teams = Array.from(new Set(players.map((p) => p.team))).sort((a, b) =>
    a.localeCompare(b),
  );

  const chips: Chip[] = [
    ...value.positions.map((v): Chip => ({ facet: "positions", value: v })),
    ...value.teams.map((v): Chip => ({ facet: "teams", value: v })),
    ...value.availability.map((v): Chip => ({ facet: "availability", value: v })),
    ...value.verdict.map((v): Chip => ({ facet: "verdict", value: v })),
  ];
  const hasPriceFilter = value.maxPrice !== null;
  const watchlistOnly = value.watchlistOnly === true;
  const hasAnyFilter = chips.length > 0 || hasPriceFilter || watchlistOnly;

  function removeChip(chip: Chip) {
    onChange({ ...value, [chip.facet]: value[chip.facet].filter((v) => v !== chip.value) });
  }

  function clearPrice() {
    onChange({ ...value, maxPrice: null });
  }

  function clearAll() {
    onChange({
      positions: [],
      teams: [],
      availability: [],
      verdict: [],
      maxPrice: null,
      priceBasis: "marketValue",
      watchlistOnly: false,
    });
  }

  const chipClass =
    "inline-flex items-center gap-[3px] rounded-full bg-[color:var(--color-accent)]/12 px-sm py-[2px] text-xs font-semibold text-[color:var(--color-accent)] hover:bg-[color:var(--color-accent)]/20";
  const legendClass = "subsection-title mb-xs";
  const optionClass = "flex items-center gap-sm py-[3px] text-sm";

  return (
    <div className="flex w-full shrink-0 flex-col gap-md lg:sticky lg:top-[72px] lg:w-[220px]">
      {hasAnyFilter && (
        <div className="flex flex-wrap items-center gap-xs" data-testid="active-filter-chips">
          {watchlistOnly && (
            <button
              type="button"
              onClick={() => onChange({ ...value, watchlistOnly: false })}
              className={chipClass}
            >
              Watchlist ×
            </button>
          )}
          {hasPriceFilter && (
            <button type="button" onClick={clearPrice} className={chipClass}>
              ≤ {formatEuroAbbreviated(value.maxPrice!)} ({basisLabel(value.priceBasis)}) ×
            </button>
          )}
          {chips.map((chip) => (
            <button
              key={`${chip.facet}-${chip.value}`}
              type="button"
              onClick={() => removeChip(chip)}
              className={`${chipClass} capitalize`}
            >
              {chip.value} ×
            </button>
          ))}
          <button
            type="button"
            onClick={clearAll}
            className="text-xs font-semibold muted underline hover:text-ink"
          >
            Clear all
          </button>
        </div>
      )}
      <aside className="panel flex flex-col gap-md p-md lg:max-h-[calc(100vh-96px)] lg:overflow-y-auto">
        {watchlistCount !== undefined && (
          <fieldset>
            <legend className={legendClass}>Watchlist</legend>
            <label className={optionClass}>
              <input
                type="checkbox"
                checked={watchlistOnly}
                onChange={() => onChange({ ...value, watchlistOnly: !watchlistOnly })}
              />
              Watchlist only
            </label>
            <p className="text-xs muted">{watchlistCount} watched</p>
          </fieldset>
        )}

        <fieldset>
          <legend className={legendClass}>Budget</legend>
          <div className="grid grid-cols-2 gap-sm lg:grid-cols-1">
            <label className="flex flex-col gap-xs text-sm">
              <span className="field-label">Max price (€M)</span>
              <input
                type="number"
                min={0}
                step={0.1}
                inputMode="decimal"
                value={value.maxPrice === null ? "" : value.maxPrice / 1_000_000}
                onChange={(event) => {
                  const raw = event.target.value.trim();
                  const millions = Number(raw);
                  onChange({
                    ...value,
                    maxPrice:
                      raw === "" || Number.isNaN(millions) ? null : millionsToEuros(millions),
                  });
                }}
                className="field tabular"
              />
            </label>
            <label className="flex flex-col gap-xs text-sm">
              <span className="field-label">Price basis</span>
              <select
                value={value.priceBasis}
                onChange={(event) =>
                  onChange({ ...value, priceBasis: event.target.value as PriceBasis })
                }
                className="field"
              >
                {PRICE_BASES.map((basis) => (
                  <option key={basis.value} value={basis.value}>
                    {basis.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </fieldset>

        <fieldset>
          <legend className={legendClass}>Position</legend>
          <div className="grid grid-cols-4 gap-xs lg:grid-cols-2">
            {POSITIONS.map((pos) => (
              <label key={pos} className={optionClass}>
                <input
                  type="checkbox"
                  checked={value.positions.includes(pos)}
                  onChange={() => onChange({ ...value, positions: toggle(value.positions, pos) })}
                />
                <PosBadge position={pos} />
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend className={legendClass}>Team</legend>
          <div className="grid grid-cols-2 gap-x-sm sm:grid-cols-3 lg:grid-cols-1">
            {teams.map((team) => (
              <label key={team} className={`${optionClass} min-w-0`}>
                <input
                  type="checkbox"
                  checked={value.teams.includes(team)}
                  onChange={() => onChange({ ...value, teams: toggle(value.teams, team) })}
                />
                <span className="truncate">{team}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend className={legendClass}>Availability</legend>
          <div className="grid grid-cols-2 gap-x-sm lg:grid-cols-1">
            {AVAILABILITY.map((status) => (
              <label key={status} className={`${optionClass} capitalize`}>
                <input
                  type="checkbox"
                  checked={value.availability.includes(status)}
                  onChange={() =>
                    onChange({ ...value, availability: toggle(value.availability, status) })
                  }
                />
                {status}
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend className={legendClass}>Verdict</legend>
          <div className="grid grid-cols-2 gap-x-sm lg:grid-cols-1">
            {VERDICT_LABELS.map((label) => (
              <label key={label} className={optionClass}>
                <input
                  type="checkbox"
                  checked={value.verdict.includes(label)}
                  onChange={() => onChange({ ...value, verdict: toggle(value.verdict, label) })}
                />
                {label}
              </label>
            ))}
          </div>
        </fieldset>
      </aside>
    </div>
  );
}
