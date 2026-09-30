import { useQuery } from "@tanstack/react-query";
import { fetchRecords } from "../../api-client/stats";
import { statLabel } from "../../lib/statFields";

interface RecordsTabProps {
  season: number;
}

export default function RecordsTab({ season }: RecordsTabProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["stats-records", season],
    queryFn: () => fetchRecords(season),
  });

  if (isLoading) return <p className="state-note">Loading…</p>;
  if (isError || !data) {
    return <p className="state-error">Couldn't load records.</p>;
  }

  return (
    <div className="flex flex-col gap-lg">
      <section className="flex flex-col gap-sm">
        <h2 className="section-title">
          Best single jornadas
        </h2>
        {data.jornadaRecords.length === 0 ? (
          <p className="state-note">No jornada scores recorded yet.</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <caption className="sr-only">Top single-jornada point performances</caption>
              <thead>
                <tr>
                  <th scope="col" className="num">Rank</th>
                  <th scope="col">Player</th>
                  <th scope="col">Team</th>
                  <th scope="col" className="num">Jornada</th>
                  <th scope="col" className="num">Points</th>
                </tr>
              </thead>
              <tbody>
                {data.jornadaRecords.map((r, index) => (
                  <tr key={`${r.playerId}-${r.week}`} className="border-b border-[color:var(--color-surface-alt)]">
                    <td className="num">{index + 1}</td>
                    <td>{r.name}</td>
                    <td>{r.team}</td>
                    <td className="num">J{r.week}</td>
                    <td className="num font-semibold">{r.points}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="flex flex-col gap-sm">
        <h2 className="section-title">
          Season bests
        </h2>
        {data.seasonRecords.length === 0 ? (
          <p className="state-note">No season records yet.</p>
        ) : (
          <div className="grid grid-cols-2 gap-sm sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
            {data.seasonRecords.map((r) => (
              <div
                key={r.field}
                className="panel flex flex-col gap-[2px] px-md py-sm"
              >
                <span className="text-sm font-semibold muted">
                  {statLabel(r.field)}
                </span>
                <span className="font-[family-name:var(--font-display)] text-[32px] font-bold leading-none tabular-nums">{r.value}</span>
                <span className="text-sm">
                  {r.name} · {r.team}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
