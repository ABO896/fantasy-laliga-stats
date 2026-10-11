import { useQuery } from "@tanstack/react-query";
import { fetchHealth } from "../api-client/health";

/** Shown above every page when the database is behind the code: after a
 * pull that adds a migration, pages fail one by one until it is applied,
 * and nothing else says why. Shares the `["health"]` query with the stale
 * banner. */
export default function SchemaBanner() {
  const { data } = useQuery({ queryKey: ["health"], queryFn: fetchHealth, staleTime: 60_000 });
  const schema = data?.schema;
  if (!schema || schema.upToDate) return null;
  return (
    <div role="alert" className="border-b border-[color:var(--color-destructive)]/30 bg-[color:var(--color-destructive)]/10">
      <div className="mx-auto max-w-[1600px] px-md py-sm sm:px-lg lg:px-xl">
        <p className="text-sm font-semibold text-[color:var(--color-destructive)]">
          The database is behind the code (at {schema.current ?? "none"}, needs {schema.head}).
        </p>
        <p className="state-note">
          Stop the app, back up data/fantasy.db, run <code>uv run alembic upgrade head</code>, and
          start it again. Until then some pages will fail to load.
        </p>
      </div>
    </div>
  );
}
