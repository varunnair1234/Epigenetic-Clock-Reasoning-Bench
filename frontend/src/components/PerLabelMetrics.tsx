import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { PerLabelMetric } from "../types";

const MODEL_LABELS: Record<string, string> = {
  claude: "Claude Sonnet 4.6",
  gemini: "Gemini Flash",
  biollm: "BioLLM",
  always_true: "always_true",
  always_false: "always_false",
  majority_class: "majority_class",
};

const LABELS = [
  "accelerated_aging",
  "fast_pacer",
  "high_mortality_risk",
  "clock_discordance",
  "intervention_effective",
];

const BASELINE_NAMES = new Set(["always_true", "always_false", "majority_class"]);

function color(v: number | null, isBaseline: boolean): string {
  if (v == null) return "text-zinc-700";
  const base = isBaseline ? " italic text-zinc-500" : "";
  if (v >= 0.75) return "text-emerald-400" + base;
  if (v >= 0.60) return "text-amber-300" + base;
  if (v >= 0.40) return "text-orange-400" + base;
  return "text-rose-400" + base;
}

export default function PerLabelMetrics() {
  const [rows, setRows] = useState<PerLabelMetric[]>([]);
  useEffect(() => { api.perLabelMetrics().then(d => setRows(d.rows)).catch(() => {}); }, []);

  // Build {model: {label: row}}
  const matrix = useMemo(() => {
    const m: Record<string, Record<string, PerLabelMetric>> = {};
    for (const r of rows) {
      if (!m[r.model]) m[r.model] = {};
      m[r.model][r.label] = r;
    }
    return m;
  }, [rows]);

  // Real models first, then baselines
  const realModels = Object.keys(matrix).filter(m => !BASELINE_NAMES.has(m)).sort();
  const baselines  = Object.keys(matrix).filter(m =>  BASELINE_NAMES.has(m));

  if (rows.length === 0) {
    return (
      <section className="mb-16">
        <div className="section-label mb-1">SECTION 08</div>
        <h2 className="text-3xl font-bold mb-6">Per-label metrics</h2>
        <div className="panel text-zinc-500 text-sm">
          Run <code>python -m eval.metrics</code> after the eval.
        </div>
      </section>
    );
  }

  return (
    <section className="mb-16">
      <div className="section-label mb-1">SECTION 08</div>
      <h2 className="text-3xl font-bold mb-2">Per-label F1 + balanced accuracy</h2>
      <p className="text-zinc-500 text-sm mb-6">
        Balanced accuracy treats both classes equally regardless of imbalance —
        so a model can't game it by always predicting the majority. F1 = harmonic
        mean of precision and recall.
      </p>

      <div className="panel p-0 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-zinc-900/80 text-xs tracking-widest text-zinc-500">
            <tr>
              <th className="px-3 py-2 text-left">MODEL</th>
              <th className="px-3 py-2 text-left">LABEL</th>
              <th className="px-3 py-2 text-right">N</th>
              <th className="px-3 py-2 text-right">ACC</th>
              <th className="px-3 py-2 text-right">BAL ACC</th>
              <th className="px-3 py-2 text-right">F1</th>
              <th className="px-3 py-2 text-right">TP</th>
              <th className="px-3 py-2 text-right">FP</th>
              <th className="px-3 py-2 text-right">TN</th>
              <th className="px-3 py-2 text-right">FN</th>
            </tr>
          </thead>
          <tbody>
            {[...realModels, ...baselines].map(model => {
              const isBaseline = BASELINE_NAMES.has(model);
              return LABELS.map((label, i) => {
                const r = matrix[model]?.[label];
                if (!r) return null;
                return (
                  <tr key={`${model}-${label}`} className={`border-t border-zinc-800 ${isBaseline ? "bg-zinc-900/30" : ""}`}>
                    <td className="px-3 py-2 text-zinc-300">
                      {i === 0 ? (
                        <span className={`font-bold ${isBaseline ? "text-zinc-500" : ""}`}>
                          {MODEL_LABELS[model] ?? model}
                          {isBaseline && <span className="text-zinc-700 ml-1 font-normal">(baseline)</span>}
                        </span>
                      ) : ""}
                    </td>
                    <td className="px-3 py-2 text-zinc-400">{label}</td>
                    <td className="px-3 py-2 text-right text-zinc-500 font-mono">{r.n}</td>
                    <td className={`px-3 py-2 text-right font-mono ${color(r.accuracy, isBaseline)}`}>
                      {r.accuracy !== null ? (r.accuracy * 100).toFixed(1) + "%" : "—"}
                    </td>
                    <td className={`px-3 py-2 text-right font-mono ${color(r.balanced_accuracy, isBaseline)}`}>
                      {r.balanced_accuracy !== null ? (r.balanced_accuracy * 100).toFixed(1) + "%" : "—"}
                    </td>
                    <td className={`px-3 py-2 text-right font-mono ${color(r.f1, isBaseline)}`}>
                      {r.f1 !== null ? r.f1.toFixed(3) : "—"}
                    </td>
                    <td className="px-3 py-2 text-right text-zinc-500 font-mono">{r.tp}</td>
                    <td className="px-3 py-2 text-right text-rose-300/70 font-mono">{r.fp}</td>
                    <td className="px-3 py-2 text-right text-zinc-500 font-mono">{r.tn}</td>
                    <td className="px-3 py-2 text-right text-rose-300/70 font-mono">{r.fn}</td>
                  </tr>
                );
              });
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-4 text-xs text-zinc-500">
        TP/FP/TN/FN counts come from the confusion matrix per (model, label). Baselines
        are scored under the same harness rubric for direct comparison.
      </div>
    </section>
  );
}
