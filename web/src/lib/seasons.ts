/** A LaLiga season spans two calendar years, and the database keys it by the
 * first of them (`Settings.current_season_year` is 2026 for 2026/27). A bare
 * `2026` in a column header is ambiguous to a reader, and the player page
 * puts two seasons side by side, so nothing renders a bare season year. */
export function seasonLabel(seasonYear: number): string {
  const next = String((seasonYear + 1) % 100).padStart(2, "0");
  return `${seasonYear}/${next}`;
}
