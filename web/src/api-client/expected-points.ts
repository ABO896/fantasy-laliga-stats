import { apiFetch } from "./client";

/** MODEL-02 — one stored expected-points prediction, with every input and
 * term it was built from (ANALYTICS-05). `basis` says what it was built
 * from; xP deliberately has no confidence grade (that vocabulary belongs to
 * the market model). */
export interface ExpectedPointsInputs {
  modelVersion: string;
  position?: string;
  rate?: {
    value: number;
    matches: number;
    recentPoints: number[];
    halfLife: number;
    prior: number;
    priorSource: "last_season" | "position";
    priorWeight: number;
  };
  starterProbability?: number | null;
  availability?: string | null;
  fixture: {
    opponent: string;
    isHome: boolean;
    teamGoals: number | null;
    cleanSheet: number | null;
    oddsSource: string | null;
  } | null;
  terms?: Record<string, number>;
  naiveSeasonAverage?: number | null;
}

export interface ExpectedPointsPrediction {
  playerId: number;
  seasonYear: number;
  jornada: number;
  expectedPoints: number;
  basis: string;
  opponent: string | null;
  isHome: boolean | null;
  locksAt: string | null;
  updatedAt: string;
  modelVersion: string;
  inputs: ExpectedPointsInputs;
}

export interface PlayerExpectedPoints {
  playerId: number;
  prediction: ExpectedPointsPrediction | null;
}

export function fetchPlayerExpectedPoints(playerId: number): Promise<PlayerExpectedPoints> {
  return apiFetch<PlayerExpectedPoints>(`/players/${playerId}/expected-points`);
}

const BASIS_LABELS: Record<string, string> = {
  form: "recent points only",
  "form+starter": "recent points + starter probability",
  "form+odds": "recent points + match odds",
  "form+starter+odds": "recent points + starter probability + match odds",
  no_fixture: "his team has no fixture this jornada",
};

export function describeBasis(basis: string | null | undefined): string {
  if (!basis) return "no prediction yet";
  return BASIS_LABELS[basis] ?? basis;
}
