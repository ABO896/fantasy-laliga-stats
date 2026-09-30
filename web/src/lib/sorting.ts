/**
 * Shared sort comparators for the player table.
 *
 * TanStack Table v9 auto-inverts a column's `sortFn` return value when the
 * column is sorted descending (see `createSortedRowModel`'s `isDesc *= -1`
 * step) — correct for a plain ascending comparison, but wrong for anything
 * that must stay direction-immune (nulls always last, ties always broken by
 * ascending player id). These two functions are written as plain,
 * self-contained comparators (no framework involved) so they behave
 * correctly with an ordinary `Array.prototype.sort` call — see
 * `PlayerTable.tsx`, which pre-sorts the row data with these functions and
 * passes `manualSorting: true` to TanStack, rather than fighting the
 * framework's automatic descending-inversion for the null/tie-break cases.
 */

/**
 * Compares two nullable numbers for sorting, with `null` always sorting
 * last regardless of direction. A player with zero points has no defined
 * price/point efficiency (`null`), and letting that coerce to `0` would
 * rank it alongside genuinely worthless players in one direction and above
 * real ones in the other — so `null` is deliberately never treated as a
 * value.
 *
 * Operates on the raw, unrounded numbers — never format/round before
 * calling this, or two values that differ only in the third decimal would
 * incorrectly compare as equal.
 */
export function nullsLastComparator(a: number | null, b: number | null, desc: boolean): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  const cmp = a < b ? -1 : a > b ? 1 : 0;
  return desc ? -cmp : cmp;
}

/**
 * Wraps a comparator so that any tie (comparator returns 0) is broken by
 * ascending `playerId`. This is what makes repeated renders of the same
 * dataset produce an identical row order, and what keeps tied rows in a
 * stable, predictable order regardless of which direction the primary
 * column is currently sorted.
 */
export function withIdTieBreak<T extends { playerId: number }>(
  cmp: (a: T, b: T) => number,
): (a: T, b: T) => number {
  return (a, b) => {
    const primary = cmp(a, b);
    if (primary !== 0) return primary;
    return a.playerId - b.playerId;
  };
}
