import { useQuery } from "@tanstack/react-query";
import { fetchPlayerBid } from "../../api-client/transfers";
import { euro, muted } from "./shared";

/** MODEL-05 on the player page: our ideal and maximum bid beside the
 * source's. Self-contained (own query) so the page only mounts it. */
export default function OurBidCard({ playerId }: { playerId: number }) {
  const { data, isError } = useQuery({
    queryKey: ["transfers", "bid", playerId],
    queryFn: () => fetchPlayerBid(playerId),
    retry: false,
  });
  if (isError || !data) return null;
  return (
    <section
      aria-label="Our bid"
      className="panel flex flex-wrap items-baseline gap-x-lg gap-y-xs border-l-4 border-l-[color:var(--color-accent)] px-md py-sm text-sm"
    >
      <span className="subsection-title">Our bid</span>
      <span>
        ideal <strong className="font-[family-name:var(--font-display)] text-[20px] tabular-nums">{euro(data.ourIdeal)}</strong>
      </span>
      <span>
        max <strong className="font-[family-name:var(--font-display)] text-[20px] tabular-nums">{euro(data.ourMax)}</strong>
      </span>
      <span className={muted}>
        source {euro(data.sourceIdeal)} / {euro(data.sourceMax)} · market value{" "}
        {euro(data.marketValue)}
        {data.freshness.reasons.length > 0 && ` · ${data.freshness.reasons[0]}`}
      </span>
    </section>
  );
}
