import { useQuery } from "@tanstack/react-query";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { fetchPlayerDetail, PlayerNotFoundError } from "../api-client/player-detail";
import EmptyState from "../components/EmptyState";
import ExpectedPointsLine from "../components/player-detail/ExpectedPointsLine";
import PlayerAnalyticsPanel from "../components/player-detail/PlayerAnalyticsPanel";
import PointsPerJornadaChart from "../components/player-detail/PointsPerJornadaChart";
import SeasonStatsTable from "../components/player-detail/SeasonStatsTable";
import ValueHistoryChart from "../components/player-detail/ValueHistoryChart";
import VerdictStrip from "../components/player-detail/VerdictStrip";
import WatchlistToggle from "../components/WatchlistToggle";
import PosBadge from "../components/ui/PosBadge";
import OurBidCard from "../components/transfers/OurBidCard";

export default function PlayerDetail() {
  const { playerId } = useParams();
  const id = Number(playerId);
  const location = useLocation();
  const navigate = useNavigate();

  // The browser's own back button already restores the browser list exactly
  // as it was left, because its filter/sort state lives in the URL and the
  // browser history entry still carries it. This page's own "back" link
  // must agree with that rather than push a fresh `/` entry that drops it —
  // `location.key === "default"` is how React Router marks the very first
  // entry in the history stack (true for both a pasted link and the first
  // page of a fresh session), so there is nothing to pop back to; anywhere
  // else, popping one entry lands exactly where the click-through started.
  function goBack() {
    if (location.key === "default") navigate("/");
    else navigate(-1);
  }

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["player-detail", id],
    queryFn: () => fetchPlayerDetail(id),
    enabled: Number.isFinite(id),
    retry: false,
  });

  if (isLoading) {
    return <p className="state-note py-lg">Loading player…</p>;
  }

  if (error instanceof PlayerNotFoundError) {
    return (
      <EmptyState
        heading="Player not found"
        body="There's no player with that id. It may have been removed from the market since you last opened this link."
        action={
          <button
            type="button"
            onClick={goBack}
            className="btn btn-secondary"
          >
            Back to the player browser
          </button>
        }
      />
    );
  }

  if (isError || !data) {
    return (
      <EmptyState
        heading="Couldn't load this player"
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

  const { player } = data;

  return (
    <div className="flex flex-col gap-lg">
      <header className="flex flex-col gap-xs border-b border-line pb-md">
        <button type="button" onClick={goBack} className="link w-fit text-sm">
          ← Back to the player browser
        </button>
        <div className="flex items-center gap-sm">
          <h1 className="page-title">{player.name}</h1>
          <WatchlistToggle playerId={player.playerId} playerName={player.name} />
        </div>
        <p className="flex flex-wrap items-center gap-x-sm gap-y-xs text-sm">
          <PosBadge position={player.position} />
          <span className="font-semibold">{player.team}</span>
          <span aria-hidden="true" className="muted">
            ·
          </span>
          <Link to={`/compare?a=${player.playerId}`} className="link font-semibold">
            Compare with another player
          </Link>
        </p>
      </header>

      <VerdictStrip latest={data.latest} squad={data.squad} predictions={data.predictions} />
      <OurBidCard playerId={player.playerId} />

      <div className="grid gap-md xl:grid-cols-2">
        <div className="panel min-w-0 p-md">
          <ValueHistoryChart points={data.valueHistory} width={640} height={240} />
        </div>
        <div className="panel min-w-0 p-md">
          <PointsPerJornadaChart
            rows={data.gameweekPoints}
            seasonWeekRanges={data.seasonWeekRanges}
            width={640}
            height={240}
          />
        </div>
      </div>

      <div className="grid items-start gap-lg xl:grid-cols-2">
        <section className="flex min-w-0 flex-col gap-sm" aria-labelledby="season-stats-heading">
          <h2 id="season-stats-heading" className="section-title">
            Season statistics
          </h2>
          <SeasonStatsTable seasons={data.seasonStats} />
        </section>
        <div className="flex min-w-0 flex-col gap-lg">
          <ExpectedPointsLine playerId={player.playerId} />
          <PlayerAnalyticsPanel playerId={player.playerId} />
        </div>
      </div>
    </div>
  );
}
