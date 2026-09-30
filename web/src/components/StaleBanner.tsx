import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchHealth, ScrapeAlreadyRunningError, triggerScrape } from "../api-client/health";

/** Madrid, because the market update is a wall-clock event there and the
 * owner's own day runs on it. */
const MADRID_TIME = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/Madrid",
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

/** D-04: on detecting stale data, prompt — never auto-refresh silently,
 * never block the interface. Mounted once in `Layout.tsx` above the
 * route outlet so it appears on every page without any page (the player
 * table included) owning it or being hidden while the banner shows.
 * Dismissing with "Not now" only hides the banner for this mount/session
 * — it is never treated as consent to scrape, and never suppresses the
 * banner again once the app is reopened. */
export default function StaleBanner() {
  const queryClient = useQueryClient();
  const [dismissed, setDismissed] = useState(false);
  const [isTriggering, setIsTriggering] = useState(false);
  const [triggerError, setTriggerError] = useState<string | null>(null);

  const { data } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    staleTime: 60_000,
  });

  async function handleRefreshNow() {
    setTriggerError(null);
    setIsTriggering(true);
    try {
      await triggerScrape();
      await queryClient.invalidateQueries({ queryKey: ["health"] });
    } catch (error) {
      setTriggerError(
        error instanceof ScrapeAlreadyRunningError
          ? "A scrape is already in progress."
          : "Couldn't start the refresh. Try again.",
      );
    } finally {
      setIsTriggering(false);
    }
  }

  if (!data || !data.isStale || dismissed) {
    return null;
  }

  const hoursSinceLastSuccess =
    data.hoursSinceLastSuccess === null ? null : Math.round(data.hoursSinceLastSuccess);
  const marketUpdated = MADRID_TIME.format(new Date(data.marketUpdatedAt));

  return (
    <div
      role="status"
      className="border-b border-[color:var(--color-warning)]/30 bg-[color:var(--color-warning)]/10"
    >
      <div className="mx-auto flex max-w-[1600px] flex-col gap-sm px-md py-sm sm:flex-row sm:items-center sm:justify-between sm:gap-md sm:px-lg lg:px-xl">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-[color:var(--color-warning)]">
            The market has moved since this data — refresh now?
          </p>
          <p className="state-note">
            {hoursSinceLastSuccess === null
              ? "Nothing has been scraped successfully yet."
              : `Last scraped ${hoursSinceLastSuccess}h ago, before the market update at ${marketUpdated}.`}{" "}
            Prices and points on screen are from the previous cycle.
          </p>
          {triggerError && <p className="state-error">{triggerError}</p>}
        </div>
        <div className="flex shrink-0 gap-sm">
          <button
            type="button"
            onClick={handleRefreshNow}
            disabled={isTriggering}
            className="btn btn-primary"
          >
            {isTriggering ? "Refreshing…" : "Refresh now"}
          </button>
          <button type="button" onClick={() => setDismissed(true)} className="btn btn-ghost">
            Not now
          </button>
        </div>
      </div>
    </div>
  );
}
