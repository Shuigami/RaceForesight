const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export type MeetingSummary = {
  meeting_key: number;
  meeting_name: string;
  circuit_short_name: string;
  country_name: string;
  year: number;
  date_start: string | null;
  is_default: boolean;
  race_laps: number;
};

export type StintPlan = {
  compound: string;
  lap_start: number;
  lap_end: number;
  tyre_age_at_start: number;
};

export type DriverStrategy = {
  driver_number: number;
  name_acronym: string;
  full_name: string;
  team_name: string;
  team_colour: string | null;
  stops: number;
  compounds: string[];
  pit_laps: number[];
  stints: StintPlan[];
  predicted_race_time_s: number;
  predicted_avg_lap_s: number | null;
  strategy_label: string;
};

export type StrategyResponse = {
  meeting: MeetingSummary;
  drivers: DriverStrategy[];
  model_version: string;
  generated_at: string;
};

export type StrategyDetail = {
  meeting: MeetingSummary;
  best: DriverStrategy;
  alternatives: DriverStrategy[];
  degradation_curve: { tyre_age: number; predicted_lap_s: number; compound: string }[];
  model_version: string;
};

export type PredictedFinish = {
  position: number;
  driver_number: number;
  name_acronym: string;
  full_name: string;
  team_name: string;
  team_colour: string | null;
  estimated_race_time_s: number | null;
  gap_to_leader_s: number | null;
  strategy_label: string | null;
  confidence: number | null;
};

export type ClassificationResponse = {
  meeting: MeetingSummary;
  standings: PredictedFinish[];
  model_version: string;
  generated_at: string;
  note: string;
};

export type ModelScore = {
  name: string;
  kind: string;
  version: string;
  primary: boolean;
  metrics: Record<string, number | string | null>;
  description: string;
};

export type ModelsMetricsResponse = {
  generated_at: string;
  models: ModelScore[];
  evaluation_races: number;
  notes: string[];
};

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

async function postJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method: "POST", cache: "no-store" });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export function fetchRaces() {
  return getJson<MeetingSummary[]>("/api/races");
}

export function fetchStrategy(meetingKey: number) {
  return getJson<StrategyResponse>(`/api/races/${meetingKey}/strategy`);
}

export function fetchDriverStrategy(meetingKey: number, driverNumber: number) {
  return getJson<StrategyDetail>(`/api/races/${meetingKey}/strategy/${driverNumber}`);
}

export function fetchPrediction(meetingKey: number) {
  return getJson<ClassificationResponse>(`/api/races/${meetingKey}/prediction`);
}

export function fetchModelMetrics() {
  return getJson<ModelsMetricsResponse>("/api/models/metrics");
}

export function runModelEvaluation() {
  return postJson<ModelsMetricsResponse>("/api/models/evaluate?years=2024,2025&max_sessions=12&ranking_races=6");
}

export function formatRaceTime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) {
    return `${h}:${String(m).padStart(2, "0")}:${s.toFixed(3).padStart(6, "0")}`;
  }
  return `${m}:${s.toFixed(3).padStart(6, "0")}`;
}

export function compoundColor(compound: string): string {
  switch (compound.toUpperCase()) {
    case "SOFT":
      return "#e10600";
    case "MEDIUM":
      return "#f5d90a";
    case "HARD":
      return "#f2f2f2";
    case "INTERMEDIATE":
      return "#43b02a";
    case "WET":
      return "#00a0e2";
    default:
      return "#888";
  }
}
