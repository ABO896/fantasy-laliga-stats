import {
  columnFilteringFeature,
  columnVisibilityFeature,
  createFilteredRowModel,
  createSortedRowModel,
  rowSortingFeature,
  tableFeatures,
  type ColumnDef,
  type Row,
} from "@tanstack/react-table";
import { Link } from "react-router-dom";
import type { PlayerRow } from "../../api-client/players";
import {
  formatEuroAbbreviated,
  formatNullable,
  formatPercent,
  formatProbability,
} from "../../lib/format";
import { nullsLastComparator, withIdTieBreak } from "../../lib/sorting";
import { StarButton } from "../WatchlistToggle";
import PosBadge from "../ui/PosBadge";

/**
 * The actual row order applied to the table is computed by `PlayerTable.tsx`
 * (which pre-sorts `data` with `nullsLastComparator`/`withIdTieBreak` and
 * passes `manualSorting: true`) rather than by the `sortFn` below — see
 * `web/src/lib/sorting.ts` for why: TanStack v9 auto-inverts a column's
 * `sortFn` result when sorted descending, which is correct for a plain
 * ascending comparison but wrong for "nulls always last" / "ties always
 * break ascending by id", both of which must stay identical regardless of
 * direction. Each sortable column still declares its own `sortFn` using the
 * shared comparators below — the single source of truth for this column's
 * sort semantics, kept in sync with the pre-sort PlayerTable.tsx applies.
 */
export const features = tableFeatures({
  columnVisibilityFeature,
  rowSortingFeature,
  columnFilteringFeature,
  sortedRowModel: createSortedRowModel(),
  filteredRowModel: createFilteredRowModel(),
});

type PlayerColumnDef = ColumnDef<typeof features, PlayerRow>;
type PlayerRowLike = Row<typeof features, PlayerRow>;

const POSITION_ORDER: PlayerRow["position"][] = ["POR", "DEF", "MED", "DEL"];

const AVAILABILITY_BADGE_CLASS: Record<string, string> = {
  available: "bg-[color:var(--color-accent)]/10 text-[color:var(--color-accent)]",
  injured: "bg-[color:var(--color-destructive)]/10 text-[color:var(--color-destructive)]",
  doubtful: "bg-[color:var(--color-warning)]/10 text-[color:var(--color-warning)]",
  suspended: "bg-[color:var(--color-neutral)]/10 muted",
};

function multiSelectFilter(row: PlayerRowLike, columnId: string, filterValue: string[]): boolean {
  if (!filterValue || filterValue.length === 0) return true;
  return filterValue.includes(String(row.getValue(columnId)));
}

/** Keeps rows at or below `filterValue`. An absent or non-numeric filter
 * value imposes no constraint — an empty price box means "no ceiling",
 * never "ceiling of zero". Separately, once a filter value IS active, a row
 * whose own price is `null` is excluded rather than kept: `marketValue`,
 * `idealBid` and `maxBid` are all `number | null` on `PlayerRow`, and a
 * player with an unknown price cannot be shown to be within budget, so an
 * active ceiling must not let them silently through. */
export function maxPriceFilter(row: PlayerRowLike, columnId: string, filterValue: unknown): boolean {
  if (typeof filterValue !== "number" || Number.isNaN(filterValue)) return true;
  const value = row.getValue(columnId);
  return typeof value === "number" && value <= filterValue;
}

function truncatedCell(value: string, maxWidthClass: string) {
  return (
    <span className={`block truncate ${maxWidthClass}`} title={value}>
      {value}
    </span>
  );
}

/** ANALYTICS-06/07. Sortable through the same nulls-last pre-sort as every
 * other numeric column; a null reads "—" (not enough data), never 0. */
function scoreColumn(
  id: "powerScore" | "economyScore",
  header: string,
  title: string,
): PlayerColumnDef {
  return {
    id,
    accessorFn: (row: PlayerRow) => row[id] ?? null,
    header,
    sortFn: (rowA: PlayerRowLike, rowB: PlayerRowLike) =>
      withIdTieBreak<PlayerRow>((a, b) => nullsLastComparator(a[id] ?? null, b[id] ?? null, false))(
        rowA.original,
        rowB.original,
      ),
    cell: ({ row }) => (
      <span className="tabular block text-right" title={title}>
        {formatNullable(row.original[id] ?? null, (v) => Math.round(v).toString())}
      </span>
    ),
  };
}

/** MODEL-02. One decimal, because xP is an expected value in points, not a
 * 0–100 score; the basis rides along in the tooltip. */
