import { useMemo, useState, type ReactNode } from "react";
import {
  useTable,
  type ColumnFiltersState,
  type ColumnVisibilityState,
  type OnChangeFn,
  type SortingState,
} from "@tanstack/react-table";
import type { PlayerRow } from "../../api-client/players";
import { VERDICT_LABELS } from "../../api-client/verdict";
import {
  createPlayerColumns,
  features,
  type SquadColumnOptions,
  type WatchlistColumnOptions,
} from "./columns";
import { nullsLastComparator, withIdTieBreak } from "../../lib/sorting";
import ColumnVisibilityToggle from "./ColumnVisibilityToggle";

/** Accessors for every column whose sort must go through the shared
 * nulls-last/id-tie-break comparators. See columns.tsx's file-level comment
 * for why the actual applied order comes from pre-sorting `data` here
 * rather than from TanStack's own per-column descending inversion. */
const SORT_ACCESSORS: Record<string, (p: PlayerRow) => number | null> = {
  marketValue: (p) => p.marketValue,
  idealBid: (p) => p.idealBid,
  maxBid: (p) => p.maxBid,
  priceChangeAbs: (p) => p.priceChangeAbs,
  priceChangePct: (p) => p.priceChangePct,
  points: (p) => p.points,
  pricePerPoint: (p) => p.pricePerPoint,
  starterProbability: (p) => p.starterProbability,
  powerScore: (p) => p.powerScore ?? null,
  expectedPoints: (p) => p.expectedPoints ?? null,
  // Task 7. "Plays" sorts by its underlying pStart, not the class string —
  // see columns.tsx's reliabilityClassColumn, which declares the matching
  // sortFn for header-click sorting.
  pointsValuePct: (p) => p.pointsValuePct ?? null,
  reliabilityClass: (p) => p.pStart ?? null,
  outlookPct: (p) => p.outlookPct ?? null,
  // Plan C Task 6. Sorts by LABELS priority order, not alphabetically —
  // see columns.tsx's verdictColumn, which declares the matching sortFn
  // for header-click sorting.
  verdict: (p) => {
    if (!p.verdict) return null;
    const idx = VERDICT_LABELS.indexOf(p.verdict.label);
    return idx === -1 ? null : idx;
  },
};

/** Columns whose header and cells right-align on tabular figures. */
const NUMERIC_COLUMNS = new Set([...Object.keys(SORT_ACCESSORS)]);

function sortPlayers(players: PlayerRow[], sorting: SortingState): PlayerRow[] {
  if (sorting.length === 0) return players;
  const { id, desc } = sorting[0]!;
  const accessor = SORT_ACCESSORS[id];
  if (!accessor) return players;
  return [...players].sort(
    withIdTieBreak<PlayerRow>((a, b) => {
      const primary = nullsLastComparator(accessor(a), accessor(b), desc);
      if (primary !== 0) return primary;
      // BROWSE-04. Ties fall back to market value, descending, before the id
      // tie-break gets a say. Pre-season this is what keeps the default view
      // meaningful: every player has zero points, so every efficiency is
      // null, every primary comparison ties, and ordering by player id would
      // present 351 players in an order that means nothing. It matters after
      // that too — "0 points" and "same efficiency" are both common ties, and
      // the dearer player is the more interesting one either way.
      return nullsLastComparator(a.marketValue, b.marketValue, true);
    }),
  );
}

interface PlayerTableProps {
  players: PlayerRow[];
  columnFilters: ColumnFiltersState;
  emptyState?: ReactNode;
  squadActions?: SquadColumnOptions;
  /** DETAIL-04 star column. Omitted while the watchlist is unknown. */
  watchlistActions?: WatchlistColumnOptions;
  /** A column id to force visible, without overwriting the owner's own
   * visibility toggles — deselecting it returns the column to whatever they
   * had set. Used by the budget filter's basis selector so the owner can
   * always see the number being filtered against. */
  revealColumn?: string;
  /** Optional controlled sort state — omit both to keep today's internal
   * uncontrolled default (used by this table's own tests). When the owner
   * passes both, they own the sort; `PlayerTable` still applies it through
   * the same `sortPlayers`/`manualSorting` contract either way. */
  sorting?: SortingState;
  onSortingChange?: (next: SortingState) => void;
}

