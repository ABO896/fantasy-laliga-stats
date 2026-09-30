import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchPlayers, type PlayerRow } from "../api-client/players";
import {
  addSquadPlayer,
  fetchSquadHistory,
  removeSquadPlayer,
  saveXi,
  SquadRuleError,
  type SquadMemberRow,
  type SquadResponse,
} from "../api-client/squad";
import { useSquad } from "../components/SquadBar";
import AddToSquadDialog from "../components/AddToSquadDialog";
import RemoveFromSquadDialog from "../components/RemoveFromSquadDialog";
import Pitch from "../components/pitch/Pitch";
import PageHeader from "../components/ui/PageHeader";
import PlayerCard from "../components/pitch/PlayerCard";
import PointsPerJornadaChart from "../components/player-detail/PointsPerJornadaChart";
import ValueHistoryChart from "../components/player-detail/ValueHistoryChart";
import {
  applyFormationChange,
  applyMove,
  benchSlots,
  isComplete,
  pitchSlots,
  railMembers,
  withRoles,
  type Arrangement,
  type MoveTarget,
} from "../lib/xi";

interface SaveVariables {
  formation: string;
  shape: Record<string, number>;
  next: Arrangement;
}

/**
 * The squad, arranged as a team.
 *
 * Three zones: the pitch as hero, the bench attached beneath it, and everyone
 * else in a right-hand rail with the search box. Adding happens from the
 * rail's search; removing from any card, wherever that card is standing.
 *
 * Every rule is the server's. This page counts slots so the owner can see
 * where they are, and it never decides whether an arrangement is legal.
 */
