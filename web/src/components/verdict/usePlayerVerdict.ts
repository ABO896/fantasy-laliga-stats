import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { fetchPlayerVerdict } from "../../api-client/verdict";

/** Mirrors `TransfersPage.tsx`'s own `parseMax` — an absent or malformed
 * `?max=` degrades to "no ceiling", never to `NaN`. */
function parseMax(raw: string | null): number | null {
  if (raw === null || raw.trim() === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

/** The player page's one verdict query — the banner and the verdict card
 * both read it, so the page fetches `/players/{id}/verdict` once. The
 * ceiling comes from the URL's `?max=` (BROWSE-05), like everywhere else. */
export function usePlayerVerdict(playerId: number) {
  const [searchParams] = useSearchParams();
  const max = parseMax(searchParams.get("max"));
  return useQuery({
    queryKey: ["player-verdict", playerId, max],
    queryFn: () => fetchPlayerVerdict(playerId, max),
    retry: false,
    // The card mounts after the analytics load; without this its observer
    // would refetch the banner's fresh result. Verdicts move once a day.
    staleTime: 60_000,
  });
}
