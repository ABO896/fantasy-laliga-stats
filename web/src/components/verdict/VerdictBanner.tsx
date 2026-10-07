import type { PersonalLine } from "../../api-client/verdict";
import { usePlayerVerdict } from "./usePlayerVerdict";
import VerdictChip from "./VerdictChip";

/** One glyph per `PersonalLine.kind` — a quick visual read before the
 * sentence is read. aria-hidden since the sentence itself already carries
 * the meaning in words. */
const PERSONAL_ICON: Record<PersonalLine["kind"], string> = {
  keep: "✓",
  sell: "↓",
  upgrade: "↑",
  replace: "⇄",
  no_improvement: "–",
};

/** Labels that make no forward claim (`core.verdict_harness.CLAIMS`): a
 * fact or the fallback, so there is nothing to validate. */
const NO_CLAIM = new Set(["Unavailable", "Unproven", "Fair price"]);

/**
 * The player page's decision-first banner (Plan C, Task 6). Fetches its
 * own verdict — label, tags, reason, confidence, the personal line read
 * against the owner's squad, and whether the walk-forward harness has
 * shown this label beats chance — so the page only has to mount it.
 */
export default function VerdictBanner({ playerId }: { playerId: number }) {
  const { data, isLoading, isError } = usePlayerVerdict(playerId);

  if (isLoading) return <p className="state-note">Loading verdict…</p>;
  if (isError || !data) return null;

  return (
    <section aria-label="Verdict" className="panel flex flex-col gap-sm px-md py-sm">
      <div className="flex flex-wrap items-center gap-sm">
        <VerdictChip label={data.label} size="md" />
        {data.tags.map((tag) => (
          <span
            key={tag}
            className="rounded-full border border-line px-sm py-[1px] text-xs font-semibold muted"
          >
            {tag}
          </span>
        ))}
        <span className="text-xs font-semibold muted">{data.confidence} confidence</span>
      </div>
      <p className="text-sm">{data.reason}</p>
      {data.personal && (
        <p className="flex items-center gap-xs text-sm" data-testid="personal-line">
          <span aria-hidden="true">{PERSONAL_ICON[data.personal.kind]}</span>
          {data.personal.text}
        </p>
      )}
      {!NO_CLAIM.has(data.label) &&
        (data.validation === null || data.validation.n === 0 ? (
          <p className="state-note">Not yet validated on our history — treat it as a hint.</p>
        ) : (
          !data.validation.beatsChance && (
            <p className="state-note">
              This label hasn't yet beaten chance on our history — treat it as a hint.
            </p>
          )
        ))}
    </section>
  );
}
