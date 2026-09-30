import { apiFetch } from "./client";

export interface SeasonsResponse {
  seasons: number[];
  /** Highest stored jornada per season, keyed by season as a string
   * (JSON object keys) — the shared `maxWeek` source for the Scores and
   * Streaks tabs' jornada/window selectors. */
  seasonWeekRanges: Record<string, number>;
}

export interface JornadaScoreRow {
  playerId: number;
  name: string;
  team: string;
  position: string;
  points: number;
  /** Current market value — `null` if the player has no snapshot yet. */
  marketValue: number | null;
  /** Season price/point efficiency, not this jornada's own points —
   * `null` if there's no snapshot, or the source hasn't published a figure. */
  pricePerPoint: number | null;
}

export interface TierBucket {
  label: string;
  min: number | null;
  max: number | null;
  count: number;
}

export interface TeamJornadaRow {
  team: string;
  totalPoints: number;
  playerCount: number;
  averagePoints: number;
}

export interface ScoresResponse {
  week: number;
  isProvisional: boolean;
  tiers: TierBucket[];
  scores: JornadaScoreRow[];
  teams: TeamJornadaRow[];
}

export interface StreakRow {
  playerId: number;
  name: string;
  team: string;
  position: string;
  totalPoints: number;
  weeksCounted: number;
}

export interface StreaksResponse {
  endWeek: number;
  window: number;
  players: StreakRow[];
}

export interface JornadaRecordRow {
  playerId: number;
  name: string;
  team: string;
  week: number;
  points: number;
}

export interface SeasonRecordRow {
  field: string;
  playerId: number;
  name: string;
  team: string;
  value: number;
}

export interface RecordsResponse {
  jornadaRecords: JornadaRecordRow[];
  seasonRecords: SeasonRecordRow[];
}

export interface LeaderboardRow {
  playerId: number;
  name: string;
  team: string;
  position: string;
  value: number;
  totalPoints: number;
}

export interface LeaderboardResponse {
  stat: string;
  players: LeaderboardRow[];
}

export function fetchStatsSeasons(): Promise<SeasonsResponse> {
  return apiFetch<SeasonsResponse>("/stats/seasons");
}

export function fetchJornadaScores(season: number, week: number): Promise<ScoresResponse> {
  return apiFetch<ScoresResponse>(`/stats/scores?season=${season}&week=${week}`);
}

export function fetchStreaks(season: number, endWeek: number, window: number): Promise<StreaksResponse> {
  return apiFetch<StreaksResponse>(
    `/stats/streaks?season=${season}&end_week=${endWeek}&window=${window}`,
  );
}

export function fetchRecords(season: number): Promise<RecordsResponse> {
  return apiFetch<RecordsResponse>(`/stats/records?season=${season}`);
}

export function fetchLeaderboard(
  season: number,
  stat: string,
  position: string | null,
  team: string | null,
): Promise<LeaderboardResponse> {
  const params = new URLSearchParams({ season: String(season), stat });
  if (position) params.set("position", position);
  if (team) params.set("team", team);
  return apiFetch<LeaderboardResponse>(`/stats/leaderboard?${params.toString()}`);
}
