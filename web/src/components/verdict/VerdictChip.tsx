import type { VerdictLabel } from "../../api-client/verdict";

export type VerdictTone = "positive" | "negative" | "caution" | "neutral";

/** Which of the four tones each label reads as — never the only signal
 * (the label text is always the chip's content too). Positive: doing well
 * right now. Negative: a reason to move on. Caution: a state worth
 * watching. Neutral: no strong signal either way. */
const TONE_BY_LABEL: Record<VerdictLabel, VerdictTone> = {
  Elite: "positive",
  Bargain: "positive",
  Rising: "positive",
  "Sell high": "negative",
  Overpriced: "negative",
  Avoid: "negative",
  "Rotation risk": "caution",
  Unavailable: "caution",
  Unproven: "neutral",
  "Fair price": "neutral",
};

export function verdictTone(label: string): VerdictTone {
  return TONE_BY_LABEL[label as VerdictLabel] ?? "neutral";
}

/** A coloured pill for one verdict label. `size="sm"` is for tight spaces
 * (the pitch card); the player page and table lead with `size="md"`. */
export default function VerdictChip({
  label,
  size = "md",
}: {
  label: string;
  size?: "sm" | "md";
}) {
  return (
    <span className={`verdict-chip verdict-chip-${size}`} data-tone={verdictTone(label)}>
      {label}
    </span>
  );
}
