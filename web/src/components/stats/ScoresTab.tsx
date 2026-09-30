import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Tooltip, XAxis, YAxis } from "recharts";
import { fetchJornadaScores } from "../../api-client/stats";
import { formatEuroAbbreviated, formatNullable } from "../../lib/format";
import { useContainerWidth } from "../../lib/useContainerWidth";
import PosBadge from "../ui/PosBadge";

interface ScoresTabProps {
  season: number;
  maxWeek: number;
}

export default function ScoresTab({ season, maxWeek }: ScoresTabProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [chartRef, chartWidth] = useContainerWidth<HTMLElement>(640);

  const week = useMemo(() => {
    const fromUrl = Number(searchParams.get("week"));
    return fromUrl >= 1 && fromUrl <= maxWeek ? fromUrl : maxWeek;
  }, [searchParams, maxWeek]);

  function setWeek(next: number) {
    const params = new URLSearchParams(searchParams);
    params.set("week", String(next));
    setSearchParams(params, { replace: true });
  }

  const { data, isLoading, isError } = useQuery({
    queryKey: ["stats-scores", season, week],
    queryFn: () => fetchJornadaScores(season, week),
  });

  const weekOptions = Array.from({ length: maxWeek }, (_, i) => i + 1);

  return (
    <div className="flex flex-col gap-lg">
      <div className="flex flex-wrap items-center gap-md">
        <label className="flex items-center gap-sm text-sm font-semibold muted">
          Jornada
          <select value={week} onChange={(e) => setWeek(Number(e.target.value))} className="field">
            {weekOptions.map((w) => (
              <option key={w} value={w}>
                J{w}
              </option>
            ))}
          </select>
        </label>
        {data?.isProvisional && (
          <span className="badge bg-[color:var(--color-warning)]/12 text-[color:var(--color-warning)]">
            Provisional
          </span>
        )}
      </div>
      {isLoading && <p className="state-note">Loading…</p>}
      {isError && <p className="state-error">Couldn't load this jornada.</p>}
      {data && data.scores.length === 0 && (
        <p className="state-note">No results recorded for this jornada yet.</p>
      )}
      {data && data.scores.length > 0 && (
        <div className="grid gap-lg xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <section className="flex min-w-0 flex-col gap-sm">
            <h2 className="section-title">Players</h2>
            <div className="table-scroll">
              <table className="data-table">
                <caption className="sr-only">Per-player scores for this jornada</caption>
                <thead>
                  <tr>
                    <th scope="col">Player</th>
                    <th scope="col">Team</th>
                    <th scope="col">Position</th>
                    <th scope="col" className="num">Points</th>
                    <th scope="col" className="num">Market Value</th>
                    <th scope="col" className="num">€/Point</th>
                  </tr>
                </thead>
                <tbody>
                  {data.scores.map((s) => (
                    <tr key={s.playerId}>
                      <td>
                        <Link to={`/players/${s.playerId}`} className="link font-semibold">
                          {s.name}
                        </Link>
                      </td>
                      <td>{s.team}</td>
                      <td>
                        <PosBadge position={s.position} />
                      </td>
                      <td className="num font-semibold">{s.points}</td>
                      <td className="num">{formatNullable(s.marketValue, formatEuroAbbreviated)}</td>
                      <td className="num">{formatNullable(s.pricePerPoint, formatEuroAbbreviated)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <div className="flex min-w-0 flex-col gap-lg">
            <section ref={chartRef} className="panel flex min-w-0 flex-col gap-sm p-md">
              <h2 className="section-title">Score spread</h2>
              {/* Horizontal: layout="vertical" swaps Recharts' axis roles — the
                  category axis (tier label) is the Y axis, the value axis
                  (count) is the X axis. */}
              <BarChart
                width={Math.max(chartWidth - 34, 200)}
                height={220}
                data={data.tiers}
                layout="vertical"
                margin={{ top: 4, right: 12, bottom: 0, left: 0 }}
              >
                <CartesianGrid strokeDasharray="2 4" horizontal={false} />
                <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="label" tick={{ fontSize: 11 }} width={48} />
                <Tooltip />
                <Bar dataKey="count" fill="var(--color-chart-1)" radius={[0, 2, 2, 0]} />
              </BarChart>
            </section>
            <section className="flex min-w-0 flex-col gap-sm">
              <h2 className="section-title">Teams</h2>
              <div className="table-scroll">
                <table className="data-table compact">
                  <caption className="sr-only">Team totals for this jornada</caption>
                  <thead>
                    <tr>
                      <th scope="col">Team</th>
                      <th scope="col" className="num">Total points</th>
                      <th scope="col" className="num">Average</th>
                      <th scope="col" className="num">Players</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.teams.map((t) => (
                      <tr key={t.team}>
                        <td>{t.team}</td>
                        <td className="num font-semibold">{t.totalPoints}</td>
                        <td className="num">{t.averagePoints.toFixed(1)}</td>
                        <td className="num">{t.playerCount}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        </div>
      )}
    </div>
  );
}
