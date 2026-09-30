import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import PosBadge from "../ui/PosBadge";
import { fetchStreaks } from "../../api-client/stats";

const WINDOW_PRESETS = [3, 5, 8, 10];

interface StreaksTabProps {
  season: number;
  maxWeek: number;
}

export default function StreaksTab({ season, maxWeek }: StreaksTabProps) {
  const [searchParams, setSearchParams] = useSearchParams();

  const windowSize = useMemo(() => {
    const fromUrl = Number(searchParams.get("window"));
    return WINDOW_PRESETS.includes(fromUrl) ? fromUrl : 5;
  }, [searchParams]);

  function setWindowSize(next: number) {
    const params = new URLSearchParams(searchParams);
    params.set("window", String(next));
    setSearchParams(params, { replace: true });
  }

  const { data, isLoading, isError } = useQuery({
    queryKey: ["stats-streaks", season, maxWeek, windowSize],
    queryFn: () => fetchStreaks(season, maxWeek, windowSize),
  });

  return (
    <div className="flex flex-col gap-lg">
      <label className="flex items-center gap-sm text-sm font-semibold muted">
        Window
        <select
          value={windowSize}
          onChange={(e) => setWindowSize(Number(e.target.value))}
          className="field"
        >
          {WINDOW_PRESETS.map((w) => (
            <option key={w} value={w}>
              Last {w}
            </option>
          ))}
        </select>
      </label>

      {isLoading && <p className="state-note">Loading…</p>}
      {isError && <p className="state-error">Couldn't load streaks.</p>}

      {data && data.players.length === 0 && (
        <p className="state-note">No streak data recorded yet.</p>
      )}

      {data && data.players.length > 0 && (
        <div className="table-scroll">
          <table className="data-table">
            <caption className="sr-only">
              Points over the last {data.window} jornadas, ending J{data.endWeek}
            </caption>
            <thead>
              <tr>
                <th scope="col" className="num">Rank</th>
                <th scope="col">Player</th>
                <th scope="col">Team</th>
                <th scope="col">Position</th>
                <th scope="col" className="num">Points</th>
              </tr>
            </thead>
            <tbody>
              {data.players.map((p, index) => (
                <tr key={p.playerId}>
                  <td className="num">{index + 1}</td>
                  <td>{p.name}</td>
                  <td>{p.team}</td>
                  <td><PosBadge position={p.position} /></td>
                  <td className="num">
                    {p.totalPoints}
                    {p.weeksCounted < data.window && (
                      <span className="ml-xs text-xs muted">
                        ({p.weeksCounted}/{data.window})
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
