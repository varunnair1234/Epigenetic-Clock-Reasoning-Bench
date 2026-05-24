import type {
  Stats, SimulateResponse, LeaderboardRow, ErrorBreakdownRow, BenchmarkScenario,
} from "./types";

const BASE = "";  // Vite proxy forwards /api/* → FastAPI on :8000

async function get<T>(path: string): Promise<T> {
  const res = await fetch(BASE + path);
  if (!res.ok) throw new Error(`${path} → ${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  stats:           () => get<Stats>("/api/stats"),
  simulate:        (seed = 7, steps = 200) =>
                    get<SimulateResponse>(`/api/simulate?seed=${seed}&steps=${steps}`),
  leaderboard:     () => get<{ rows: LeaderboardRow[] }>("/api/leaderboard"),
  benchmark:       (params: { limit?: number; task_type?: string; status?: string } = {}) => {
                    const q = new URLSearchParams();
                    if (params.limit) q.set("limit", String(params.limit));
                    if (params.task_type) q.set("task_type", params.task_type);
                    if (params.status) q.set("status", params.status);
                    return get<{ total: number; scenarios: BenchmarkScenario[] }>(
                      `/api/benchmark?${q.toString()}`
                    );
                  },
  errorBreakdown:  () => get<{ rows: ErrorBreakdownRow[] }>("/api/error_breakdown"),
};
