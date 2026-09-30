import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import PosBadge from "../ui/PosBadge";
import { fetchLeaderboard } from "../../api-client/stats";
import { fetchPlayers } from "../../api-client/players";
import { STAT_OPTIONS, statLabel } from "../../lib/statFields";

const POSITIONS = ["POR", "DEF", "MED", "DEL"];

interface LeaderboardTabProps {
  season: number;
}

export default function LeaderboardTab({ season }: LeaderboardTabProps) {
  const [searchParams, setSearchParams] = useSearchParams();

  const stat = searchParams.get("stat") ?? STAT_OPTIONS[0].field;
  const position = searchParams.get("position");
  const team = searchParams.get("team");

  function setParam(key: string, value: string | null) {
    const params = new URLSearchParams(searchParams);
    if (value === null || value === "") params.delete(key);
    else params.set(key, value);
    setSearchParams(params, { replace: true });
  }

  const { data, isLoading, isError } = useQuery({
    queryKey: ["stats-leaderboard", season, stat, position, team],
    queryFn: () => fetchLeaderboard(season, stat, position, team),
  });

  // Team options come from the full roster, not this tab's own (already
  // filtered) result set — deriving them from `data.players` would shrink
  // the dropdown to one entry the moment a team filter is applied.
  const { data: rosterData } = useQuery({ queryKey: ["players"], queryFn: fetchPlayers });
  const teams = useMemo(
    () => Array.from(new Set((rosterData?.players ?? []).map((p) => p.team))).sort(),
    [rosterData],
  );

  return (
    <div className="flex flex-col gap-lg">
      <div className="flex flex-wrap gap-md">
        <label className="flex items-center gap-sm text-sm font-semibold muted">
          Statistic
          <select
            value={stat}
            onChange={(e) => setParam("stat", e.target.value)}
            className="field"
          >
            {STAT_OPTIONS.map((opt) => (
              <option key={opt.field} value={opt.field}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-sm text-sm font-semibold muted">
          Position
          <select
            value={position ?? ""}
            onChange={(e) => setParam("position", e.target.value || null)}
            className="field"
          >
            <option value="">All</option>
            {POSITIONS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-sm text-sm font-semibold muted">
          Team
          <select
            value={team ?? ""}
            onChange={(e) => setParam("team", e.target.value || null)}
            className="field"
          >
            <option value="">All</option>
            {teams.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
      </div>

      {isLoading && <p className="state-note">Loading…</p>}
      {isError && <p className="state-error">Couldn't load the leaderboard.</p>}

      {data && data.players.length === 0 && (
        <p className="state-note">
          No players match this statistic and these filters.
        </p>
      )}

      {data && data.players.length > 0 && (
        <div className="table-scroll">
          <table className="data-table">
            <caption className="sr-only">Season leaderboard for {statLabel(stat)}</caption>
            <thead>
              <tr>
                <th scope="col" className="num">Rank</th>
                <th scope="col">Player</th>
                <th scope="col">Team</th>
                <th scope="col">Position</th>
                <th scope="col" className="num">{statLabel(stat)}</th>
                <th scope="col" className="num">Total points</th>
              </tr>
            </thead>
            <tbody>
              {data.players.map((p, index) => (
                <tr key={p.playerId}>
                  <td className="num">{index + 1}</td>
                  <td>{p.name}</td>
                  <td>{p.team}</td>
                  <td><PosBadge position={p.position} /></td>
                  <td className="num">{p.value}</td>
                  <td className="num">{p.totalPoints}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