const expectedPointsColumn: PlayerColumnDef = {
  id: "expectedPoints",
  accessorFn: (row: PlayerRow) => row.expectedPoints ?? null,
  header: "xP",
  sortFn: (rowA: PlayerRowLike, rowB: PlayerRowLike) =>
    withIdTieBreak<PlayerRow>((a, b) =>
      nullsLastComparator(a.expectedPoints ?? null, b.expectedPoints ?? null, false),
    )(rowA.original, rowB.original),
  cell: ({ row }) => (
    <span
      className="tabular block text-right"
      title={`Expected points next jornada — basis: ${row.original.expectedPointsBasis ?? "none yet"}`}
    >
      {formatNullable(row.original.expectedPoints ?? null, (v) => v.toFixed(1))}
    </span>
  ),
};

export interface SquadColumnOptions {
  onAdd: (player: PlayerRow) => void;
  isInSquad: (playerId: number) => boolean;
  squadFull: boolean;
}

/** DETAIL-04. Callbacks rather than the query itself, so the cell stays
 * presentational and the one `useWatchlist` subscription lives in the page. */
export interface WatchlistColumnOptions {
  isWatched: (playerId: number) => boolean;
  onToggle: (player: PlayerRow) => void;
  pending?: boolean;
}

/** Trailing, beside the squad action, rather than leading: both are row
 * actions, and the name staying the first cell keeps it the row's anchor. */
function watchColumn(options: WatchlistColumnOptions): PlayerColumnDef {
  return {
    id: "watchlist",
    header: "Watch",
    enableSorting: false,
    cell: ({ row }) => (
      <StarButton
        watched={options.isWatched(row.original.playerId)}
        playerName={row.original.name}
        disabled={options.pending}
        onClick={() => options.onToggle(row.original)}
      />
    ),
  };
}

const baseColumns: PlayerColumnDef[] = [
  {
    id: "name",
    accessorKey: "name",
    header: "Player",
    cell: ({ row }) => (
      <Link
        to={`/players/${row.original.playerId}`}
        title={row.original.name}
        className="link block max-w-[180px] truncate font-semibold"
      >
        {row.original.name}
      </Link>
    ),
  },
  {
    id: "team",
    accessorKey: "team",
    header: "Team",
    filterFn: multiSelectFilter,
    cell: ({ row }) => truncatedCell(row.original.team, "max-w-[140px]"),
  },
  {
    id: "position",
    accessorKey: "position",
    header: "Position",
    filterFn: multiSelectFilter,
    cell: ({ row }) => (
<PosBadge position={row.original.position} />
    ),
  },
  {
    id: "marketValue",
    accessorKey: "marketValue",
    header: "Market value",
    filterFn: maxPriceFilter,
    sortFn: (rowA: PlayerRowLike, rowB: PlayerRowLike) =>
      withIdTieBreak<PlayerRow>((a, b) => nullsLastComparator(a.marketValue, b.marketValue, false))(
        rowA.original,
        rowB.original,
      ),
    cell: ({ row }) => (
      <span className="tabular block text-right">{formatEuroAbbreviated(row.original.marketValue)}</span>
    ),
  },
  {
    id: "idealBid",
    accessorKey: "idealBid",
    header: "Ideal bid",
    filterFn: maxPriceFilter,
    sortFn: (rowA: PlayerRowLike, rowB: PlayerRowLike) =>
      withIdTieBreak<PlayerRow>((a, b) => nullsLastComparator(a.idealBid, b.idealBid, false))(
        rowA.original,
        rowB.original,
      ),
    cell: ({ row }) => (
      <span className="tabular block text-right">
        {formatNullable(row.original.idealBid, (v) => formatEuroAbbreviated(v))}
      </span>
    ),
  },
  {
    id: "maxBid",
    accessorKey: "maxBid",
    header: "Max bid",
    filterFn: maxPriceFilter,
    sortFn: (rowA: PlayerRowLike, rowB: PlayerRowLike) =>
      withIdTieBreak<PlayerRow>((a, b) => nullsLastComparator(a.maxBid, b.maxBid, false))(
        rowA.original,
        rowB.original,
      ),
    cell: ({ row }) => (
      <span className="tabular block text-right">
        {formatNullable(row.original.maxBid, (v) => formatEuroAbbreviated(v))}
      </span>
    ),
  },
  {
    id: "priceChangeAbs",
    accessorKey: "priceChangeAbs",
    header: "Price change (€)",
    sortFn: (rowA: PlayerRowLike, rowB: PlayerRowLike) =>
      withIdTieBreak<PlayerRow>((a, b) =>
        nullsLastComparator(a.priceChangeAbs, b.priceChangeAbs, false),
      )(rowA.original, rowB.original),
    cell: ({ row }) => (
      <span className="tabular block text-right">
        {formatNullable(row.original.priceChangeAbs, (v) => formatEuroAbbreviated(v))}
      </span>
    ),
  },
  {
    id: "priceChangePct",
    accessorKey: "priceChangePct",
    header: "Price change (%)",
    sortFn: (rowA: PlayerRowLike, rowB: PlayerRowLike) =>
      withIdTieBreak<PlayerRow>((a, b) =>
        nullsLastComparator(a.priceChangePct, b.priceChangePct, false),
      )(rowA.original, rowB.original),
    cell: ({ row }) => (
      <span className="tabular block text-right">{formatPercent(row.original.priceChangePct)}</span>
    ),
  },
  {
    id: "points",
    accessorKey: "points",
    header: "Points",
    sortFn: (rowA: PlayerRowLike, rowB: PlayerRowLike) =>
      withIdTieBreak<PlayerRow>((a, b) => nullsLastComparator(a.points, b.points, false))(
        rowA.original,
        rowB.original,
      ),
    cell: ({ row }) => <span className="tabular block text-right">{row.original.points}</span>,
  },
  {
    id: "pricePerPoint",
    accessorKey: "pricePerPoint",
    header: "€ / point",
    sortFn: (rowA: PlayerRowLike, rowB: PlayerRowLike) =>
      withIdTieBreak<PlayerRow>((a, b) =>
        nullsLastComparator(a.pricePerPoint, b.pricePerPoint, false),
      )(rowA.original, rowB.original),
    cell: ({ row }) => (
      <span className="tabular block text-right">
        {formatNullable(row.original.pricePerPoint, (v) => formatEuroAbbreviated(v))}
      </span>
    ),
  },
  scoreColumn(
    "powerScore",
    "Power",
    "Power Score (0–100): expected points per match — this season's rate shrunk toward " +
      "last season, calibrated per position, × availability",
  ),
  scoreColumn(
    "economyScore",
    "Economy",
    "Economy Score (0–100): how far below what his Power usually costs the player is priced",
  ),
  expectedPointsColumn,
  {
    id: "starterProbability",
    accessorKey: "starterProbability",
    header: "Starter %",
    sortFn: (rowA: PlayerRowLike, rowB: PlayerRowLike) =>
      withIdTieBreak<PlayerRow>((a, b) =>
        nullsLastComparator(a.starterProbability, b.starterProbability, false),
      )(rowA.original, rowB.original),
    cell: ({ row }) => (
      <span className="tabular block text-right">
        {formatProbability(row.original.starterProbability)}
      </span>
    ),
  },
  {
    id: "availabilityStatus",
    accessorKey: "availabilityStatus",
    header: "Availability",
    filterFn: multiSelectFilter,
    cell: ({ row }) => (
      <span
        className={`badge capitalize ${
          AVAILABILITY_BADGE_CLASS[row.original.availabilityStatus] ?? ""
        }`}
      >
        {row.original.availabilityStatus}
      </span>
    ),
  },
  {
    id: "nextOpponent",
    accessorKey: "nextOpponent",
    header: "Next opponent",
    cell: ({ row }) =>
      row.original.nextOpponent === null
        ? "—"
        : truncatedCell(row.original.nextOpponent, "max-w-[120px]"),
  },
];

