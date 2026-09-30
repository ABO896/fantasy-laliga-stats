import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import VerdictStrip from "./VerdictStrip";
import type { LatestSnapshot } from "../../api-client/player-detail";

const LATEST: LatestSnapshot = {
  marketValue: 18_400_000,
  idealBid: null,
  maxBid: null,
  priceChangeAbs: 320_000,
  priceChangePct: 1.8,
  points: 12,
  pricePerPoint: 1.53,
  starterProbability: 0.87,
  availabilityStatus: "available",
  nextOpponent: "GET",
};

describe("VerdictStrip", () => {
  it("leads with the current value and its direction", () => {
    render(<VerdictStrip latest={LATEST} squad={null} predictions={{}} />);
    expect(screen.getByText(/18\.4/)).toBeInTheDocument();
    expect(screen.getByText(/▲/)).toBeInTheDocument();
  });

  it("names the purchase when the player is owned", () => {
    render(
      <VerdictStrip
        latest={LATEST}
        squad={{ purchasePrice: 17_900_000, acquiredOn: "2026-08-12" }}
        predictions={{}}
      />,
    );
    expect(screen.getByText(/owned/i)).toBeInTheDocument();
    expect(screen.getByText(/17\.9/)).toBeInTheDocument();
  });

  it("says nothing about ownership when the player is not owned", () => {
    render(<VerdictStrip latest={LATEST} squad={null} predictions={{}} />);
    expect(screen.queryByText(/owned/i)).not.toBeInTheDocument();
  });

  it("renders an em dash rather than a number when efficiency is unavailable", () => {
    render(
      <VerdictStrip latest={{ ...LATEST, pricePerPoint: null }} squad={null} predictions={{}} />,
    );
    expect(screen.getByTestId("price-per-point")).toHaveTextContent("—");
  });

  it("renders price/point as an abbreviated euro value, not a raw number", () => {
    // Regression: the raw stat is stored as a large float (e.g. a market
    // value divided down to price-per-point), and printing it bare put
    // "4815545.07" on screen next to a correctly formatted market value in
    // the same strip. It must render the same way the player table renders
    // this exact statistic.
    render(
      <VerdictStrip
        latest={{ ...LATEST, pricePerPoint: 4_815_545.07 }}
        squad={null}
        predictions={{}}
      />,
    );
    expect(screen.getByTestId("price-per-point")).toHaveTextContent("€4.82M");
    expect(screen.queryByText(/4815545/)).not.toBeInTheDocument();
  });

  it("omits the prediction entirely when none is stored", () => {
    render(<VerdictStrip latest={LATEST} squad={null} predictions={{}} />);
    expect(screen.queryByText(/predicted/i)).not.toBeInTheDocument();
  });

  it("shows a stored points prediction as the source's, not ours", () => {
    render(<VerdictStrip latest={LATEST} squad={null} predictions={{ points: 4.2 }} />);
    expect(screen.getByText(/4\.2/)).toBeInTheDocument();
  });

  it("degrades to a stated absence when there is no snapshot at all", () => {
    render(<VerdictStrip latest={null} squad={null} predictions={{}} />);
    expect(screen.getByText(/no market data/i)).toBeInTheDocument();
  });
});
