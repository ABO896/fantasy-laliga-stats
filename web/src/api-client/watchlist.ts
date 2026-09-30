import { apiFetch } from "./client";

/** DETAIL-04. Membership as one id list, oldest-added first — never a flag
 * threaded through the player payloads, so a star click refetches nothing
 * but this. Every write returns the whole new list. */
export interface WatchlistResponse {
  playerIds: number[];
}

export function fetchWatchlist(): Promise<WatchlistResponse> {
  return apiFetch<WatchlistResponse>("/watchlist");
}

export function addToWatchlist(playerId: number): Promise<WatchlistResponse> {
  return apiFetch<WatchlistResponse>(`/watchlist/${playerId}`, { method: "PUT" });
}

export function removeFromWatchlist(playerId: number): Promise<WatchlistResponse> {
  return apiFetch<WatchlistResponse>(`/watchlist/${playerId}`, { method: "DELETE" });
}
