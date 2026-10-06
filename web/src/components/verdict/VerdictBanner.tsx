import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { fetchPlayerVerdict, type PersonalLine } from "../../api-client/verdict";
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

/** Mirrors `TransfersPage.tsx`'s own `parseMax` — an absent or malformed
 * `?max=` degrades to "no ceiling", never to `NaN`. */
function parseMax(raw: string | null): number | null {
  if (raw === null || raw.trim() === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

/**
 * The player page's decision-first banner (Plan C, Task 6). Fetches its
 * own verdict — label, tags, reason, confidence, the personal line read
 * against the owner's squad, and whether the walk-forward harness has
 * shown this label beats chance — so the page only has to mount it.
 */
export default function VerdictBanner({ playerId }: { playerId: number }) {
  const [searchParams] = useSearchParams();
  const max = parseMax(searchParams.get("max"));

  const { data, isLoading, isError } = useQuery({
    queryKey: ["player-verdict", playerId, max],
    queryFn: () => fetchPlayerVerdict(playerId, max),
    retry: false,
  });

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
      {data.validation && !data.validation.beatsChance && (
        <p className="state-note">
          This label hasn't yet beaten chance on our history — treat it as a hint.
        </p>
      )}
    </section>
  );
}
