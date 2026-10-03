import { useState, type ChangeEvent } from "react";
import {
  ScrapeAlreadyRunningError,
  triggerScrape,
  type ScrapeMode,
} from "../api-client/health";

const INCLUDE_MINE_KEY = "refresh.includeMine";

/** localStorage can throw (private browsing, quota, disabled storage) —
 * every read/write is wrapped so a blocked store degrades to "off"
 * rather than crashing the control. */
function readIncludeMine(): boolean {
  try {
    return localStorage.getItem(INCLUDE_MINE_KEY) === "true";
  } catch {
    return false;
  }
}

function writeIncludeMine(value: boolean): void {
  try {
    localStorage.setItem(INCLUDE_MINE_KEY, value ? "true" : "false");
  } catch {
    // Best-effort persistence only — the toggle still works for this
    // mount even when it can't be written back.
  }
}

interface RefreshControlsProps {
  /** Called after a trigger request succeeds, so a host page can
   * invalidate/refetch its own health query. */
  onTriggered?: () => void;
  /** Set by a host page when it already knows (e.g. from polling) that a
   * run is in progress, so the controls present as busy before any click
   * here starts one. */
  disabled?: boolean;
}

/** Shared refresh controls (Task 6): quick vs. my-players vs. complete,
 * reused by `StaleBanner` and `HealthPage` so the three modes and the
 * `refresh.includeMine` toggle live in one place. */
export default function RefreshControls({ onTriggered, disabled = false }: RefreshControlsProps) {
  const [includeMine, setIncludeMine] = useState<boolean>(readIncludeMine);
  const [isTriggering, setIsTriggering] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const busy = disabled || isTriggering;

  async function trigger(mode: ScrapeMode) {
    setError(null);
    setIsTriggering(true);
    try {
      await triggerScrape(mode);
      onTriggered?.();
    } catch (err) {
      setError(
        err instanceof ScrapeAlreadyRunningError
          ? "A scrape is already in progress."
          : "Couldn't start the refresh. Try again.",
      );
    } finally {
      setIsTriggering(false);
    }
  }

  function handleToggle(event: ChangeEvent<HTMLInputElement>) {
    const next = event.target.checked;
    setIncludeMine(next);
    writeIncludeMine(next);
  }

  return (
    <div className="flex flex-wrap items-center gap-sm">
      <label className="flex items-center gap-xs text-sm">
        <input
          type="checkbox"
          checked={includeMine}
          onChange={handleToggle}
          disabled={busy}
        />
        + squad &amp; watchlist
      </label>
      <button
        type="button"
        onClick={() => trigger(includeMine ? "mine" : "quick")}
        disabled={busy}
        className="btn btn-primary"
      >
        {busy ? "Refreshing…" : "Refresh now"}
      </button>
      <button
        type="button"
        onClick={() => trigger("complete")}
        disabled={busy}
        title="~15 min: every player's full price and match history"
        className="btn btn-ghost"
      >
        Complete refresh
      </button>
      {error && <p className="state-error">{error}</p>}
    </div>
  );
}
