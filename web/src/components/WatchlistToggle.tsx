import { useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addToWatchlist,
  fetchWatchlist,
  removeFromWatchlist,
  type WatchlistResponse,
} from "../api-client/watchlist";

const WATCHLIST_KEY = ["watchlist"] as const;

/**
 * DETAIL-04. One query, one cache entry, read by every surface that shows a
 * star — the browser rows, the player page, the compare page — so they can
 * never disagree. `toggle` writes through the server and drops the list it
 * returns straight into the cache; no optimistic guess to roll back.
 */
export function useWatchlist() {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: WATCHLIST_KEY, queryFn: fetchWatchlist });

  const mutation = useMutation({
    mutationFn: ({ playerId, watched }: { playerId: number; watched: boolean }) =>
      watched ? removeFromWatchlist(playerId) : addToWatchlist(playerId),
    onSuccess: (next: WatchlistResponse) => {
      queryClient.setQueryData(WATCHLIST_KEY, next);
    },
  });

  const ids = query.data?.playerIds;
  const { mutate } = mutation;
  // Stable per list, so a memoised consumer (the browser's column set) only
  // rebuilds when membership actually changes.
  const toggle = useCallback(
    (playerId: number) => mutate({ playerId, watched: ids?.includes(playerId) ?? false }),
    [ids, mutate],
  );

  return {
    /** `undefined` until loaded (or when the request failed) — callers omit
     * their star rather than show one that might be wrong. */
    playerIds: ids,
    isWatched: (playerId: number) => ids?.includes(playerId) ?? false,
    toggle,
    pending: mutation.isPending,
  };
}

interface StarButtonProps {
  watched: boolean;
  playerName: string;
  onClick: () => void;
  disabled?: boolean;
}

/** Presentational only, so the browser's table cells can use it without
 * each cell subscribing to the query itself. The accessible name says what
 * a click *will do*; `aria-pressed` says what is true now. */
export function StarButton({ watched, playerName, onClick, disabled }: StarButtonProps) {
  return (
    <button
      type="button"
      aria-pressed={watched}
      aria-label={watched ? `Remove ${playerName} from watchlist` : `Add ${playerName} to watchlist`}
      title={watched ? "On your watchlist" : "Add to watchlist"}
      disabled={disabled}
      onClick={onClick}
      className={`text-lg leading-none transition-colors disabled:opacity-40 ${
        watched
          ? "text-[color:var(--color-card)] [text-shadow:0_0_1px_var(--color-warning)]"
          : "muted hover:text-[color:var(--color-card)]"
      }`}
    >
      {watched ? "★" : "☆"}
    </button>
  );
}

export default function WatchlistToggle({
  playerId,
  playerName,
}: {
  playerId: number;
  playerName: string;
}) {
  const watchlist = useWatchlist();
  if (watchlist.playerIds === undefined) return null;

  return (
    <StarButton
      watched={watchlist.isWatched(playerId)}
      playerName={playerName}
      disabled={watchlist.pending}
      onClick={() => watchlist.toggle(playerId)}
    />
  );
}
