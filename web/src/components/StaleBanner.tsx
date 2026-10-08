import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchHealth } from "../api-client/health";
import RefreshControls from "./RefreshControls";
import { useRefreshStatus } from "../hooks/useRefreshStatus";

/** Madrid, because the market update is a wall-clock event there and the
 * owner's own day runs on it. */
const MADRID_TIME = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/Madrid",
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

const LOCK_WEEKDAY_TIME = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/Madrid",
  weekday: "short",
  hour: "2-digit",
  minute: "2-digit",
});

/** How close a lock has to be before the banner reminds about it. */
const LOCK_REMINDER_HOURS = 36;

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

  const { data } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    staleTime: 60_000,
  });
  // Polls while a refresh runs, and reloads every page's data when it ends.
  const { running } = useRefreshStatus();

  async function handleTriggered() {
    await queryClient.invalidateQueries({ queryKey: ["health"] });
  }

  const lock = data?.nextLock ?? null;
  const hoursToLock = lock ? (new Date(lock.locksAt).getTime() - Date.now()) / 3_600_000 : null;
  const lockSoon =
    lock !== null &&
    !lock.predictionsRecorded &&
    hoursToLock !== null &&
    hoursToLock > 0 &&
    hoursToLock <= LOCK_REMINDER_HOURS;
  const lockNote = lock
    ? `J${lock.jornada} locks ${LOCK_WEEKDAY_TIME.format(new Date(lock.locksAt))}. Refresh before then to record predictions.`
    : "";

  if (!data || (!data.isStale && !running && !lockSoon) || dismissed) {
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
          {!data.isStale && lockSoon ? (
            <p className="text-sm font-semibold text-[color:var(--color-warning)]">{lockNote}</p>
          ) : (
            <>
              <p className="text-sm font-semibold text-[color:var(--color-warning)]">
                The market has moved since this data — refresh now?
              </p>
              <p className="state-note">
                {hoursSinceLastSuccess === null
                  ? "Nothing has been scraped successfully yet."
                  : `Last scraped ${hoursSinceLastSuccess}h ago, before the market update at ${marketUpdated}.`}{" "}
                Prices and points on screen are from the previous cycle.
              </p>
              {lockSoon && <p className="state-note">{lockNote}</p>}
            </>
          )}
          {data.suggestComplete && (
            <p className="state-note">
              A complete refresh is recommended — some players&apos; history is behind.
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-sm">
          <RefreshControls onTriggered={handleTriggered} />
          <button type="button" onClick={() => setDismissed(true)} className="btn btn-ghost">
            Not now
          </button>
        </div>
      </div>
    </div>
  );
}
