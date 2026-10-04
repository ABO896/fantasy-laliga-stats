import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchHealth } from "../api-client/health";
import RefreshControls from "../components/RefreshControls";
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

  const { data } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: (query) => (query.state.data?.recentRuns[0]?.status === "running" ? 1000 : false),
  });

  const newestIsRunning = data?.recentRuns[0]?.status === "running";

  async function handleTriggered() {
    await queryClient.invalidateQueries({ queryKey: ["health"] });
  }

  const lastSuccessfulRun = data?.lastSuccessfulRun ?? null;
  const lastCompleteRun = data?.lastCompleteRun ?? null;
  const hoursSinceLastSuccess = data?.hoursSinceLastSuccess ?? null;
  const isStale = data?.isStale ?? false;
  const recentRuns = data?.recentRuns ?? [];
  const playerPages = data?.playerPages ?? {
    players: 0,
    complete: 0,
    withGaps: 0,
    withMatchGaps: 0,
    oldestLastDay: null,
  };

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
        <RefreshControls disabled={newestIsRunning} onTriggered={handleTriggered} />
      </section>

      <section className="panel flex flex-wrap items-center justify-between gap-lg px-lg py-md">
        <div>
          <p className="section-title">Last complete refresh</p>
          <p className="state-note">
            {lastCompleteRun
              ? new Date(lastCompleteRun.finishedAt ?? lastCompleteRun.startedAt).toLocaleString()
              : "Never run"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-md">
          <p className="state-note">
            {`${playerPages.complete} of ${playerPages.players} players complete`}
          </p>
          {playerPages.oldestLastDay !== null && (
            <p className="state-note">{`oldest data: ${playerPages.oldestLastDay}`}</p>
          )}
          {playerPages.withMatchGaps > 0 && (
            <p className="state-note">{`${playerPages.withMatchGaps} with missing matches`}</p>
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
