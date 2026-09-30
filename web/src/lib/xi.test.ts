import { describe, expect, it } from "vitest";
import type { SquadMemberRow } from "../api-client/squad";
import {
  applyFormationChange,
  applyMove,
  benchSlots,
  isComplete,
  pitchSlots,
  railMembers,
  withRoles,
} from "./xi";

const SHAPE_442 = { POR: 1, DEF: 4, MED: 4, DEL: 2 };
const SHAPE_343 = { POR: 1, DEF: 3, MED: 4, DEL: 3 };
const SHAPE_460 = { POR: 1, DEF: 4, MED: 6, DEL: 0 };

function member(
  playerId: number,
  position: string,
  role: SquadMemberRow["role"] = "reserve",
): SquadMemberRow {
  return {
    playerId,
    name: `P${playerId}`,
    position,
    purchasePrice: 1_000_000,
    marketValue: 1_000_000,
    effectiveValue: 1_000_000,
    role,
    availability: "available",
  };
}

describe("pitchSlots", () => {
  it("lays out one slot per position the formation fields, in POR-DEF-MED-DEL order", () => {
    const slots = pitchSlots(SHAPE_442, []);
    expect(slots).toHaveLength(11);
    expect(slots.map((s) => s.position).join("")).toBe(
      "POR" + "DEF".repeat(4) + "MED".repeat(4) + "DEL".repeat(2),
    );
    expect(slots.every((s) => s.player === null)).toBe(true);
  });

  it("fills slots with the starters of that position, in squad order", () => {
    const slots = pitchSlots(SHAPE_442, [member(7, "DEF", "starter"), member(3, "DEF", "starter")]);
    const defenders = slots.filter((s) => s.position === "DEF");
    expect(defenders.map((s) => s.player?.playerId)).toEqual([7, 3, undefined, undefined]);
  });

  it("offers no forward slot in a 4-6-0", () => {
    expect(pitchSlots(SHAPE_460, []).some((s) => s.position === "DEL")).toBe(false);
  });

  it("returns nothing when the shape is unknown", () => {
    expect(pitchSlots(null, [member(1, "DEF", "starter")])).toEqual([]);
  });
});

describe("benchSlots", () => {
  it("offers one slot per position the formation fields, and only when the bench is on", () => {
    expect(benchSlots(SHAPE_442, [], true).map((s) => s.position)).toEqual([
      "POR",
      "DEF",
      "MED",
      "DEL",
    ]);
    expect(benchSlots(SHAPE_442, [], false)).toEqual([]);
  });

  it("offers no forward slot in a 4-6-0", () => {
    expect(benchSlots(SHAPE_460, [], true).map((s) => s.position)).toEqual(["POR", "DEF", "MED"]);
  });

  it("seats the bench members in their own position's slot", () => {
    const slots = benchSlots(SHAPE_442, [member(4, "MED", "bench")], true);
    expect(slots.find((s) => s.position === "MED")?.player?.playerId).toBe(4);
    expect(slots.find((s) => s.position === "DEF")?.player).toBeNull();
  });

  it("returns nothing when the shape is unknown", () => {
    expect(benchSlots(null, [member(1, "DEF", "bench")], true)).toEqual([]);
  });
});

describe("railMembers", () => {
  it("holds the reserves", () => {
    const members = [member(1, "DEF", "starter"), member(2, "DEF"), member(3, "MED")];
    expect(railMembers(members, true).map((m) => m.playerId)).toEqual([2, 3]);
  });

  it("also holds bench members when the league has no bench, so nobody vanishes", () => {
    const members = [member(1, "DEF", "bench"), member(2, "DEF")];
    expect(railMembers(members, false).map((m) => m.playerId)).toEqual([1, 2]);
    expect(railMembers(members, true).map((m) => m.playerId)).toEqual([2]);
  });
});