export default function SquadPage() {
  const queryClient = useQueryClient();
  const { data: squad, isLoading: isSquadLoading, isError: isSquadError } = useSquad();
  const { data: playersData } = useQuery({ queryKey: ["players"], queryFn: fetchPlayers });
  // Its own query key, deliberately: unlike ["squad"], nothing here needs to
  // refetch when the pitch is rearranged — only when the roster or the
  // underlying data actually changes.
  const { data: history } = useQuery({ queryKey: ["squad-history"], queryFn: fetchSquadHistory });

  const [search, setSearch] = useState("");
  const [lifted, setLifted] = useState<number | null>(null);
  const [pendingPlayer, setPendingPlayer] = useState<PlayerRow | null>(null);
  const [addError, setAddError] = useState<string | null>(null);
  const [removeTarget, setRemoveTarget] = useState<SquadMemberRow | null>(null);
  const [removeError, setRemoveError] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["squad"] });

  const addMutation = useMutation({
    mutationFn: ({ playerId, price }: { playerId: number; price: number }) =>
      addSquadPlayer(playerId, price),
    onSuccess: () => {
      invalidate();
      setPendingPlayer(null);
      setAddError(null);
    },
    onError: (error: unknown) =>
      setAddError(
        error instanceof SquadRuleError ? error.violation.message : "Couldn't add that player.",
      ),
  });

  const removeMutation = useMutation({
    mutationFn: ({ playerId, salePrice }: { playerId: number; salePrice: number | undefined }) =>
      removeSquadPlayer(playerId, salePrice),
    onSuccess: () => {
      invalidate();
      setRemoveTarget(null);
      setRemoveError(null);
      setLifted(null);
    },
    onError: (error: unknown) =>
      setRemoveError(
        error instanceof SquadRuleError ? error.violation.message : "Couldn't remove that player.",
      ),
  });

  /**
   * Every change saves at once — there is no save button, because this page is
   * where the owner *looks* at their squad as well as edits it, and a save
   * button on a page visited for browsing is precisely how an arrangement gets
   * silently lost.
   *
   * The update is optimistic and the rollback is the whole point: on a 409 the
   * pitch returns to the last state the server accepted and shows the refusal.
   * The refusal is the signal — a silent revert would leave the owner believing
   * a move stuck.
   */
  const saveMutation = useMutation({
    mutationFn: ({ formation, next }: SaveVariables) =>
      saveXi(formation, next.starterIds, next.benchIds),
    onMutate: async ({ formation, shape: nextShape, next }: SaveVariables) => {
      await queryClient.cancelQueries({ queryKey: ["squad"] });
      const previous = queryClient.getQueryData<SquadResponse>(["squad"]);
      if (previous) {
        // `formationShape` is patched too, not only `formation`: a formation
        // change must redraw the slot grid at once, and every caller already
        // knows the shape it is moving into. For a plain move it is the
        // current shape, unchanged.
        queryClient.setQueryData<SquadResponse>(["squad"], {
          ...previous,
          members: withRoles(previous.members, next),
          summary: { ...previous.summary, formation, formationShape: nextShape },
        });
      }
      setLifted(null);
      setRefusal(null);
      return { previous };
    },
    onError: (error: unknown, _variables, context) => {
      if (context?.previous) queryClient.setQueryData(["squad"], context.previous);
      setRefusal(
        error instanceof SquadRuleError
          ? error.violation.message
          : "Couldn't save that arrangement.",
      );
    },
    onSuccess: (saved) => queryClient.setQueryData(["squad"], saved),
    onSettled: () => invalidate(),
  });

  const owned = useMemo(
    () => new Set(squad?.summary.memberPlayerIds ?? []),
    [squad?.summary.memberPlayerIds],
  );

  const matches = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (term.length === 0) return [];
    return (playersData?.players ?? [])
      .filter((p) => !owned.has(p.playerId) && p.name.toLowerCase().includes(term))
      .slice(0, 10);
  }, [search, playersData, owned]);

  if (isSquadLoading) {
    return <p className="state-note pt-md">Loading your squad…</p>;
  }

  if (isSquadError || !squad) {
    return (
      <p role="alert" className="state-error pt-md">
        Your squad couldn&apos;t be loaded — this page can&apos;t show your roster or take
        roster actions until it does.
      </p>
    );
  }

  const { members, summary } = squad;
  const shape = summary.formationShape;
  const slots = pitchSlots(shape, members);
  const bench = benchSlots(shape, members, summary.benchEnabled);
  const rail = railMembers(members, summary.benchEnabled);
  const complete = isComplete(shape, members);
  const liftedPlayer = members.find((m) => m.playerId === lifted) ?? null;
  const frozen = !summary.formationAvailable;

  function commit(formation: string, shape: Record<string, number>, next: Arrangement) {
    // A stale `bench` role survives the league switching its bench off —
    // `railMembers` shows those players in the rail, but `applyMove` rebuilds
    // `benchIds` from the stored roles and would keep re-sending them, earning
    // a `bench_disabled` refusal on every move that named no substitute.
    // `applyFormationChange` already reconciles this; moves must too.
    saveMutation.mutate({
      formation,
      shape,
      next: summary.benchEnabled ? next : { ...next, benchIds: [] },
    });
  }

  function handleSlotClick(target: MoveTarget) {
    // isPending: a second save must not start while one is unresolved. If it
    // did, the first's rollback would clobber the second's optimistic patch
    // and its refusal would name an arrangement no longer on screen. This
    // guard is load-bearing in a way handlePlayerClick's isn't: onMutate
    // awaits cancelQueries, which can take arbitrarily long when a refetch is
    // genuinely in flight, leaving a window where isPending is true while
    // `lifted` is still set. In that window `lifted === null` doesn't help —
    // only this check does. Don't delete it as redundant with that clause.
    if (frozen || saveMutation.isPending || lifted === null || shape === null) return;
    commit(summary.formation, shape, applyMove(members, lifted, target));
  }

  function handlePlayerClick(playerId: number) {
    if (frozen || saveMutation.isPending) return;
    setLifted((current) => (current === playerId ? null : playerId));
  }

  return (
    <div className="flex flex-col gap-xl">
      <PageHeader
        title="My squad"
        subtitle="Click a player to lift him, then click where he should stand. Changes save as you go."
      />
      <div className="flex flex-col gap-xl lg:flex-row lg:items-start">
        <section className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-md pb-sm">
          <h2 className="section-title">
            {summary.formation} — {summary.squadSize} / {summary.maxSquadSize} players
            {!complete && (
              <span className="pl-sm font-[family-name:var(--font-sans)] text-sm font-normal muted">
                (incomplete — {slots.filter((s) => s.player === null).length} slots still empty)
              </span>
            )}
          </h2>
          <div className="flex items-center gap-sm">
            <label htmlFor="formation" className="text-sm font-semibold muted">
              Formation
            </label>
            <select
              id="formation"
              value={summary.formation}
              disabled={saveMutation.isPending}
              onChange={(event) => {
                const chosen = event.target.value;
                const nextShape = summary.formationShapes[chosen];
                if (!nextShape) return;
                commit(
                  chosen,
                  nextShape,
                  applyFormationChange(members, nextShape, summary.benchEnabled),
                );
              }}
              className="field"
            >
              {summary.allowedFormations.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </div>
          </div>

          {frozen && (
            <p role="alert" className="pb-sm text-sm font-semibold text-[color:var(--color-warning)]">
              {summary.formation} isn&apos;t a shape your league allows any more. Your team is
              shown as it stands; choose a formation your league fields before moving anyone.
            </p>
          )}


          {refusal && (
            <p role="alert" className="state-error pb-sm">
              {refusal}
            </p>
          )}

          <div>
            <Pitch
              slots={slots}
              bench={bench}
              liftedId={lifted}
              liftedPosition={frozen ? null : (liftedPlayer?.position ?? null)}
              onSlotClick={handleSlotClick}
              onPlayerClick={handlePlayerClick}
              onRemove={(player) => {
                setRemoveError(null);
                setRemoveTarget(player);
              }}
            />
          </div>
        </section>

        <aside data-testid="squad-rail" className="panel w-full p-md lg:sticky lg:top-[72px] lg:w-[320px]">
          <label className="subsection-title block" htmlFor="player-search">
            Search players
          </label>
          <input
            id="player-search"
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Name…"
            className="field mt-xs w-full"
          />

          <ul className="pt-sm">
            {matches.map((player) => (
              <li
                key={player.playerId}
                className="flex items-center justify-between gap-sm border-b border-line py-xs text-sm last:border-b-0"
              >
                <span>{player.name}</span>
                <button
                  type="button"
                  aria-label={`Add ${player.name}`}
                  onClick={() => {
                    setAddError(null);
                    setPendingPlayer(player);
                  }}
                  className="btn btn-secondary btn-sm text-[color:var(--color-accent)]"
                >
                  Add
                </button>
              </li>
            ))}
          </ul>

          <h3 className="subsection-title pt-lg">
            Rest of squad
          </h3>
          <button
            type="button"
            aria-label="Send to the rest of the squad"
            disabled={lifted === null || frozen || saveMutation.isPending}
            onClick={() => handleSlotClick({ kind: "rail" })}
            className={`mt-sm w-full rounded-[var(--radius-md)] border-2 border-dashed px-sm py-sm text-xs font-semibold ${
              lifted !== null && !frozen
                ? "border-[color:var(--color-accent)] text-[color:var(--color-accent)]"
                : "border-line muted"
            }`}
          >
            Drop here to take off the pitch
          </button>
          <div className="mt-sm flex flex-col gap-xs">
            {rail.map((player) => (
              <PlayerCard
                key={player.playerId}
                player={player}
                lifted={lifted === player.playerId}
                highlighted={false}
                onClick={() => handlePlayerClick(player.playerId)}
                onRemove={() => {
                  setRemoveError(null);
                  setRemoveTarget(player);
                }}
              />
            ))}
          </div>
        </aside>
      </div>

      {history && (
        <section className="flex flex-col gap-md" data-testid="squad-history">
          <h2 className="section-title">Squad over time</h2>
          <div className="grid gap-md xl:grid-cols-2">
          <div className="panel min-w-0 p-md">
          <ValueHistoryChart
            points={history.valueHistory.map((v) => ({
              asOf: v.asOf,
              marketValue: v.squadValue,
            }))}
            width={640}
            height={240}
            caption="Squad value"
            emptyMessage="No squad value history yet."
          />
          </div>
          <div className="panel min-w-0 p-md">
          <PointsPerJornadaChart
            rows={history.pointsHistory}
            seasonWeekRanges={history.seasonWeekRanges}
            width={640}
            height={240}
            caption="Squad points per jornada · current squad, every recorded week"
            emptyMessage="No jornada scores recorded for the squad yet."
          />
          </div>
          </div>
        </section>
      )}

      {pendingPlayer && (
        <AddToSquadDialog
          player={pendingPlayer}
          error={addError}
          pending={addMutation.isPending}
          onCancel={() => {
            setPendingPlayer(null);
            setAddError(null);
          }}
          onConfirm={(price) => addMutation.mutate({ playerId: pendingPlayer.playerId, price })}
        />
      )}

      {removeTarget && (
        <RemoveFromSquadDialog
          member={removeTarget}
          error={removeError}
          pending={removeMutation.isPending}
          onCancel={() => {
            setRemoveTarget(null);
            setRemoveError(null);
          }}
          onConfirm={(salePrice) =>
            removeMutation.mutate({ playerId: removeTarget.playerId, salePrice })
          }
        />
      )}
    </div>
  );
}
