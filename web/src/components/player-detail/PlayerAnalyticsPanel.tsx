import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { DEFAULT_WINDOWS, fetchPlayerAnalytics, type PlayerAnalytics } from "../../api-client/analytics";
import { fetchPlayerVerdict } from "../../api-client/verdict";
import MetricCard from "../metrics/MetricCard";
import {
  buildConsistencySteps,
  buildFormSteps,
  buildMomentumSteps,
  buildOutlookSteps,
  buildPointsValueSteps,
  buildPowerSteps,
  buildReliabilitySteps,
  buildVerdictSteps,
  buildXpSteps,
} from "../metrics/steps";

/** Momentum windows the owner can toggle (ANALYTICS-02's "configurable"). */
const WINDOW_PRESETS = [1, 3, 7, 14, 30, 60];

function MomentumToggle({
  windows,
  onToggle,
}: {
  windows: number[];
  onToggle: (w: number) => void;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-sm pt-sm">
      <span className="text-xs muted">Windows</span>
      <div className="segmented" role="group" aria-label="Momentum windows">
        {WINDOW_PRESETS.map((w) => (
          <button
            key={w}
            type="button"
            aria-pressed={windows.includes(w)}
            onClick={() => onToggle(w)}
            className="tabular"
          >
            {w}d
          </button>
        ))}
      </div>
    </div>
  );
}

