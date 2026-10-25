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

export type GlobalStrategy = {
  rank: number;
  stops: number;
  compounds: string[];
  pit_laps: number[];
  pit_windows: number[][];
  stints: StintPlan[];
  predicted_race_time_s: number;
  predicted_avg_lap_s: number | null;
  strategy_label: string;
  gap_to_best_s: number;
};

export function formatPitWindows(windows: number[][] | undefined, fallbackLaps: number[]): string {
  const src = windows?.length ? windows : fallbackLaps.map((lap) => [lap, lap]);
  return src
    .map(([lo, hi]) => (lo === hi ? String(lo) : `${lo}–${hi}`))
    .join(", ");
}

export type ActualDriverStrategy = {
  driver_number: number;
  stops: number;
  compounds: string[];
  pit_laps: number[];
  stints: StintPlan[];
  strategy_label: string;
};

export type StrategyResponse = {
  meeting: MeetingSummary;
  strategies: GlobalStrategy[];
  actual?: ActualDriverStrategy[];
  model_version: string;
  generated_at: string;
};

export type PacePoint = {
  lap_number: number;
  tyre_age: number;
  fuel_proxy: number;
  predicted_lap_s: number;
  tyre_effect_s: number;
  tyre_degradation_pct: number;
  tyre_life_used_pct: number;
  compound: string;
};

export type StintPaceCurve = {
  stint_index: number;
  compound: string;
  lap_start: number;
  lap_end: number;
  points: PacePoint[];
};

export type StrategyOption = {
  strategy: DriverStrategy;
  stint_curves: StintPaceCurve[];
  is_recommended: boolean;
};

export type StrategyDetail = {
  meeting: MeetingSummary;
  best: DriverStrategy;
  alternatives: DriverStrategy[];
  degradation_curve: PacePoint[];
  stint_curves: StintPaceCurve[];
  options: StrategyOption[];
  actual?: ActualDriverStrategy | null;
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

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    cache: "no-store",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

async function patchJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "PATCH",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

async function deleteJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method: "DELETE", cache: "no-store" });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `Request failed (${res.status})`);
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
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

export function fetchRaceTime(meetingKey: number) {
  return getJson<ClassificationResponse>(`/api/races/${meetingKey}/race-time`);
}

export function fetchModelMetrics() {
  return getJson<ModelsMetricsResponse>("/api/models/metrics");
}

export function runModelEvaluation() {
  return postJson<ModelsMetricsResponse>(
    "/api/models/evaluate?years=2025,2026&max_sessions=40&ranking_races=8",
  );
}

export type LockStatus =
  | "locked_before_start"
  | "overwritten_after_start"
  | "saved_after_start"
  | "awaiting_race_start";

export type PredictionMeetingListItem = {
  meeting_key: number;
  meeting_name: string;
  year: number | null;
  circuit_short_name: string | null;
  first_saved_at: string | null;
  saved_at: string | null;
  race_start_at: string | null;
  save_count: number;
  has_actual: boolean;
  status: "awaiting_race" | "scored";
};

export type PredictionSaveListItem = {
  id: string;
  name: string;
  meeting_key: number;
  meeting_name: string;
  year: number | null;
  circuit_short_name: string | null;
  first_saved_at: string | null;
  saved_at: string | null;
  race_start_at: string | null;
  has_actual: boolean;
  lock_status: LockStatus;
  status: "awaiting_race" | "scored";
};

export type PredictionSnapshot = {
  id: string;
  name: string;
  meeting: MeetingSummary;
  race_start_at: string | null;
  first_saved_at: string;
  saved_at: string;
  model_versions: {
    classification: string;
    race_time: string;
    strategy: string;
  };
  classification: { standings: PredictedFinish[]; note: string };
  race_time: { standings: PredictedFinish[]; note: string };
  strategy: { strategies: GlobalStrategy[] };
};

export type ActualFinishRow = {
  position: number;
  driver_number: number;
  duration_s: number | null;
};

export type PredictionCompareResponse = {
  snapshot: PredictionSnapshot;
  lock_status: LockStatus;
  status: "awaiting_race" | "scored";
  overwritten: boolean;
  actual_finishes: ActualFinishRow[];
  actual_strategies: ActualDriverStrategy[];
  metrics: {
    classification: Record<string, number | null>;
    race_time: Record<string, number | null>;
    strategy: Record<string, number | null>;
  } | null;
};

export function fetchSavedPredictions() {
  return getJson<PredictionMeetingListItem[]>("/api/predictions");
}

export function fetchMeetingSaves(meetingKey: number) {
  return getJson<PredictionSaveListItem[]>(`/api/predictions/${meetingKey}/saves`);
}

export function savePredictions(meetingKey: number, name?: string) {
  return postJson<PredictionCompareResponse>(
    `/api/predictions/${meetingKey}/save`,
    name ? { name } : undefined,
  );
}

export function fetchPredictionCompare(meetingKey: number, saveId: string) {
  return getJson<PredictionCompareResponse>(
    `/api/predictions/${meetingKey}/saves/${saveId}/compare`,
  );
}

export function renamePredictionSave(meetingKey: number, saveId: string, name: string) {
  return patchJson<PredictionSaveListItem>(
    `/api/predictions/${meetingKey}/saves/${saveId}`,
    { name },
  );
}

export function deletePredictionSave(meetingKey: number, saveId: string) {
  return deleteJson<{ ok: boolean }>(`/api/predictions/${meetingKey}/saves/${saveId}`);
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
