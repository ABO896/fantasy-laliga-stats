import { Link } from "react-router-dom";
import type { SquadMemberRow } from "../../api-client/squad";
import { formatEuroAbbreviated } from "../../lib/format";
import VerdictChip from "../verdict/VerdictChip";

const POSITION_NAMES: Record<string, string> = {
  POR: "goalkeeper",
  DEF: "defender",
  MED: "midfielder",
  DEL: "forward",
};

function formatScore(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : Math.round(value).toString();
}

/** "PWR 71 #2 · VAL 84" — Power's score, his rank within the position when
 * there is one, and the points-value percentile. Built as one string (not
 * interpolated across JSX children) so the rank's leading space never
 * depends on JSX's whitespace-collapsing rules. */
function powerLine(player: SquadMemberRow): string {
  const rank = player.powerRank ? ` #${player.powerRank.rank}` : "";
  return `PWR ${formatScore(player.powerScore)}${rank} · VAL ${formatScore(player.pointsValuePct)}`;
}

interface PlayerCardProps {
  player: SquadMemberRow;
  lifted: boolean;
  highlighted: boolean;
  onClick: () => void;
  onRemove?: () => void;
}

/**
 * One player, wherever they are standing. A button rather than a draggable —
 * click-to-lift works identically on a trackpad and a touchscreen, and is
 * keyboard-operable without extra work, which is the whole reason
 * drag-and-drop was cut.
 *
 * The availability badge is a badge and never a refusal: the real game lets
 * you field an injured player and punishes you with the score.
 */
export default function PlayerCard({
  player,
  lifted,
  highlighted,
  onClick,
  onRemove,
}: PlayerCardProps) {
  const noun = POSITION_NAMES[player.position] ?? player.position;
  return (
    <div className="relative h-full min-w-0">
      <button
        type="button"
        aria-pressed={lifted}
        aria-label={`${player.name}, ${noun}`}
        onClick={onClick}
        data-pos={player.position}
        className={`block h-full w-full min-w-0 overflow-hidden rounded-[var(--radius-md)] border bg-surface py-xs pl-sm pr-lg text-left text-sm text-ink shadow-[var(--shadow-panel)] transition-[box-shadow,transform] ${
          lifted
            ? "-translate-y-[2px] border-[color:var(--color-card)] shadow-[0_0_0_3px_var(--color-card),var(--shadow-pop)]"
            : highlighted
              ? "border-[color:var(--color-accent)] shadow-[0_0_0_2px_var(--color-accent)]"
              : "border-line hover:border-[color:var(--color-neutral)]"
        }`}
      >
        {/* Position colour runs down the card's left edge. */}
        <span
          aria-hidden="true"
          className="absolute inset-y-0 left-0 w-[4px] rounded-l-[var(--radius-md)]"
          style={{ background: `var(--color-pos-${player.position.toLowerCase()})` }}
        />
        <span className={`block truncate ${lifted ? "font-bold" : "font-semibold"}`}>
          {player.name}
        </span>
        <span className="block text-xs muted">
          {player.position} ·{" "}
          <span className="tabular">
            {player.marketValue === null ? "—" : formatEuroAbbreviated(player.marketValue)}
          </span>
        </span>
        <span className="flex flex-wrap gap-x-sm text-xs">
          {/* ANALYTICS-06 + Task 7. Side by side with a same-position
              teammate's card, Power (and his rank within the position) and
              points Value are the "who should I start" comparison. */}
          <span
            className="tabular muted"
            title="Power Score (0–100) and position rank · Value: points above a cheap regular starter, per € (percentile within position)"
          >
            {powerLine(player)}
          </span>
          {/* MODEL-02: expected points for the next jornada. */}
          <span
            className="tabular font-semibold"
            title={`Expected points next jornada — basis: ${player.expectedPointsBasis ?? "none yet"}`}
          >
            xP{" "}
            {player.expectedPoints === null || player.expectedPoints === undefined
              ? "—"
              : player.expectedPoints.toFixed(1)}
          </span>
          {/* Plan C Task 6 — the verdict label every surface agrees on. */}
          {player.verdict && <VerdictChip label={player.verdict.label} size="sm" />}
        </span>
        {player.availability !== "available" && (
          <span className="mt-[2px] inline-block rounded-[var(--radius-sm)] bg-[color:var(--color-warning)]/15 px-[5px] text-[11px] font-semibold capitalize text-[color:var(--color-warning)]">
            {player.availability}
          </span>
        )}
      </button>
      {onRemove && (
        <button
          type="button"
          aria-label={`Remove ${player.name}`}
          onClick={onRemove}
          className="absolute right-[3px] top-[3px] flex h-5 w-5 items-center justify-center rounded-full text-sm leading-none muted hover:bg-[color:var(--color-destructive)]/12 hover:text-[color:var(--color-destructive)]"
        >
          ×
        </button>
      )}
      <Link
        to={`/players/${player.playerId}`}
        aria-label={`View ${player.name}`}
        className="absolute bottom-[3px] right-[3px] flex h-5 w-5 items-center justify-center rounded-full text-xs text-[color:var(--color-accent)] hover:bg-[color:var(--color-accent)]/12"
      >
        ⓘ
      </Link>
    </div>
  );
}