function Panel({
  data,
  windows,
  onToggleWindow,
}: {
  data: PlayerAnalytics;
  windows: number[];
  onToggleWindow: (w: number) => void;
}) {
  const { form, consistency, power, momentum, reliability, pointsValue, priceOutlook, xp, valuation, ranks } = data;

  const verdictQuery = useQuery({
    queryKey: ["player-verdict-card", data.playerId],
    queryFn: () => fetchPlayerVerdict(data.playerId),
    retry: false,
  });

  return (
    <div className="grid gap-md sm:grid-cols-2">
      {verdictQuery.data ? (
        (() => {
          const { steps, headline } = buildVerdictSteps(
            verdictQuery.data.label,
            verdictQuery.data.deciding,
            verdictQuery.data.reason,
          );
          return (
            <MetricCard
              metric="verdict"
              value={verdictQuery.data.label}
              word={verdictQuery.data.label}
              rank={null}
              steps={steps}
              headline={headline}
            />
          );
        })()
      ) : (
        <MetricCard
          metric="verdict"
          value={null}
          rank={null}
          steps={null}
          headline={null}
          emptyReason={verdictQuery.isError ? "Couldn't load the verdict." : "Loading…"}
        />
      )}

      {power ? (
        (() => {
          const { steps, headline, formula } = buildPowerSteps(power);
          return (
            <MetricCard
              metric="power"
              value={Math.round(power.score).toString()}
              rank={ranks?.power ?? null}
              steps={steps}
              headline={headline}
              formula={formula}
            />
          );
        })()
      ) : (
        <MetricCard
          metric="power"
          value={null}
          rank={null}
          steps={null}
          headline={null}
          emptyReason="No jornada recorded yet."
        />
      )}

      {pointsValue && pointsValue.value !== null ? (
        (() => {
          const { steps, headline, formula } = buildPointsValueSteps(
            pointsValue,
            valuation?.fairValue ?? null,
          );
          return (
            <MetricCard
              metric="pointsValue"
              value={headline.value as string}
              rank={ranks?.pointsValue ?? null}
              steps={steps}
              headline={headline}
              formula={formula}
            />
          );
        })()
      ) : (
        <MetricCard
          metric="pointsValue"
          value={null}
          rank={null}
          steps={null}
          headline={null}
          emptyReason={pointsValue?.reason ?? "Not enough data."}
        />
      )}

      {priceOutlook ? (
        (() => {
          const { steps, headline } = buildOutlookSteps(priceOutlook);
          const direction =
            priceOutlook.direction === "rise"
              ? "Rising"
              : priceOutlook.direction === "fall"
                ? "Falling"
                : "Flat";
          return (
            <MetricCard
              metric="outlook"
              value={headline.value as string}
              word={direction}
              rank={ranks?.outlook ?? null}
              steps={steps}
              headline={headline}
            />
          );
        })()
      ) : (
        <MetricCard
          metric="outlook"
          value={null}
          rank={null}
          steps={null}
          headline={null}
          emptyReason="No price outlook yet."
        />
      )}

      {reliability ? (
        (() => {
          const { steps, headline } = buildReliabilitySteps(reliability);
          return (
            <MetricCard
              metric="reliability"
              value={headline.value as string}
              word={reliability.class}
              rank={ranks?.reliability ?? null}
              steps={steps}
              headline={headline}
            />
          );
        })()
      ) : (
        <MetricCard
          metric="reliability"
          value={null}
          rank={null}
          steps={null}
          headline={null}
          emptyReason="No live inputs for this player yet."
        />
      )}

      {xp ? (
        (() => {
          const { steps, headline } = buildXpSteps(xp);
          return (
            <MetricCard
              metric="xp"
              value={headline.value as string}
              rank={ranks?.xp ?? null}
              steps={steps}
              headline={headline}
            />
          );
        })()
      ) : (
        <MetricCard
          metric="xp"
          value={null}
          rank={null}
          steps={null}
          headline={null}
          emptyReason="No prediction stored yet — it is made on the next refresh."
        />
      )}

      {form && form.value !== null ? (
        (() => {
          const { steps, headline } = buildFormSteps(form);
          return (
            <MetricCard
              metric="form"
              value={headline.value as string}
              rank={ranks?.form ?? null}
              steps={steps}
              headline={headline}
            />
          );
        })()
      ) : (
        <MetricCard
          metric="form"
          value={null}
          rank={null}
          steps={null}
          headline={null}
          emptyReason="No jornada recorded yet."
        />
      )}

      {consistency && consistency.value !== null && consistency.jornadas > 0 ? (
        (() => {
          const { steps, headline, formula } = buildConsistencySteps(consistency);
          return (
            <MetricCard
              metric="consistency"
              value={headline.value as string}
              rank={ranks?.consistency ?? null}
              steps={steps}
              headline={headline}
              formula={formula}
            />
          );
        })()
      ) : (
        <MetricCard
          metric="consistency"
          value={null}
          rank={null}
          steps={null}
          headline={null}
          emptyReason="No jornada recorded yet."
        />
      )}

      {(() => {
        const { steps, headline } = buildMomentumSteps(momentum);
        const sevenDay = momentum.find((m) => m.windowDays === 7) ?? null;
        return (
          <MetricCard
            metric="momentum"
            value={sevenDay ? headline.value as string : null}
            rank={ranks?.momentum7 ?? null}
            steps={sevenDay ? steps : null}
            headline={sevenDay ? headline : null}
            emptyReason="Enable the 7-day window below to see this."
          >
            <MomentumToggle windows={windows} onToggle={onToggleWindow} />
          </MetricCard>
        );
      })()}
    </div>
  );
}

export default function PlayerAnalyticsPanel({ playerId }: { playerId: number }) {
  const [windows, setWindows] = useState<number[]>(DEFAULT_WINDOWS);
  const { data, isLoading, isError } = useQuery({
    queryKey: ["player-analytics", playerId, windows],
    queryFn: () => fetchPlayerAnalytics(playerId, windows),
  });

  function toggle(w: number) {
    setWindows((current) => {
      const next = current.includes(w) ? current.filter((x) => x !== w) : [...current, w];
      return next.length === 0 ? current : next.sort((a, b) => a - b);
    });
  }

  return (
    <section aria-labelledby="analytics-heading" className="flex flex-col gap-md">
      <h2 id="analytics-heading" className="section-title">
        Analytics
      </h2>
      {isLoading && <p className="state-note">Loading analytics…</p>}
      {isError && <p className="state-error">Couldn't load analytics.</p>}
      {data && <Panel data={data} windows={windows} onToggleWindow={toggle} />}
    </section>
  );
}
