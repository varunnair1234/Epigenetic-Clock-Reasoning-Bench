import { useEffect, useState } from "react";
import { api } from "../api";
import type { Stats } from "../types";
import LaymanExplanation from "./LaymanExplanation";

export default function Hero() {
  const [stats, setStats] = useState<Stats | null>(null);
  useEffect(() => { api.stats().then(setStats).catch(() => {}); }, []);

  return (
    <section className="mb-16">
      <div className="text-emerald-400 text-xs font-bold tracking-widest mb-2">
        ● LIVE BENCHMARK
      </div>
      <h1 className="text-5xl md:text-6xl font-extrabold mb-3 tracking-tight">
        Epigenetic Clock Reasoning Bench
      </h1>
      <p className="text-zinc-400 mb-8 text-sm md:text-base">
        Testing LLM reasoning about biological aging
      </p>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Stat label="Total scenarios"   value={stats?.n_scenarios ?? "—"} />
        <Stat label="Models evaluated"  value={stats?.n_models ?? "—"} />
        <Stat label="Best accuracy"
              value={stats ? `${stats.best_accuracy_pct.toFixed(1)}%` : "—"} />
        <Stat label="Benchmark tasks"   value={stats?.n_task_types ?? "—"} />
        <Stat label="Data source"       value={stats?.data_source ?? "—"} small />
      </div>

    </section>
  );
}

function Stat({ label, value, small }: { label: string; value: string | number; small?: boolean }) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className={`stat-value ${small ? "text-base md:text-lg leading-tight" : ""}`}>
        {value}
      </div>
    </div>
  );
}
