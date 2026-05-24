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

      <LaymanExplanation>
        <strong>What is this?</strong> EPOCH is a test to see if AI models like ChatGPT or Claude actually understand biological aging clocks.
        These clocks predict how fast you're aging and your mortality risk by reading chemical tags on your DNA.
        <br /><br />
        <strong>Why does it matter?</strong> Doctors are starting to use AI to interpret these aging tests. But nobody's checked
        if the AI truly understands what the numbers mean. We created {stats?.n_scenarios ?? "200"} realistic patient scenarios
        where we KNOW the right answer, then tested AI models to see if they get it right. Best score so far: {stats?.best_accuracy_pct.toFixed(1) ?? "77"}%
        — meaning even the smartest AI still makes mistakes 1 in 4 times.
      </LaymanExplanation>
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