export default function PlayerTable({
  players,
  columnFilters,
  emptyState,
  squadActions,
  watchlistActions,
  revealColumn,
  sorting: controlledSorting,
  onSortingChange,
}: PlayerTableProps) {
  // Default sort is price/point efficiency, ascending — lower is better, so
  // this leads with the best-value players first. Supersedes D-05/BROWSE-04's
  // originally recorded descending default; see the 2026-08-21 change-log
  // entry in docs/superpowers/ROADMAP.md for why.
  const [internalSorting, setInternalSorting] = useState<SortingState>([
    { id: "pricePerPoint", desc: false },
  ]);
  const sorting = controlledSorting ?? internalSorting;
  // TanStack always drives header-click sorting through a functional updater
  // (`(old) => new`, see column_toggleSorting), never a plain next value —
  // so a caller-supplied `onSortingChange(next: SortingState)` can't be
  // handed the updater directly. Resolve it against the current `sorting`
  // here, once, and hand every consumer (internal state or the controlling
  // owner) a concrete next value.
  const handleSortingChange: OnChangeFn<SortingState> = (updaterOrValue) => {
    const next =
      typeof updaterOrValue === "function" ? updaterOrValue(sorting) : updaterOrValue;
    if (onSortingChange) onSortingChange(next);
    else setInternalSorting(next);
  };
  // D-06: price trend, starter probability and availability start hidden;
  // next opponent is not one of the six D-06 essentials either. Ideal bid
  // and max bid start hidden too — Task 7's filter basis selector reveals
  // whichever one it names, so the default view doesn't grow just because
  // these are now renderable.
  const [columnVisibility, setColumnVisibility] = useState<ColumnVisibilityState>({
    idealBid: false,
    maxBid: false,
    priceChangeAbs: false,
    priceChangePct: false,
    starterProbability: false,
    availabilityStatus: false,
    nextOpponent: false,
  });

  const sortedData = useMemo(() => sortPlayers(players, sorting), [players, sorting]);
  const columns = useMemo(
    () => createPlayerColumns(squadActions, watchlistActions),
    [squadActions, watchlistActions],
  );

  const effectiveVisibility = useMemo(
    () => (revealColumn ? { ...columnVisibility, [revealColumn]: true } : columnVisibility),
    [columnVisibility, revealColumn],
  );

  const table = useTable({
    features,
    columns,
    data: sortedData,
    manualSorting: true,
    state: { sorting, columnVisibility: effectiveVisibility, columnFilters },
    onSortingChange: handleSortingChange,
    onColumnVisibilityChange: setColumnVisibility,
    onColumnFiltersChange: () => {
      /* columnFilters is owned by PlayerBrowser's FilterSidebar, not the table */
    },
    getRowId: (row) => String(row.playerId),
  });

  const rows = table.getRowModel().rows;
  const visibleColumnCount = table.getVisibleLeafColumns().length;

  return (
    <div className="min-w-0 flex-1">
      <div className="flex items-center justify-between gap-sm pb-sm">
        <p className="state-note">
          <span className="tabular font-semibold text-ink">{rows.length}</span>{" "}
          {rows.length === 1 ? "player" : "players"} shown
        </p>
        <ColumnVisibilityToggle table={table} forcedVisibleColumn={revealColumn} />
      </div>
      <div
        className="table-scroll overflow-x-auto lg:max-h-[calc(100vh-190px)] lg:overflow-y-auto"
        data-testid="player-table-scroll"
      >
        <table className="data-table">
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  const sortDirection = header.column.getIsSorted();
                  const numeric = NUMERIC_COLUMNS.has(header.column.id);
                  return (
                    <th
                      key={header.id}
                      className={`sticky top-0 z-[1] cursor-pointer select-none hover:text-ink ${
                        numeric ? "num" : ""
                      } ${sortDirection ? "text-ink" : ""}`}
                      onClick={header.column.getToggleSortingHandler()}
                    >
                      <span
                        className={`inline-flex items-center gap-xs ${numeric ? "flex-row-reverse" : ""}`}
                      >
                        <table.FlexRender header={header} />
                        {sortDirection && (
                          <span className="text-[10px] text-[color:var(--color-accent)]" aria-hidden="true">
                            {sortDirection === "desc" ? "▼" : "▲"}
                          </span>
                        )}
                      </span>
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={visibleColumnCount}>{emptyState}</td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.id}>
                  {row.getVisibleCells().map((cell) => (
                    <td
                      key={cell.id}
                      className={NUMERIC_COLUMNS.has(cell.column.id) ? "num" : undefined}
                    >
                      <table.FlexRender cell={cell} />
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
