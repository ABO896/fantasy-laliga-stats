import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnFiltersState, SortingState } from "@tanstack/react-table";
import { useSearchParams } from "react-router-dom";
import { fetchPlayers } from "../api-client/players";
import type { PlayerRow } from "../api-client/players";
import { addSquadPlayer, SquadRuleError } from "../api-client/squad";
import AddToSquadDialog from "../components/AddToSquadDialog";
import PlayerTable from "../components/PlayerTable/PlayerTable";
import TableSkeleton from "../components/PlayerTable/TableSkeleton";
import FilterSidebar from "../components/FilterSidebar";
import type { PlayerFilters } from "../components/FilterSidebar";
import EmptyState from "../components/EmptyState";
import PageHeader from "../components/ui/PageHeader";
import { useSquad } from "../components/SquadBar";
import { useWatchlist } from "../components/WatchlistToggle";

/** A malformed `max` (non-numeric, or numeric-looking but non-finite —
 * `?max=abc`, a truncated bookmark, a hand-edited URL) must degrade to "no
 * ceiling", the same as `max` being absent — not to `NaN`. `maxPriceFilter`
 * (columns.tsx) already treats a NaN filter value as "no constraint" at the
 * row level, so a leaked NaN doesn't empty the table — but it still
 * corrupts every other consumer of `PlayerFilters.maxPrice`: FilterSidebar
 * renders a nonsensical "≤ €NaNM" active-filter chip, and the max-price
 * number input's controlled `value` becomes `NaN`. Guarding here keeps NaN
 * out of the state entirely, rather than relying on each consumer to defend
 * against it separately. */
function parseMaxPrice(searchParams: URLSearchParams): number | null {
  if (!searchParams.has("max")) return null;
  const parsed = Number(searchParams.get("max"));
  return Number.isFinite(parsed) ? parsed : null;
}

