import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { BenchmarkScenario } from "../types";

const TASKS  = [null, "A", "B", "C", "D"];
const STATUSES = [null, "at_risk", "accelerated", "normal", "decelerated"];

const TASK_BADGE: Record<string, string> = {
  A: "bg-emerald-900/40 text-emerald-300 border-emerald-700",
  B: "bg-blue-900/40 text-blue-300 border-blue-700",
  C: "bg-purple-900/40 text-purple-300 border-purple-700",
  D: "bg-orange-900/40 text-orange-300 border-orange-700",
};

const STATUS_COLOR: Record<string, string> = {
  at_risk:     "text-orange-300",
  accelerated: "text-rose-400",
  normal:      "text-zinc-400",
  decelerated: "text-blue-300",
};

export default function ScenarioBrowser() {
  const [task, setTask] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [data, setData] = useState<{ total: number; scenarios: BenchmarkScenario[] }>({ total: 0, scenarios: [] });

  useEffect(() => {
    api.benchmark({
      limit: 20,
      ...(task ? { task_type: task } : {}),
      ...(status ? { status: status } : {}),
    }).then(setData).catch(() => setData({ total: 0, scenarios: [] }));
  }, [task, status]);

  return (
    <section className="mb-16">
      <div className="section-label mb-1">SECTION 04</div>
      <h2 className="text-3xl font-bold mb-6">Scenario browser</h2>

      <div className="flex flex-wrap items-center gap-2 mb-4 text-sm">
        <span className="text-zinc-500 mr-2">TASK</span>
        {TASKS.map(t => (
          <button
            key={t ?? "all"}
            onClick={() => setTask(t)}
            className={`btn ${task === t ? "btn-active" : ""}`}
          >
            {t ? `Type ${t}` : "All"}
          </button>
        ))}

        <span className="text-zinc-500 ml-4 mr-2">STATUS</span>
        {STATUSES.map(s => (
          <button
            key={s ?? "all"}
            onClick={() => setStatus(s)}
            className={`btn ${status === s ? "btn-active" : ""}`}
          >
            {s ? s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, " ") : "All"}
          </button>
        ))}

        <span className="ml-auto text-zinc-500">
          Showing {data.scenarios.length} of {data.total}
        </span>
      </div>

      <div className="flex flex-col gap-3">
        {data.scenarios.map(s => <ScenarioCard key={s.scenario_id} scenario={s} />)}
        {data.scenarios.length === 0 && (
          <div className="panel text-zinc-500 text-sm">No scenarios match this filter.</div>
        )}
      </div>
    </section>
  );
}

function ScenarioCard({ scenario }: { scenario: BenchmarkScenario }) {
  const cv = scenario.clock_values;
  const t = (scenario.task_type || "A").charAt(0).toUpperCase();
  const status = scenario.ground_truth?.overall_status;
  return (
    <div className="panel">
      <div className="flex items-center gap-3 mb-2">
        <span className={`px-2 py-0.5 rounded text-xs font-bold border ${TASK_BADGE[t] ?? ""}`}>
          TYPE {t}
        </span>
        {status && (
          <span className={`text-xs font-bold uppercase ${STATUS_COLOR[status] ?? "text-zinc-400"}`}>
            {status.replace(/_/g, " ")}
          </span>
        )}
        <span className="ml-auto text-zinc-500 text-xs">#{scenario.scenario_id}</span>
      </div>

      <div className="mb-3">
        <span className="font-bold text-zinc-100">Age {scenario.patient_age}</span>
        <span className="text-zinc-400 text-sm"> — {scenario.patient_context}</span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm mb-3">
        {(["horvath", "grimage", "dunedin_pace"] as const).map(k =>
          cv[k] !== undefined ? (
            <MetricBox key={k}
              label={k.toUpperCase().replace("_", "")}
              sublabel={k === "dunedin_pace" ? "Above Average Pace" : (k === "horvath" ? "Biological Age" : "Mortality Risk Age")}
              value={k === "dunedin_pace" ? cv[k].toFixed(3) : `${cv[k].toFixed(1)} yrs`}
              color={k === "horvath" ? "text-emerald-300" : k === "grimage" ? "text-orange-300" : "text-amber-300"}
            />
          ) : null
        )}
        {cv["senescent_fraction_pct"] !== undefined && (
          <MetricBox label="SENESCENT" sublabel="Senescent Fraction"
            value={`${cv["senescent_fraction_pct"].toFixed(1)}%`}
            color="text-pink-400"
          />
        )}
      </div>

      <div className="flex flex-wrap gap-1.5">
        {scenario.ground_truth?.fast_pacer && <Tag color="text-orange-300 border-orange-700">Fast Pacer</Tag>}
        {scenario.ground_truth?.high_mortality_risk && <Tag color="text-rose-300 border-rose-700">High Mortality Risk</Tag>}
        {scenario.ground_truth?.clock_discordance && <Tag color="text-purple-300 border-purple-700">Clock Discordance</Tag>}
        {scenario.ground_truth?.accelerated_aging && <Tag color="text-amber-300 border-amber-600">Accelerated Aging</Tag>}
        {scenario.ground_truth?.intervention_effective === true && <Tag color="text-emerald-300 border-emerald-700">Intervention Effective</Tag>}
      </div>
    </div>
  );
}

function MetricBox({ label, sublabel, value, color }: { label: string; sublabel: string; value: string; color: string }) {
  return (
    <div className="border border-zinc-800 rounded-md px-3 py-2">
      <div className="flex justify-between items-baseline">
        <span className="text-zinc-500 text-xs tracking-wider">{label}</span>
        <span className={`text-sm font-mono ${color}`}>{value}</span>
      </div>
      <div className="text-zinc-600 text-xs mt-0.5">{sublabel}</div>
    </div>
  );
}

function Tag({ children, color }: { children: React.ReactNode; color: string }) {
  return <span className={`px-2 py-0.5 rounded-full text-xs border ${color}`}>{children}</span>;
}
