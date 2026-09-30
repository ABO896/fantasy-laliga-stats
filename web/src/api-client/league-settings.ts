import { apiFetch } from "./client";

const API_BASE_URL = "http://127.0.0.1:8000/api";

/** The league's two Premium toggles. Independent settings (LN-29), not
 * one master switch — a league admin turns each on separately. */
export interface LeagueSettings {
  premiumFormationsEnabled: boolean;
  premiumBenchEnabled: boolean;
}

export function fetchLeagueSettings(): Promise<LeagueSettings> {
  return apiFetch<LeagueSettings>("/league-settings");
}

/** Always sends both flags. A partial update would let this client
 * silently switch off a flag it does not yet know about. */
export async function saveLeagueSettings(settings: LeagueSettings): Promise<LeagueSettings> {
  const response = await fetch(`${API_BASE_URL}/league-settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
  if (!response.ok) {
    throw new Error(`Couldn't save league settings (status ${response.status})`);
  }
  return (await response.json()) as LeagueSettings;
}
