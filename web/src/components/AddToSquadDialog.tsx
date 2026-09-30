import { useState } from "react";
import type { PlayerRow } from "../api-client/players";
import { formatEuroAbbreviated } from "../lib/format";

interface AddToSquadDialogProps {
  player: PlayerRow;
  onConfirm: (purchasePrice: number) => void;
  onCancel: () => void;
  error?: string | null;
  pending?: boolean;
}

/**
 * Spec D-02: a player enters at a *user-entered* purchase price, pre-filled
 * with today's market value. In the real game you bid, so the two routinely
 * differ, and a builder that assumes market price computes the wrong budget.
 *
 * `error` is the server's own refusal sentence (spec D-05) and is rendered
 * verbatim — this component never composes an explanation of its own.
 */
export default function AddToSquadDialog({
  player,
  onConfirm,
  onCancel,
  error = null,
  pending = false,
}: AddToSquadDialogProps) {
  const [priceDraft, setPriceDraft] = useState(String(player.marketValue));

  // type="text", not "number": see the balance field in SquadPage.tsx for why
  // a controlled type="number" input is unsafe here — this field previously
  // did `Number(event.target.value)` directly, so clearing it produced
  // `Number("") === 0` and silently recorded "paid nothing" (the engine only
  // refuses negatives, so 0 sailed through). Parsing is deferred to submit.
  const trimmed = priceDraft.trim();
  const parsedPrice = /^\d+$/.test(trimmed) ? Number(trimmed) : null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-md">
      <div className="w-full max-w-[420px] rounded-[var(--radius-md)] border border-line bg-surface p-lg shadow-[var(--shadow-pop)]">
        <h2 className="section-title">Add {player.name}</h2>
        <p className="pt-xs text-sm muted">
          {player.team} · {player.position} · market value{" "}
          {formatEuroAbbreviated(player.marketValue)}
        </p>

        <label className="block pt-md text-sm font-medium" htmlFor="purchase-price">
          Purchase price (what you actually paid, in euros)
        </label>
        <input
          id="purchase-price"
          type="text"
          inputMode="numeric"
          value={priceDraft}
          onChange={(event) => setPriceDraft(event.target.value)}
          className="field mt-xs w-full tabular"
        />
        {parsedPrice !== null && (
          <p className="pt-xs text-xs muted tabular">
            {formatEuroAbbreviated(parsedPrice)}
          </p>
        )}

        {error && (
          <p role="alert" className="pt-sm text-sm text-[color:var(--color-destructive)]">
            {error}
          </p>
        )}

        <div className="flex flex-wrap justify-end gap-sm pt-lg">
          <button
            type="button"
            onClick={onCancel}
            className="btn btn-ghost"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={pending || parsedPrice === null}
            onClick={() => {
              if (parsedPrice !== null) onConfirm(parsedPrice);
            }}
            className="btn btn-primary"
          >
            Add to squad
          </button>
        </div>
      </div>
    </div>
  );
}