export default function PlayerBrowser() {
  const [searchParams, setSearchParams] = useSearchParams();

  const filters: PlayerFilters = useMemo(
    () => ({
      positions: searchParams.getAll("pos"),
      teams: searchParams.getAll("team"),
      availability: searchParams.getAll("avail"),
      verdict: searchParams.getAll("verdict"),
      maxPrice: parseMaxPrice(searchParams),
      priceBasis: (searchParams.get("basis") as PlayerFilters["priceBasis"]) ?? "marketValue",
      watchlistOnly: searchParams.get("watch") === "1",
    }),
    [searchParams],
  );

  const sorting: SortingState = useMemo(() => {
    const id = searchParams.get("sort") ?? "pricePerPoint";
    return [{ id, desc: searchParams.get("dir") === "desc" }];
  }, [searchParams]);

  function setFilters(next: PlayerFilters) {
    const params = new URLSearchParams(searchParams);
    params.delete("pos");
    next.positions.forEach((p) => params.append("pos", p));
    params.delete("team");
    next.teams.forEach((t) => params.append("team", t));
    params.delete("avail");
    next.availability.forEach((a) => params.append("avail", a));
    params.delete("verdict");
    next.verdict.forEach((v) => params.append("verdict", v));
    if (next.maxPrice === null) params.delete("max");
    else params.set("max", String(next.maxPrice));
    params.set("basis", next.priceBasis);
    if (next.watchlistOnly) params.set("watch", "1");
    else params.delete("watch");
    setSearchParams(params, { replace: true });
  }

  function setSorting(next: SortingState) {
    const params = new URLSearchParams(searchParams);
    const first = next[0];
    if (!first) {
      params.delete("sort");
      params.delete("dir");
    } else {
      params.set("sort", first.id);
      params.set("dir", first.desc ? "desc" : "asc");
    }
    setSearchParams(params, { replace: true });
  }

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["players"],
    queryFn: fetchPlayers,
  });

  const queryClient = useQueryClient();
  const { data: squad } = useSquad();
  const [pendingPlayer, setPendingPlayer] = useState<PlayerRow | null>(null);
  const [addError, setAddError] = useState<string | null>(null);

  const addMutation = useMutation({
    mutationFn: ({ playerId, price }: { playerId: number; price: number }) =>
      addSquadPlayer(playerId, price),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["squad"] });
      setPendingPlayer(null);
      setAddError(null);
    },
    onError: (error: unknown) => {
      // The server owns the rules, so its sentence is the message shown.
      setAddError(
        error instanceof SquadRuleError ? error.violation.message : "Couldn't add that player.",
      );
    },
  });

  // `undefined` here (squad still loading, or the squad query failed) is the
  // deliberate degraded state: the action column is silently omitted rather
  // than shown half-working, because affording add/afford/full checks
  // without knowing the squad would be wrong. SquadBar is mounted above the
  // outlet on every route and already carries the user-facing "squad
  // unavailable" error for this case — do not add a second error message
  // here, it would just duplicate that one.
  const squadActions = squad
    ? {
        onAdd: (player: PlayerRow) => {
          setAddError(null);
          setPendingPlayer(player);
        },
        isInSquad: (playerId: number) => squad.summary.memberPlayerIds.includes(playerId),
        squadFull: squad.summary.squadSize >= squad.summary.maxSquadSize,
      }
    : undefined;

  // DETAIL-04. `playerIds` is undefined until the watchlist has loaded; the
  // star column and the sidebar filter are both omitted until then.
  const watchlist = useWatchlist();
  const watchlistActions = useMemo(
    () =>
      watchlist.playerIds === undefined
        ? undefined
        : {
            isWatched: (playerId: number) => watchlist.playerIds!.includes(playerId),
            onToggle: (player: PlayerRow) => watchlist.toggle(player.playerId),
            pending: watchlist.pending,
          },
    [watchlist.playerIds, watchlist.toggle, watchlist.pending],
  );

  const columnFilters: ColumnFiltersState = useMemo(() => {
    const next: ColumnFiltersState = [];
    if (filters.positions.length > 0) next.push({ id: "position", value: filters.positions });
    if (filters.teams.length > 0) next.push({ id: "team", value: filters.teams });
    if (filters.availability.length > 0) {
      next.push({ id: "availabilityStatus", value: filters.availability });
    }
    if (filters.verdict.length > 0) next.push({ id: "verdict", value: filters.verdict });
    if (filters.maxPrice !== null) {
      next.push({ id: filters.priceBasis, value: filters.maxPrice });
    }
    return next;
  }, [filters]);

  if (isLoading) {
    return <TableSkeleton />;
  }

  if (isError) {
    return (
      <EmptyState
        heading="Couldn't load player data"
        body="Something went wrong reaching the server. Check the Health page or try again."
        action={
          <button
            type="button"
            onClick={() => refetch()}
            className="btn btn-primary"
          >
            Try again
          </button>
        }
      />
    );
  }

  const players = data?.players ?? [];

  if (players.length === 0) {
    return (
      <EmptyState
        heading="No player data yet"
        body="Run your first scrape to populate the player browser — click Refresh now on the Health page to get started."
      />
    );
  }

  // The watchlist filter narrows the row set before the table sees it: it
  // is a membership test against a separate list, not a property of a row,
  // so it has no column to hang a TanStack filter on. While the watchlist
  // is still unknown the filter is not applied (and not offered).
  const watchedIds = watchlist.playerIds;
  const watchlistFiltering = filters.watchlistOnly === true && watchedIds !== undefined;
  const shownPlayers = watchlistFiltering
    ? players.filter((p) => watchedIds.includes(p.playerId))
    : players;

  return (
    <div className="flex flex-col gap-lg">
      <PageHeader
        title="Players"
        subtitle={`${players.length} players on the market. Sort any column; open a player for his history.`}
      />
      <div className="flex flex-col gap-lg lg:flex-row lg:items-start">
      <FilterSidebar
        value={filters}
        onChange={setFilters}
        players={players}
        watchlistCount={watchedIds?.length}
      />
      <PlayerTable
        players={shownPlayers}
        columnFilters={columnFilters}
        squadActions={squadActions}
        watchlistActions={watchlistActions}
        revealColumn={filters.priceBasis}
        sorting={sorting}
        onSortingChange={setSorting}
        emptyState={
          watchlistFiltering && watchedIds.length === 0 ? (
            <EmptyState
              heading="Your watchlist is empty"
              body="Star a player — from their row here or from their page — to keep an eye on them."
            />
          ) : (
            <EmptyState
              heading="No players match these filters"
              body={
                watchlistFiltering
                  ? "None of your watchlisted players match these filters — try widening them, or turn off Watchlist only."
                  : "Try widening your position, team, availability, or price filters."
              }
            />
          )
        }
      />
      </div>
      {pendingPlayer && (
        <AddToSquadDialog
          player={pendingPlayer}
          error={addError}
          pending={addMutation.isPending}
          onCancel={() => {
            setPendingPlayer(null);
            setAddError(null);
          }}
          onConfirm={(price) =>
            addMutation.mutate({ playerId: pendingPlayer.playerId, price })
          }
        />
      )}
    </div>
  );
}
