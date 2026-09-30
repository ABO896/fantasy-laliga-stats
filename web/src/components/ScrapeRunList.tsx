import { useState } from "react";
import type { ScrapeRunDto } from "../api-client/health";

interface ScrapeRunListProps {
  runs: ScrapeRunDto[];
}

const STATUS_BADGE_CLASS: Record<ScrapeRunDto["status"], string> = {
  success: "bg-[color:var(--color-accent)]/10 text-[color:var(--color-accent)]",
  rejected: "bg-[color:var(--color-destructive)]/10 text-[color:var(--color-destructive)]",
  failed: "bg-[color:var(--color-destructive)]/10 text-[color:var(--color-destructive)]",
  running: "bg-[color:var(--color-neutral)]/10 text-[color:var(--color-neutral)]",
};

const REASON_PREVIEW_LIMIT = 3;

function formatDuration(startedAt: string, finishedAt: string | null): string {
  if (!finishedAt) return "in progress";
  const ms = new Date(finishedAt).getTime() - new Date(startedAt).getTime();
  const seconds = Math.max(0, Math.round(ms / 1000));
  return seconds < 60 ? `${seconds}s` : `${Math.round(seconds / 60)}m`;
}

/** Rejected/failed reasons — collapsed to the first three with an expand
 * control past that (UI-SPEC overflow backstop), heading and body copy
 * verbatim from the UI-SPEC Copywriting Contract's "scrape rejected" row. */
function RunReasons({ run }: { run: ScrapeRunDto }) {
  const [expanded, setExpanded] = useState(false);
  const reasons = run.validationErrors;
  const visible = expanded ? reasons : reasons.slice(0, REASON_PREVIEW_LIMIT);
  const preview = reasons.length > 0 ? `e.g. ${reasons[0]}. ` : "";

  return (
    <div className="mt-sm rounded-[var(--radius-md)] border-l-4 border-[color:var(--color-destructive)] bg-[color:var(--color-destructive)]/8 p-md text-sm">
      <p className="font-semibold text-[color:var(--color-destructive)]">Scrape rejected</p>
      <p className="mt-xs text-[color:var(--color-neutral)]">
        {reasons.length} validation issues — {preview}Yesterday&apos;s data is unchanged.
      </p>
      {reasons.length > 0 && (
        <ul className="mt-sm list-disc pl-lg">
          {visible.map((reason, index) => (
            <li key={index}>{reason}</li>
          ))}
        </ul>
      )}
      {reasons.length > REASON_PREVIEW_LIMIT && (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="link mt-xs text-sm"
        >
          {expanded ? "Show less" : `Show all ${reasons.length}`}
        </button>
      )}
    </div>
  );
}

/** Recent scrape runs, most recent first — one row per run (started time,
 * duration, status badge, row count), with rejected/failed runs expanding
 * to their validation reasons (D-01). */
export default function ScrapeRunList({ runs }: ScrapeRunListProps) {
  return (
    <ul className="mt-sm divide-y divide-[color:var(--color-line)]">
      {runs.map((run) => (
        <li key={run.id} className="py-sm">
          <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-md gap-y-xs text-sm sm:grid-cols-[minmax(0,1fr)_5rem_6rem_7rem]">
            <span className="tabular">{new Date(run.startedAt).toLocaleString()}</span>
            <span className="tabular text-[color:var(--color-neutral)] sm:text-right">
              {formatDuration(run.startedAt, run.finishedAt)}
            </span>
            <span
              data-testid={`status-badge-${run.id}`}
              className={`badge w-fit capitalize sm:justify-self-center ${STATUS_BADGE_CLASS[run.status] ?? "bg-[color:var(--color-surface-alt)] text-[color:var(--color-neutral)]"}`}
            >
              {run.status}
            </span>
            <span className="tabular text-right font-semibold">{run.rowCount} players</span>
          </div>
          {(run.status === "rejected" || run.status === "failed") && <RunReasons run={run} />}
        </li>
      ))}
    </ul>
  );
}
