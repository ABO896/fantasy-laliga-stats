import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { fetchStatsSeasons } from "../api-client/stats";
import EmptyState from "../components/EmptyState";
import PageHeader from "../components/ui/PageHeader";
import ScoresTab from "../components/stats/ScoresTab";
import StreaksTab from "../components/stats/StreaksTab";
import RecordsTab from "../components/stats/RecordsTab";
import LeaderboardTab from "../components/stats/LeaderboardTab";
import MarketModelTab from "../components/stats/MarketModelTab";
import { seasonLabel } from "../lib/seasons";

const TABS = [
  { id: "scores", label: "Scores" },
  { id: "streaks", label: "Streaks" },
  { id: "records", label: "Records" },
  { id: "leaderboards", label: "Leaderboards" },
  // MODEL-01/03/04. A tab, not a page: this is league-wide market
  // information and /stats is already the league-wide surface.
  { id: "market", label: "Market model" },
] as const;
type TabId = (typeof TABS)[number]["id"];

export default function StatsPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["stats-seasons"],
    queryFn: fetchStatsSeasons,
  });

  const requestedTab = searchParams.get("tab");
  const tab: TabId = TABS.some((t) => t.id === requestedTab) ? (requestedTab as TabId) : "scores";

  const seasons = data?.seasons ?? [];
  const season = useMemo(() => {
    const fromUrl = Number(searchParams.get("season"));
    if (seasons.includes(fromUrl)) return fromUrl;
    return seasons[0] ?? null;
  }, [searchParams, seasons]);

  function setTab(nextTab: TabId) {
    const params = new URLSearchParams(searchParams);
    params.set("tab", nextTab);
    setSearchParams(params, { replace: true });
  }

  function setSeason(nextSeason: number) {
    const params = new URLSearchParams(searchParams);
    params.set("season", String(nextSeason));
    setSearchParams(params, { replace: true });
  }

  if (isLoading) {
    return <p className="state-note py-lg">Loading league stats…</p>;
  }

  if (isError || !data) {
    return (
      <EmptyState
        heading="Couldn't load league stats"
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

  // The market model needs no season: it reads snapshots, not jornadas.
  if (tab !== "market" && (seasons.length === 0 || season === null)) {
    return (
      <EmptyState
        heading="No league stats yet"
        body="Run a scrape to populate jornada scores and season statistics — click Refresh now on the Health page to get started."
      />
    );
  }

  const maxWeek = season === null ? 1 : (data.seasonWeekRanges[String(season)] ?? 1);

  return (
    <div className="flex flex-col gap-lg">
      <PageHeader
        title="League stats"
        subtitle="Every jornada, streak and record in the league — and how our market model is doing."
        actions={
          tab !== "market" &&
          season !== null && (
            <label className="flex items-center gap-sm text-sm font-semibold muted">
              Season
              <select
                value={season}
                onChange={(e) => setSeason(Number(e.target.value))}
                className="field"
              >
                {seasons.map((s) => (
                  <option key={s} value={s}>
                    {seasonLabel(s)}
                  </option>
                ))}
              </select>
            </label>
          )
        }
      />
      <div className="max-w-full overflow-x-auto">
        <nav aria-label="League stats sections" className="segmented flex-nowrap">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              aria-pressed={tab === t.id}
              onClick={() => setTab(t.id)}
              className="whitespace-nowrap"
            >
              {t.label}
            </button>
          ))}
        </nav>
      </div>
      {season !== null && tab === "scores" && <ScoresTab season={season} maxWeek={maxWeek} />}
      {season !== null && tab === "streaks" && <StreaksTab season={season} maxWeek={maxWeek} />}
      {season !== null && tab === "records" && <RecordsTab season={season} />}
      {season !== null && tab === "leaderboards" && <LeaderboardTab season={season} />}
      {tab === "market" && <MarketModelTab />}
    </div>
  );
}
