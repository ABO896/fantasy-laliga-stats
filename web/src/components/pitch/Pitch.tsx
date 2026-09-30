import type { SquadMemberRow } from "../../api-client/squad";
import type { MoveTarget, Slot } from "../../lib/xi";
import PlayerCard from "./PlayerCard";

const POSITION_NAMES: Record<string, string> = {
  POR: "goalkeeper",
  DEF: "defender",
  MED: "midfielder",
  DEL: "forward",
};

interface PitchProps {
  slots: Slot[];
  bench: Slot[];
  liftedId: number | null;
  liftedPosition: string | null;
  onSlotClick: (target: MoveTarget) => void;
  onPlayerClick: (playerId: number) => void;
  /** Removing a starter or a substitute directly, without first moving them to
   * the rail — the rail already offers this, and spec §6 asks for the same
   * control on any card, wherever it is standing. */
  onRemove?: (player: SquadMemberRow) => void;
}

function row(slots: Slot[], position: string) {
  return slots.filter((s) => s.position === position);
}

/**
 * The eleven, drawn as the shape they are standing in, with the bench
 * attached directly beneath. The bench belongs here rather than in the rail
 * because its slots are defined by the formation — it is part of the shape,
 * not part of the pool.
 *
 * Presentational only: it emits intents and holds no state. Which moves are
 * legal is the server's answer; which are *offered* is the highlight below,
 * and the two can disagree without anything breaking — an offered move that
 * the server refuses reverts and shows the refusal.
 */
export default function Pitch({
  slots,
  bench,
  liftedId,
  liftedPosition,
  onSlotClick,
  onPlayerClick,
  onRemove,
}: PitchProps) {
  function renderSlot(slot: Slot, kind: "pitch" | "bench") {
    const noun = POSITION_NAMES[slot.position] ?? slot.position;
    const highlighted = liftedPosition === slot.position;

    if (slot.player === null) {
      return (
        <button
          key={`${kind}-${slot.position}-${slot.index}`}
          type="button"
          aria-label={`Empty ${noun} slot`}
          onClick={() => onSlotClick({ kind, position: slot.position, occupantId: null })}
          className={`flex min-h-[84px] w-full items-center justify-center rounded-[var(--radius-md)] border-2 border-dashed font-[family-name:var(--font-display)] text-sm font-bold tracking-[0.04em] transition-colors ${
            kind === "bench"
              ? highlighted
                ? "border-[color:var(--color-accent)] text-[color:var(--color-accent)]"
                : "border-line muted"
              : highlighted
                ? "border-[color:var(--color-card)] bg-white/10 text-white"
                : "border-white/45 text-white/80 hover:bg-white/5"
          }`}
        >
          {slot.position}
        </button>
      );
    }

    const occupant = slot.player;
    return (
      <PlayerCard
        key={`${kind}-${occupant.playerId}`}
        player={occupant}
        lifted={liftedId === occupant.playerId}
        highlighted={highlighted && liftedId !== occupant.playerId}
        onClick={() =>
          liftedId !== null && liftedId !== occupant.playerId
            ? onSlotClick({ kind, position: slot.position, occupantId: occupant.playerId })
            : onPlayerClick(occupant.playerId)
        }
        onRemove={onRemove ? () => onRemove(occupant) : undefined}
      />
    );
  }

  return (
    <>
      {/* The pitch keeps a legible card width; below ~34rem it scrolls
          inside this box instead of squeezing names to nothing (UI-02). */}
      <div className="overflow-x-auto rounded-[var(--radius-lg)]">
        <div
          data-testid="pitch"
          className="pitch flex min-w-[30rem] flex-col gap-md px-sm pb-2xl pt-xl sm:gap-lg sm:px-md"
        >
          <PitchMarkings />
          {(["DEL", "MED", "DEF", "POR"] as const).map((position) => {
            const cells = row(slots, position);
            if (cells.length === 0) return null;
            return (
              <div
                key={position}
                className="grid justify-center gap-sm"
                style={{ gridTemplateColumns: `repeat(${cells.length}, minmax(0, 150px))` }}
              >
                {cells.map((slot) => renderSlot(slot, "pitch"))}
              </div>
            );
          })}
        </div>
      </div>
      {bench.length > 0 && (
        <div
          data-testid="bench-strip"
          className="mt-sm rounded-[var(--radius-md)] border border-line bg-surface-alt p-sm"
        >
          <h3 className="subsection-title px-xs">Bench</h3>
          <div className="mt-sm grid grid-cols-2 gap-sm sm:grid-cols-4">
            {bench.map((slot) => renderSlot(slot, "bench"))}
          </div>
        </div>
      )}
    </>
  );
}

/** Touchline, halfway line with the centre circle cut by the top edge, and
 * our own penalty area at the bottom — drawn as fixed-size pieces so the
 * circle stays a circle whatever the pitch's width. */
function PitchMarkings() {
  const line = { stroke: "currentColor", strokeWidth: 2, fill: "none" } as const;
  return (
    <div className="pitch-markings" aria-hidden="true">
      <div className="absolute inset-0 rounded-[6px] border-2 border-current" />
      <svg className="absolute left-1/2 top-0 -translate-x-1/2" width="180" height="72" viewBox="0 0 180 72">
        <circle cx="90" cy="0" r="70" {...line} />
        <circle cx="90" cy="0" r="4" fill="currentColor" />
      </svg>
      <svg className="absolute bottom-0 left-1/2 -translate-x-1/2" width="320" height="118" viewBox="0 0 320 118">
        <rect x="40" y="30" width="240" height="88" {...line} />
        <rect x="104" y="84" width="112" height="34" {...line} />
        <path d="M 124 30 A 44 44 0 0 1 196 30" {...line} />
        <circle cx="160" cy="62" r="3" fill="currentColor" />
      </svg>
    </div>
  );
}
