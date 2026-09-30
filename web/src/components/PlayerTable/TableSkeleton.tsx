/** Placeholder rows matching the default visible column layout (player,
 * team, position, market value, points, efficiency) so the table doesn't
 * reflow when real data replaces the skeleton. Rendered while the
 * `/api/players` fetch is in flight. */
const DEFAULT_VISIBLE_COLUMN_COUNT = 6;
const SKELETON_ROW_COUNT = 8;

export default function TableSkeleton() {
  return (
    <div className="table-scroll">
    <table className="data-table" aria-label="Loading players">
      <thead>
        <tr>
          {Array.from({ length: DEFAULT_VISIBLE_COLUMN_COUNT }).map((_, i) => (
            <th key={i} data-testid="skeleton-header-cell">
              <div className="skeleton h-3 w-16 bg-[color:var(--color-line)]" />
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {Array.from({ length: SKELETON_ROW_COUNT }).map((_, r) => (
          <tr key={r} data-testid="skeleton-row">
            {Array.from({ length: DEFAULT_VISIBLE_COLUMN_COUNT }).map((_, c) => (
              <td key={c}>
                <div className="skeleton h-4 w-full" />
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
    </div>
  );
}
