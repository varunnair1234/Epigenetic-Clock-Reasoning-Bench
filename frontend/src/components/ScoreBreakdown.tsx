import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { LeaderboardRow } from "../types";

const TASKS = ["A", "B", "C", "D"];
const MODEL_COLORS: Record<string, string> = {
  claude: "#10b981",
  gemini: "#60a5fa",
  biollm: "#a78bfa",
};
const MODEL_LABELS: Record<string, string> = {
  claude: "Claude Sonnet 4.6",
  gemini: "Gemini Flash",
  biollm: "BioLLM (Longevity-Tuned)",
};

export default function ScoreBreakdown() {
  const [rows, setRows] = useState<LeaderboardRow[]>([]);
  useEffect(() => { api.leaderboard().then(d => setRows(d.rows)).catch(() => {}); }, []);

  // Build model × task matrix
  const byModelTask = useMemo(() => {
    const out: Record<string, Record<string, number>> = {};
    for (const r of rows) {
      if (r.task_type === "ALL") continue;
      const letter = (r.task_type || "?").charAt(0).toUpperCase();
      if (!out[r.model]) out[r.model] = {};
      out[r.model][letter] = r.pct;
    }
    return out;
  }, [rows]);

  const models = Object.keys(byModelTask).sort();
  const maxPct = 100;

  // Identify the only task type where a non-leader wins (for the trophy marker).
  const leader = models[0];  // alphabetical fallback; better: by overall
  const winnerByTask: Record<string, string> = {};
  for (const t of TASKS) {
    let best = "", bestPct = -1;
    for (const m of models) {
      const p = byModelTask[m][t] ?? 0;
      if (p > bestPct) { bestPct = p; best = m; }
    }
    winnerByTask[t] = best;
  }
  const upsetTask = TASKS.find(t => winnerByTask[t] !== leader);

  return (
    <section className="mb-16">
      <div className="section-label mb-1">SECTION 05</div>
      <h2 className="text-3xl font-bold mb-6">Score breakdown</h2>

      <div className="panel">
        <div className="flex items-center justify-between mb-4">
          <div className="text-sm font-medium">Accuracy by task type</div>
          {upsetTask && (
            <div className="bg-amber-900/30 border border-amber-700/50 text-amber-300 text-xs px-3 py-1.5 rounded-md">
              🏆 Only category where {MODEL_LABELS[winnerByTask[upsetTask]] ?? winnerByTask[upsetTask]} leads: Type {upsetTask}
            </div>
          )}
        </div>

        <div className="relative h-80 mt-2">
          {/* Y-axis ticks */}
          <div className="absolute left-0 top-0 bottom-8 w-8 flex flex-col justify-between text-xs text-zinc-500 text-right pr-2">
            {[100, 75, 50, 25, 0].map(v => <div key={v}>{v}</div>)}
          </div>

          {/* Plot area */}
          <div className="ml-8 h-full relative border-b border-zinc-700">
            {/* Gridlines */}
            {[25, 50, 75].map(v => (
              <div key={v}
                   className="absolute left-0 right-0 border-t border-zinc-800"
                   style={{ top: `${100 - v}%` }} />
            ))}

            {/* Bars per task type */}
            <div className="absolute inset-0 flex justify-around items-end pb-8 px-4">
              {TASKS.map(t => (
                <div key={t} className="flex items-end gap-1 h-full">
                  {models.map(m => {
                    const pct = byModelTask[m][t] ?? 0;
                    const height = Math.max((pct / maxPct) * 100, 0);
                    return (
                      <div key={m} className="flex flex-col items-center justify-end h-full relative">
                        {winnerByTask[t] === m && upsetTask === t && (
                          <div className="text-amber-400 text-base absolute"
                               style={{ bottom: `calc(${height}% + 4px)` }}>
                            🏆
                          </div>
                        )}
                        <div
                          className="w-12 transition-all"
                          style={{ height: `${height}%`, background: MODEL_COLORS[m] ?? "#888" }}
                          title={`${MODEL_LABELS[m] ?? m}: ${pct.toFixed(1)}%`}
                        />
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>

            {/* X-axis labels */}
            <div className="absolute left-0 right-0 bottom-0 flex justify-around text-xs text-zinc-400 px-4">
              {TASKS.map(t => <span key={t}>Type {t}</span>)}
            </div>
          </div>
        </div>

        {/* Legend */}
        <div className="flex justify-center gap-6 mt-4 text-xs">
          {models.map(m => (
            <span key={m} className="flex items-center gap-2 text-zinc-300">
              <span className="inline-block w-3 h-3 rounded"
                    style={{ background: MODEL_COLORS[m] ?? "#888" }} />
              {MODEL_LABELS[m] ?? m}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
