import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchLeagueSettings,
  saveLeagueSettings,
  type LeagueSettings,
} from "../api-client/league-settings";
import EmptyState from "../components/EmptyState";
import PageHeader from "../components/ui/PageHeader";

// Labels are the bare nouns ("Formations", "Bench"), not "Premium X" — the
// page title and intro paragraph already establish that both are Premium
// features a league admin switches on, so repeating "Premium" on every row
// would be redundant, not clearer. This is a deliberate copy decision, not
// an oversight.
const TOGGLES: { key: keyof LeagueSettings; label: string; help: string }[] = [
  {
    key: "premiumFormationsEnabled",
    label: "Formations",
    help: "Adds 3-3-4, 3-6-1, 4-2-4, 4-6-0 and 5-2-3 to the formations you can field.",
  },
  {
    key: "premiumBenchEnabled",
    label: "Bench",
    help: "Lets you name up to four substitutes, one per position your formation fields.",
  },
];

/**
 * The league's Premium settings.
 *
 * These mirror what a league admin has switched on — the app cannot detect
 * them, so it asks. Each is independent (LN-29); one master switch would
 * misrepresent how the real game works.
 */
export default function SettingsPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["league-settings"],
    queryFn: fetchLeagueSettings,
  });

  const mutation = useMutation({
    // Wrapped rather than passed directly: this react-query version calls
    // mutationFn(variables, context) with a second context argument, which
    // saveLeagueSettings does not accept and callers should not see.
    mutationFn: (settings: LeagueSettings) => saveLeagueSettings(settings),
    onSuccess: (saved) => {
      queryClient.setQueryData(["league-settings"], saved);
      // The formations the editor offers and the shapes the squad page
      // calls reachable both follow these flags.
      queryClient.invalidateQueries({ queryKey: ["squad"] });
    },
  });

  if (isLoading) {
    return <p className="state-note">Loading settings…</p>;
  }
  if (isError || !data) {
    return <EmptyState heading="Couldn&apos;t load your settings" body="Try again in a moment." />;
  }

  return (
    <section className="flex w-full max-w-[44rem] flex-col gap-lg">
      <PageHeader
        title="Settings"
        subtitle="Premium features are switched on per league by its admin, and the app has no way to detect them — so tell it what your league has. Turning one off narrows what you can field from now on; it never rearranges the team you have already set."
      />

      <ul className="flex flex-col gap-sm">
        {TOGGLES.map(({ key, label, help }) => (
          <li key={key} className="panel px-md py-md">
            <label className="flex cursor-pointer items-start gap-md text-[15px] font-semibold">
              <input
                type="checkbox"
                checked={data[key]}
                disabled={mutation.isPending}
                onChange={(event) =>
                  mutation.mutate({ ...data, [key]: event.target.checked })
                }
                className="mt-[3px]"
              />
              <span>
                {label}
                <span className="block pt-[2px] text-sm font-normal muted">
                  {help}
                </span>
              </span>
            </label>
          </li>
        ))}
      </ul>

      {mutation.isError && (
        <p role="alert" className="state-error">
          Couldn&apos;t save that setting.
        </p>
      )}
    </section>
  );
}
