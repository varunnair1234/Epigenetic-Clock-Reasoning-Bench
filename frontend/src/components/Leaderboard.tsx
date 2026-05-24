import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { LeaderboardRow } from "../types";

const TASK_LETTERS = ["A", "B", "C", "D"];

interface ModelRow {
  model: string;
  overall_pct: number;
  task_pcts: Record<string, number>;
  parse_fails: number;
  total_scenarios: number;
}

function aggregate(rows: LeaderboardRow[]): ModelRow[] {
  const byModel: Record<string, ModelRow> = {};
  for (const r of rows) {
    if (!byModel[r.model]) {
      byModel[r.model] = {
        model: r.model,
        overall_pct: 0,
        task_pcts: {},
        parse_fails: 0,
        total_scenarios: 0,
      };
    }
    const m = byModel[r.model];
    if (r.task_type === "ALL") {
      m.overall_pct = r.pct;
      m.parse_fails += r.parse_fails;
      m.total_scenarios = r.n_scenarios;
    } else {
      const letter = (r.task_type || "?").charAt(0).toUpperCase();
      m.task_pcts[letter] = r.pct;
    }
  }
  return Object.values(byModel).sort((a, b) => b.overall_pct - a.overall_pct);
}

function colorClass(pct: number): string {
  if (pct >= 75) return "text-emerald-400";
  if (pct >= 60) return "text-amber-300";
  if (pct >= 40) return "text-orange-400";
  return "text-rose-400";
}

const MODEL_LABELS: Record<string, string> = {
  claude: "Claude Sonnet 4.6",
  gemini: "Gemini Flash",
  biollm: "BioLLM (Longevity-Tuned)",
};

export default function Leaderboard() {
  const [rows, setRows] = useState<LeaderboardRow[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.leaderboard()
      .then(d => setRows(d.rows))
      .catch(e => setErr(String(e)));
  }, []);

  const models = useMemo(() => aggregate(rows), [rows]);

  return (
    <section className="mb-16">
      <div className="section-label mb-1">SECTION 03</div>
      <h2 className="text-3xl font-bold mb-6">Leaderboard</h2>

      {err && (
        <div className="panel text-rose-400 text-sm">{err}</div>
      )}
      {!err && models.length === 0 && (
        <div className="panel text-zinc-500 text-sm">
          No leaderboard rows yet. Run <code>python -m eval.run_eval</code>.
        </div>
      )}
      {models.length > 0 && (
        <div className="panel p-0 overflow-hidden">
          <table className="w-full">
            <thead className="bg-zinc-900/80 text-xs tracking-widest text-zinc-500">
              <tr>
                <th className="px-4 py-3 text-left">RANK</th>
                <th className="px-4 py-3 text-left">MODEL</th>
                <th className="px-4 py-3 text-right">OVERALL</th>
                {TASK_LETTERS.map(t => (
                  <th key={t} className="px-4 py-3 text-right">TYPE {t}</th>
                ))}
                <th className="px-4 py-3 text-right">PARSE FAILS</th>
              </tr>
            </thead>
            <tbody>
              {models.map((m, i) => (
                <tr key={m.model} className="border-t border-zinc-800">
                  <td className="px-4 py-4 text-zinc-500">
                    <span className={i === 0 ? "border-l-2 border-emerald-500 pl-2" : "pl-2"}>
                      #{i + 1}
                    </span>
                  </td>
                  <td className="px-4 py-4 font-medium">
                    {MODEL_LABELS[m.model] ?? m.model}
                  </td>
                  <td className={`px-4 py-4 text-right font-mono ${colorClass(m.overall_pct)}`}>
                    {m.overall_pct.toFixed(1)}%
                  </td>
                  {TASK_LETTERS.map(t => (
                    <td key={t}
                        className={`px-4 py-4 text-right font-mono ${colorClass(m.task_pcts[t] ?? 0)}`}>
                      {m.task_pcts[t] !== undefined ? `${m.task_pcts[t].toFixed(1)}%` : "—"}
                    </td>
                  ))}
                  <td className={`px-4 py-4 text-right font-mono ${m.parse_fails > 0 ? "text-rose-400" : "text-zinc-500"}`}>
                    {m.parse_fails}/{m.total_scenarios}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {models.length >= 2 && <LeaderboardInsight models={models} />}
    </section>
  );
}

function LeaderboardInsight({ models }: { models: ModelRow[] }) {
  // Find a category where the #2 model beats the #1 model — surprising finding.
  const top = models[0];
  const others = models.slice(1);
  for (const letter of TASK_LETTERS) {
    for (const other of others) {
      const topPct = top.task_pcts[letter];
      const otherPct = other.task_pcts[letter];
      if (topPct !== undefined && otherPct !== undefined && otherPct > topPct) {
        return (
          <div className="mt-4 panel border-l-4 border-amber-500 text-sm">
            <span className="text-amber-300">⚡ Key Finding:</span>{" "}
            {MODEL_LABELS[other.model] ?? other.model} outperforms {MODEL_LABELS[top.model] ?? top.model} on Type {letter}
            {" "}({otherPct.toFixed(1)}% vs {topPct.toFixed(1)}%), suggesting
            domain-specific training advantages on this task category — despite
            {" "}{MODEL_LABELS[top.model] ?? top.model}'s superior overall performance.
          </div>
        );
      }
    }
  }
  return null;
}
