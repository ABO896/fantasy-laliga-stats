import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import {
  fetchPlayerDetail,
  PlayerNotFoundError,
  type PlayerDetailResponse,
} from "../api-client/player-detail";
import { fetchPlayers } from "../api-client/players";
import PointsPerJornadaChart from "../components/player-detail/PointsPerJornadaChart";
import ValueHistoryChart from "../components/player-detail/ValueHistoryChart";
import WatchlistToggle from "../components/WatchlistToggle";
import PageHeader from "../components/ui/PageHeader";
import PosBadge from "../components/ui/PosBadge";
import { buildCompareRows } from "../lib/compare";

type Slot = "a" | "b";

const SLOT_LABEL: Record<Slot, string> = { a: "First player", b: "Second player" };

const CHART_WIDTH = 460;
const CHART_HEIGHT = 220;

/** A malformed id (`?a=abc`, a truncated link) degrades to an empty slot,
 * the same way the browser's `max` param does, rather than a NaN fetch. */
function parseId(raw: string | null): number | null {
  if (raw === null || raw === "") return null;
  const id = Number(raw);
  return Number.isInteger(id) ? id : null;
}

/** Same query key as the player page, so a player just viewed arrives from
 * cache (spec D-05). */
function usePlayerSlot(id: number | null) {
  return useQuery({
    queryKey: ["player-detail", id],
    queryFn: () => fetchPlayerDetail(id!),
    enabled: id !== null,
    retry: false,
  });
}

function SlotHeader({
  id,
  query,
}: {
  id: number | null;
  query: ReturnType<typeof usePlayerSlot>;
}) {
  const muted = "text-sm muted";
  if (id === null) return <p className={muted}>No player chosen.</p>;
  if (query.isLoading) return <p className={muted}>Loading player…</p>;
  if (query.error instanceof PlayerNotFoundError) {
    return (
      <div>
        <p className="text-sm font-semibold">Player not found</p>
        <p className={muted}>There's no player with that id — pick another.</p>
      </div>
    );
  }
  if (query.isError || !query.data) {
    return <p className={muted}>Couldn't load this player. Try again from the Health page.</p>;
  }
  const { player } = query.data;
  return (
    <div>
      <div className="flex items-center gap-sm">
        <Link
          to={`/players/${player.playerId}`}
          className="link font-[family-name:var(--font-display)] text-[24px] font-bold leading-tight"
        >
          {player.name}
        </Link>
        <WatchlistToggle playerId={player.playerId} playerName={player.name} />
      </div>
      <p className="flex items-center gap-sm text-sm">
        <PosBadge position={player.position} />
        <span>{player.team}</span>
      </p>
    </div>
  );
}

/**
 * DETAIL-06. Two players side by side: a key-stats table with the better
 * value marked where "better" is unambiguous, then each player's own
 * market-value and points-per-jornada charts, reused unchanged, stacked in
 * matching columns so the eye compares by row. Selection lives in the URL
 * (`?a=&b=`), like every other page's state, so a comparison is linkable
 * and survives a reload or a back-press.
 */
export default function ComparePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const ids: Record<Slot, number | null> = {
    a: parseId(searchParams.get("a")),
    b: parseId(searchParams.get("b")),
  };

  const queries: Record<Slot, ReturnType<typeof usePlayerSlot>> = {
    a: usePlayerSlot(ids.a),
    b: usePlayerSlot(ids.b),
  };

  const { data: playerList } = useQuery({ queryKey: ["players"], queryFn: fetchPlayers });
  const options = useMemo(
    () =>
      [...(playerList?.players ?? [])].sort(
        (x, y) => x.name.localeCompare(y.name) || x.playerId - y.playerId,
      ),
    [playerList],
  );

  function choose(slot: Slot, value: string) {
    const params = new URLSearchParams(searchParams);
    if (value === "") params.delete(slot);
    else params.set(slot, value);
    setSearchParams(params, { replace: true });
  }

  const loaded: Record<Slot, PlayerDetailResponse | null> = {
    a: ids.a !== null ? (queries.a.data ?? null) : null,
    b: ids.b !== null ? (queries.b.data ?? null) : null,
  };
  const rows = buildCompareRows(loaded.a, loaded.b);
  const anyLoaded = loaded.a !== null || loaded.b !== null;
  const slots: Slot[] = ["a", "b"];

  return (
    <div className="flex flex-col gap-lg">
      <PageHeader
        title="Compare players"
        subtitle={
          (ids.a === null || ids.b === null) &&
          "Pick two players to compare their market value, points and form side by side."
        }
      />

      <div className="grid gap-md sm:grid-cols-2 sm:gap-xl">
        {slots.map((slot) => (
          <div key={slot} className="panel flex min-w-0 flex-col gap-sm p-md">
            <label className="flex flex-col gap-xs field-label">
              {SLOT_LABEL[slot]}
              <select
                value={ids[slot] === null ? "" : String(ids[slot])}
                onChange={(event) => choose(slot, event.target.value)}
                className="field w-full font-normal"
              >
                <option value="">Choose a player…</option>
                {options.map((p) => (
                  <option key={p.playerId} value={String(p.playerId)}>
                    {p.name} · {p.position} · {p.team}
                  </option>
                ))}
              </select>
            </label>
            <SlotHeader id={ids[slot]} query={queries[slot]} />
          </div>
        ))}
      </div>

      {anyLoaded && (
        <>
          <div className="table-scroll">
          <table aria-label="Key stats" className="data-table">
            <thead>
              <tr>
                <th>Stat</th>
                {slots.map((slot) => (
                  <th
                    key={slot}
                    className="num"
                  >
                    {loaded[slot]?.player.name ?? "—"}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.label}>
                  <th scope="row" className="font-normal">
                    {row.label}
                  </th>
                  {slots.map((slot) => {
                    const better = row.better === slot;
                    return (
                      <td
                        key={slot}
                        data-better={better ? "true" : undefined}
                        className={`num capitalize ${
                          better ? "font-semibold text-[color:var(--color-accent)]" : ""
                        }`}
                      >
                        {row[slot]}
                        {better && <span className="sr-only"> (better)</span>}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          </div>

          <section aria-label="Market value history" className="grid gap-md md:grid-cols-2">
            {slots.map((slot) => (
              <div key={slot} className="min-w-0">
                {loaded[slot] && (
                  <ValueHistoryChart
                    points={loaded[slot]!.valueHistory}
                    width={CHART_WIDTH}
                    height={CHART_HEIGHT}
                  />
                )}
              </div>
            ))}
          </section>

          <section aria-label="Points per jornada" className="grid gap-md md:grid-cols-2">
            {slots.map((slot) => (
              <div key={slot} className="min-w-0">
                {loaded[slot] && (
                  <PointsPerJornadaChart
                    rows={loaded[slot]!.gameweekPoints}
                    seasonWeekRanges={loaded[slot]!.seasonWeekRanges}
                    width={CHART_WIDTH}
                    height={CHART_HEIGHT}
                  />
                )}
              </div>
            ))}
          </section>
        </>
      )}
    </div>
  );
}
