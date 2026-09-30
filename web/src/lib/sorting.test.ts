import { describe, expect, it } from "vitest";
import { nullsLastComparator, withIdTieBreak } from "./sorting";

interface Row {
  playerId: number;
  value: number | null;
}

function sortRows(rows: Row[], desc: boolean): Row[] {
  return [...rows].sort(withIdTieBreak((a, b) => nullsLastComparator(a.value, b.value, desc)));
}

describe("nullsLastComparator", () => {
  it("nulls_last_both_directions", () => {
    const rows: Row[] = [
      { playerId: 1, value: 10 },
      { playerId: 2, value: null },
      { playerId: 3, value: 5 },
    ];

    const desc = sortRows(rows, true).map((r) => r.playerId);
    expect(desc).toEqual([1, 3, 2]);

    const asc = sortRows(rows, false).map((r) => r.playerId);
    expect(asc).toEqual([3, 1, 2]);
  });

  it("zero_points_is_not_zero_efficiency", () => {
    const rows: Row[] = [
      { playerId: 1, value: 2.5 }, // genuine efficiency
      { playerId: 2, value: null }, // zero points -> no defined efficiency
    ];

    expect(sortRows(rows, true).map((r) => r.playerId)).toEqual([1, 2]);
    expect(sortRows(rows, false).map((r) => r.playerId)).toEqual([1, 2]);
  });

  it("unrounded_precision", () => {
    const rows: Row[] = [
      { playerId: 1, value: 1.111 },
      { playerId: 2, value: 1.112 },
    ];

    expect(sortRows(rows, false).map((r) => r.playerId)).toEqual([1, 2]);
    expect(sortRows(rows, true).map((r) => r.playerId)).toEqual([2, 1]);
  });
});

describe("withIdTieBreak", () => {
  it("id_tie_break_is_stable", () => {
    const rows: Row[] = [
      { playerId: 3, value: 5 },
      { playerId: 1, value: 5 },
      { playerId: 2, value: 5 },
    ];

    const sortedOnce = sortRows(rows, false).map((r) => r.playerId);
    const sortedTwice = sortRows(rows, false).map((r) => r.playerId);
    expect(sortedOnce).toEqual([1, 2, 3]);
    expect(sortedTwice).toEqual([1, 2, 3]);
  });

  it("direction_toggle_preserves_tie_break", () => {
    const rows: Row[] = [
      { playerId: 3, value: 5 },
      { playerId: 1, value: 10 },
      { playerId: 2, value: 5 },
    ];

    // Primary ordering reverses with direction, but the tied pair (5, 5)
    // stays in ascending playerId order (2 before 3) in both directions.
    expect(sortRows(rows, false).map((r) => r.playerId)).toEqual([2, 3, 1]);
    expect(sortRows(rows, true).map((r) => r.playerId)).toEqual([1, 2, 3]);
  });
});
