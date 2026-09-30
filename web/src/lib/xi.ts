import type { SquadMemberRow, SquadRole } from "../api-client/squad";

/** The order the pitch is drawn in, keeper at the bottom of the render but
 * first in the data — every consumer relies on this being stable. */
export const POSITION_ORDER = ["POR", "DEF", "MED", "DEL"] as const;

export interface Slot {
  position: string;
  /** Its ordinal within that position, so React has a stable key for an
   * empty slot, which has no player id to key on. */
  index: number;
  player: SquadMemberRow | null;
}

export interface Arrangement {
  starterIds: number[];
  benchIds: number[];
}

export type MoveTarget =
  | { kind: "pitch" | "bench"; position: string; occupantId: number | null }
  | { kind: "rail" };

function of(members: SquadMemberRow[], role: SquadRole, position?: string) {
  return members.filter((m) => m.role === role && (position === undefined || m.position === position));
}

function slotsFor(
  shape: Record<string, number> | null,
  members: SquadMemberRow[],
  role: SquadRole,
  count: (position: string) => number,
): Slot[] {
  if (shape === null) return [];
  const slots: Slot[] = [];
  for (const position of POSITION_ORDER) {
    const occupants = of(members, role, position);
    for (let index = 0; index < count(position); index += 1) {
      slots.push({ position, index, player: occupants[index] ?? null });
    }
  }
  return slots;
}

/** One slot per player the formation fields, filled with the starters of that
 * position in squad order. A slot with `player: null` is an empty place, which
 * is a normal state and never a violation. */
export function pitchSlots(
  shape: Record<string, number> | null,
  members: SquadMemberRow[],
): Slot[] {
  return slotsFor(shape, members, "starter", (position) => shape?.[position] ?? 0);
}

/** One substitute per position the formation actually fields — a 4-6-0 offers
 * no forward slot — and nothing at all when the league has no bench. */
export function benchSlots(
  shape: Record<string, number> | null,
  members: SquadMemberRow[],
  benchEnabled: boolean,
): Slot[] {
  if (!benchEnabled) return [];
  return slotsFor(shape, members, "bench", (position) => ((shape?.[position] ?? 0) > 0 ? 1 : 0));
}

/** Everyone not on the pitch. A player holding a stored `bench` role in a
 * league without a bench belongs here too — otherwise they would be invisible
 * until the next save, which is how a squad member silently disappears. */
export function railMembers(members: SquadMemberRow[], benchEnabled: boolean): SquadMemberRow[] {
  return members.filter(
    (m) => m.role === "reserve" || (m.role === "bench" && !benchEnabled),
  );
}

/** Whether every slot is filled. A label, never a legality check — the server
 * owns that, and it accepts an incomplete XI. */
export function isComplete(
  shape: Record<string, number> | null,
  members: SquadMemberRow[],
): boolean {
  if (shape === null) return false;
  return POSITION_ORDER.every(
    (position) => of(members, "starter", position).length === (shape[position] ?? 0),
  );
}

function arrangementFrom(members: SquadMemberRow[], roles: Map<number, SquadRole>): Arrangement {
  return {
    starterIds: members.filter((m) => roles.get(m.playerId) === "starter").map((m) => m.playerId),
    benchIds: members.filter((m) => roles.get(m.playerId) === "bench").map((m) => m.playerId),
  };
}

/** The arrangement that results from putting the lifted player down on
 * `target`. An occupied destination is a swap: the occupant inherits whatever
 * place the lifted player just left, so nobody is displaced into nowhere. */
export function applyMove(
  members: SquadMemberRow[],
  liftedId: number,
  target: MoveTarget,
): Arrangement {
  const roles = new Map<number, SquadRole>(members.map((m) => [m.playerId, m.role]));
  const from = roles.get(liftedId) ?? "reserve";

  if (target.kind === "rail") {
    roles.set(liftedId, "reserve");
  } else {
    if (target.occupantId !== null) roles.set(target.occupantId, from);
    roles.set(liftedId, target.kind === "pitch" ? "starter" : "bench");
  }

  return arrangementFrom(members, roles);
}

/** The arrangement that survives a formation change.
 *
 * Starters a narrower shape has no room for are demoted here, in the client,
 * where the owner can see it happen — which is why there is no
 * `PUT /api/squad/formation`: the server would have to invent the same rule
 * invisibly. "The earliest survive" means earliest in squad order, which is
 * acquisition order, and is arbitrary but stable — the alternative is a
 * demotion that reshuffles differently every time the page loads.
 */
export function applyFormationChange(
  members: SquadMemberRow[],
  shape: Record<string, number>,
  benchEnabled: boolean,
): Arrangement {
  const roles = new Map<number, SquadRole>(members.map((m) => [m.playerId, m.role]));

  for (const position of POSITION_ORDER) {
    of(members, "starter", position)
      .slice(shape[position] ?? 0)
      .forEach((m) => roles.set(m.playerId, "reserve"));

    const bench = of(members, "bench", position);
    const keep = benchEnabled && (shape[position] ?? 0) > 0 ? 1 : 0;
    bench.slice(keep).forEach((m) => roles.set(m.playerId, "reserve"));
  }

  return arrangementFrom(members, roles);
}

/** The members list as it would look once `next` is saved — the optimistic
 * render's input. Returns new objects so React sees the change. */
export function withRoles(members: SquadMemberRow[], next: Arrangement): SquadMemberRow[] {
  const starters = new Set(next.starterIds);
  const bench = new Set(next.benchIds);
  return members.map((m) => ({
    ...m,
    role: starters.has(m.playerId) ? "starter" : bench.has(m.playerId) ? "bench" : "reserve",
  }));
}