/**
 * Spec D-01: adding works from the browser table as well as the squad page —
 * deciding happens while filtering and sorting, so the action belongs on the
 * row rather than behind a context switch.
 *
 * The disabled state (owned / squad full) is pure affordance, built from
 * scalars the server already computed (`memberPlayerIds`, `squadSize`).
 * Affordability is the price filter's job now, not the table's — it needs no
 * cash figure to filter by market value, so this button no longer checks
 * one either. No rule is re-implemented client-side; the authoritative
 * refusal, with its remedy, always comes back from POST /api/squad/players.
 */
export function createPlayerColumns(
  options?: SquadColumnOptions,
  watchlist?: WatchlistColumnOptions,
): PlayerColumnDef[] {
  const withWatch = watchlist ? [...baseColumns, watchColumn(watchlist)] : baseColumns;
  if (!options) return withWatch;

  const actionColumn: PlayerColumnDef = {
    id: "squadAction",
    header: "Squad",
    cell: ({ row }) => {
      const player = row.original;
      const owned = options.isInSquad(player.playerId);
      const blocked = owned || options.squadFull;
      const title = owned
        ? "Already in your squad"
        : options.squadFull
          ? "Squad is full"
          : `Add ${player.name} to your squad`;

      return (
        <button
          type="button"
          disabled={blocked}
          title={title}
          onClick={() => options.onAdd(player)}
          className={`btn btn-sm ${owned ? "btn-ghost" : "btn-secondary text-[color:var(--color-accent)]"}`}
        >
          {owned ? "In squad" : "Add"}
        </button>
      );
    },
  };

  return [...withWatch, actionColumn];
}

export { POSITION_ORDER };
