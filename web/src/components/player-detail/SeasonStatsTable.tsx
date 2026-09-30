import { Fragment } from "react";
import type { SeasonStatsRow } from "../../api-client/player-detail";
import { seasonLabel } from "../../lib/seasons";

/** Readable names for the schema's camelCase counters. A key absent here
 * falls back to a spaced-out version of its own name, so a statistic added
 * to `core/season_stats_schema.py` appears immediately — badly labelled
 * rather than missing, which is the right failure of the two. */
export const STAT_LABELS: Record<string, string> = {
  goals: "Goals",
  goalAssist: "Assists",
  offtargetAttAssist: "Off-target assists",
  totalScoringAtt: "Shots",
  penAreaEntries: "Penalty-area entries",
  penaltyWon: "Penalties won",
  penaltySave: "Penalties saved",
  penaltyFailed: "Penalties missed",
  penaltyConceded: "Penalties conceded",
  saves: "Saves",
  effectiveClearance: "Clearances",
  ownGoals: "Own goals",
  goalsConceded: "Goals conceded",
  wonContest: "Dribbles won",
  ballRecovery: "Ball recoveries",
  possLostAll: "Possession lost",
  yellowCard: "Yellow cards",
  secondYellowCard: "Second yellows",
  redCard: "Red cards",
  minsPlayed: "Minutes played",
  marcaPoints: "Marca points",
};

function humanize(key: string): string {
  const spaced = key.replace(/(?!^)([A-Z])/g, " $1").toLowerCase();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** Minus sign, not hyphen — these are numbers, and a hyphen reads as a dash
 * at small sizes. */
function signed(points: number): string {
  if (points < 0) return `−${Math.abs(points)}`;
  return `+${points}`;
}

interface SeasonStatsTableProps {
  seasons: SeasonStatsRow[];
}

export default function SeasonStatsTable({ seasons }: SeasonStatsTableProps) {
  if (seasons.length === 0) {
    return (
      <p className="state-note">
        No season statistics recorded for this player.
      </p>
    );
  }

  // The union across seasons, in the order the first season lists them, so a
  // statistic present in only one season still gets a row.
  const keys = Array.from(new Set(seasons.flatMap((s) => Object.keys(s.stats))));

  return (
    <div className="table-scroll">
      <table className="data-table compact">
        <caption className="sr-only">Season statistics, counter and points contributed</caption>
        <thead>
          <tr>
            <th scope="col">Statistic</th>
            {seasons.map((s) => (
              <th
                key={s.seasonYear}
                scope="col"
                colSpan={2}
               
              >
                {seasonLabel(s.seasonYear)}
              </th>
            ))}
          </tr>
          <tr>
            <th />
            {seasons.map((s) => (
              <Fragment key={s.seasonYear}>
                <th scope="col" className="num">Count</th>
                <th scope="col" className="num">Pts</th>
              </Fragment>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr className="font-semibold">
            <th scope="row">
              Matches · total · average
            </th>
            {seasons.map((s) => (
              <td key={s.seasonYear} colSpan={2} className="num">
                {s.matchesPlayed} · {s.totalPoints} · {s.averagePoints.toFixed(1)}
              </td>
            ))}
          </tr>
          {keys.map((key) => (
            <tr key={key}>
              <th scope="row" className="font-normal">
                {STAT_LABELS[key] ?? humanize(key)}
              </th>
              {seasons.map((s) => {
                const pair = s.stats[key];
                return (
                  <Fragment key={s.seasonYear}>
                    <td className="num">{pair ? pair.count : "—"}</td>
                    <td className="num muted">
                      {pair ? signed(pair.points) : "—"}
                    </td>
                  </Fragment>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
