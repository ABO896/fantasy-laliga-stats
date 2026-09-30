import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchHealth, ScrapeAlreadyRunningError, triggerScrape } from "../api-client/health";
import ScrapeRunList from "../components/ScrapeRunList";
import PageHeader from "../components/ui/PageHeader";

/** Scrape Health page (D-01): the last successful refresh, its row count,
 * the ten most recent runs with their outcomes, and an always-available
 * manual "Refresh now" trigger. Polls `GET /api/health` while the newest
 * run is `running` (RESEARCH.md Pattern 3), so a scrape kicked off from
 * here or from the stale-data banner — the only two ways a scrape starts
 * from the app since Phase 13 removed the scheduled agent — is reflected
 * without a manual reload. */
export default function HealthPage() {
  const queryClient = useQueryClient();
  const [triggerError, setTriggerError] = useState<string | null>(null);
  const [isTriggering, setIsTriggering] = useState(false);

  const { data } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: (query) => (query.state.data?.recentRuns[0]?.status === "running" ? 1000 : false),
  });

  const newestIsRunning = data?.recentRuns[0]?.status === "running";
  const isRefreshing = isTriggering || newestIsRunning;

  async function handleRefreshNow() {
    setTriggerError(null);
    setIsTriggering(true);
    try {
      await triggerScrape();
      await queryClient.invalidateQueries({ queryKey: ["health"] });
    } catch (error) {
      setTriggerError(
        error instanceof ScrapeAlreadyRunningError
          ? "A scrape is already in progress."
          : "Couldn't start the refresh. Try again.",
      );
    } finally {
      setIsTriggering(false);
    }
  }

  const lastSuccessfulRun = data?.lastSuccessfulRun ?? null;
  const hoursSinceLastSuccess = data?.hoursSinceLastSuccess ?? null;
  const isStale = data?.isStale ?? false;
  const recentRuns = data?.recentRuns ?? [];

  return (
    <div className="flex max-w-[56rem] flex-col gap-lg">
      <PageHeader
        title="Scrape Health"
        subtitle="How fresh the data is, and what the last refreshes did."
      />
      <section className="panel flex flex-wrap items-center justify-between gap-lg px-lg py-md">
        <div className="flex flex-wrap items-baseline gap-x-2xl gap-y-sm">
          <p
            data-testid="health-headline-row-count"
            className="font-[family-name:var(--font-display)] text-[40px] font-bold leading-none tabular-nums"
          >
            {lastSuccessfulRun ? `${lastSuccessfulRun.rowCount} players` : "No data yet"}
          </p>
          <p
            data-testid="health-headline-recency"
            className={`font-[family-name:var(--font-display)] text-[40px] font-bold leading-none tabular-nums ${
              isStale ? "text-[color:var(--color-warning)]" : ""
            }`}
          >
            {hoursSinceLastSuccess !== null ? `${Math.round(hoursSinceLastSuccess)}h ago` : "Never refreshed"}
          </p>
        </div>
        <div>
        <button
          type="button"
          onClick={handleRefreshNow}
          disabled={isRefreshing}
          className="btn btn-primary"
        >
          {isRefreshing ? "Refreshing…" : "Refresh now"}
        </button>
        {triggerError && (
          <p className="state-error mt-xs">{triggerError}</p>
        )}
        </div>
      </section>

      <section className="panel p-lg">
        <h2 className="section-title">Recent Runs</h2>
        {recentRuns.length === 0 ? (
          <p className="mt-md text-sm muted">No scrape runs yet</p>
        ) : (
          <ScrapeRunList runs={recentRuns} />
        )}
      </section>
    </div>
  );
}