describe("isComplete", () => {
  it("is true only when every slot is filled", () => {
    const full = [
      member(1, "POR", "starter"),
      ...[2, 3, 4, 5].map((id) => member(id, "DEF", "starter")),
      ...[6, 7, 8, 9].map((id) => member(id, "MED", "starter")),
      ...[10, 11].map((id) => member(id, "DEL", "starter")),
    ];
    expect(isComplete(SHAPE_442, full)).toBe(true);
    expect(isComplete(SHAPE_442, full.slice(1))).toBe(false);
    expect(isComplete(null, full)).toBe(false);
  });
});

describe("applyMove", () => {
  const members = [
    member(1, "DEF", "starter"),
    member(2, "DEF"),
    member(3, "MED", "bench"),
  ];

  it("puts a reserve into an empty pitch slot", () => {
    expect(applyMove(members, 2, { kind: "pitch", position: "DEF", occupantId: null })).toEqual({
      starterIds: [1, 2],
      benchIds: [3],
    });
  });

  it("swaps the two when the slot is occupied — the occupant inherits the lifted player's place", () => {
    expect(applyMove(members, 2, { kind: "pitch", position: "DEF", occupantId: 1 })).toEqual({
      starterIds: [2],
      benchIds: [3],
    });
  });

  it("hands the displaced occupant the lifted player's own previous place", () => {
    // The discriminating case: the lifted player comes off the BENCH, so the
    // starter they displace must land on the bench and not in the rail. The
    // sibling test above lifts a reserve, where `from` is "reserve" anyway —
    // a hardcoded "reserve" would pass it while silently emptying the bench
    // on every pitch swap.
    const benched = [member(1, "MED", "starter"), member(2, "MED", "bench")];
    expect(applyMove(benched, 2, { kind: "pitch", position: "MED", occupantId: 1 })).toEqual({
      starterIds: [2],
      benchIds: [1],
    });
  });

  it("sends a starter back to the rail", () => {
    expect(applyMove(members, 1, { kind: "rail" })).toEqual({ starterIds: [], benchIds: [3] });
  });

  it("seats a reserve on the bench", () => {
    // [2, 3] and not [3, 2]: `arrangementFrom` reads the members list in
    // order, so both id lists come back in squad order regardless of the
    // order things were clicked. The next test pins that property directly.
    expect(applyMove(members, 2, { kind: "bench", position: "DEF", occupantId: null })).toEqual({
      starterIds: [1],
      benchIds: [2, 3],
    });
  });

  it("keeps the ids in squad order, not click order", () => {
    const result = applyMove(members, 2, { kind: "pitch", position: "DEF", occupantId: null });
    expect(result.starterIds).toEqual([1, 2]);
  });
});

describe("applyFormationChange", () => {
  const backFive = [
    member(1, "POR", "starter"),
    ...[2, 3, 4, 5].map((id) => member(id, "DEF", "starter")),
    member(6, "DEL", "bench"),
  ];

  it("demotes the starters a narrower shape has no room for, keeping the earliest", () => {
    expect(applyFormationChange(backFive, SHAPE_343, true)).toEqual({
      starterIds: [1, 2, 3, 4],
      benchIds: [6],
    });
  });

  it("drops a substitute whose position the new shape does not field", () => {
    expect(applyFormationChange(backFive, SHAPE_460, true)).toEqual({
      starterIds: [1, 2, 3, 4, 5],
      benchIds: [],
    });
  });

  it("empties the bench when the league has none", () => {
    expect(applyFormationChange(backFive, SHAPE_442, false).benchIds).toEqual([]);
  });
});

describe("withRoles", () => {
  it("rewrites every member's role from an arrangement, for the optimistic render", () => {
    const members = [member(1, "DEF", "starter"), member(2, "DEF"), member(3, "MED", "bench")];
    const next = withRoles(members, { starterIds: [2], benchIds: [1] });
    expect(next.map((m) => m.role)).toEqual(["bench", "starter", "reserve"]);
    expect(next[0]).not.toBe(members[0]);
  });
});
