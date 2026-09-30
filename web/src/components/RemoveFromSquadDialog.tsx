import { useState } from "react";
import type { SquadMemberRow } from "../api-client/squad";
import { formatEuroAbbreviated } from "../lib/format";

interface RemoveFromSquadDialogProps {
  member: SquadMemberRow;
  onConfirm: (salePrice: number | undefined) => void;
  onCancel: () => void;
  error?: string | null;
  pending?: boolean;
}

/**
 * The sibling of `AddToSquadDialog` for the removal side of Spec D-02: a
 * sale is optional to record, but when it happens it stores the real
 * proceeds (spec SQUAD-03) as `sale_price` on the squad member, not the
 * market value at removal time. The field pre-fills with the member's own
 * market value only when one exists — a member can carry no snapshot, and
 * there is nothing honest to pre-fill then.
 *
 * `error` is the server's own refusal sentence, rendered verbatim, exactly
 * as `AddToSquadDialog` does — this component never composes its own
 * explanation either.
 */
export default function RemoveFromSquadDialog({
  member,
  onConfirm,
  onCancel,
  error = null,
  pending = false,
}: RemoveFromSquadDialogProps) {
  const [priceDraft, setPriceDraft] = useState(
    member.marketValue === null ? "" : String(member.marketValue),
  );

  // Same reasoning as the purchase price field in AddToSquadDialog.tsx:
  // type="text" + inputMode="numeric" with a raw string in state, parsed on
  // submit rather than on every keystroke, because a controlled
  // type="number" input reports value === "" for intermediate input like
  // "1e" or "--", which would silently drop what was typed. Sale price
  // cannot be negative, so the parse regex admits only non-negative
  // integers.
  const trimmed = priceDraft.trim();
  const parsedPrice = /^\d+$/.test(trimmed) ? Number(trimmed) : null;
  const isUnparseable = trimmed.length > 0 && parsedPrice === null;

  function recordSale() {
    onConfirm(trimmed.length === 0 ? undefined : (parsedPrice ?? undefined));
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-md">
      <div className="w-full max-w-[420px] rounded-[var(--radius-md)] border border-line bg-surface p-lg shadow-[var(--shadow-pop)]">
        <h2 className="section-title">Remove {member.name}</h2>
        <p className="pt-xs text-sm muted">
          {member.position} · paid {formatEuroAbbreviated(member.purchasePrice)}
        </p>

        <label className="block pt-md text-sm font-medium" htmlFor="sale-price">
          Sale price (leave blank if you&apos;d rather not record it)
        </label>
        <input
          id="sale-price"
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
            disabled={pending}
            onClick={() => onConfirm(undefined)}
            className="btn btn-secondary"
          >
            Skip — don&apos;t record
          </button>
          <button
            type="button"
            disabled={pending || isUnparseable}
            onClick={recordSale}
            className="btn btn-primary"
          >
            Record sale
          </button>
        </div>
      </div>
    </div>
  );
}
