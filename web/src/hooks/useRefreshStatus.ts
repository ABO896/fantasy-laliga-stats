import { useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchHealth } from "../api-client/health";

/** While a refresh is running, how often the health query is re-read. */
const POLL_MS = 1500;

export interface RefreshStatus {
  /** The health query has answered at least once. */
  loaded: boolean;
  /** The newest run is `running` — from its first request to its last
   * model step (the server keeps it `running` until then). */
  running: boolean;
  /** The dataset that run is on, e.g. `player_pages`. */
  currentDataset: string | null;
}

/** The one place the app learns whether a refresh is going. Every refresh
 * control and banner reads this, so they agree, stay disabled for the whole
 * run, and every page reloads its data once — when the run ends. */
export function useRefreshStatus(): RefreshStatus {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    staleTime: 60_000,
    refetchInterval: (query) =>
      query.state.data?.recentRuns[0]?.status === "running" ? POLL_MS : false,
  });

  const newest = data?.recentRuns[0];
  const running = newest?.status === "running";
  const wasRunning = useRef(false);

  useEffect(() => {
    if (wasRunning.current && !running) {
      void queryClient.invalidateQueries();
    }
    wasRunning.current = running;
  }, [running, queryClient]);

  return {
    loaded: data !== undefined,
    running,
    currentDataset: running ? (newest?.currentDataset ?? null) : null,
  };
}
