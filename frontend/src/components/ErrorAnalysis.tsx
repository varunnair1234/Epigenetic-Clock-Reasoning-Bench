import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { ErrorBreakdownRow } from "../types";

const CATEGORY_INFO: Record<string, { label: string; color: string; desc: string }> = {
  clock_confusion:           { label: "Clock Confusion",      color: "text-blue-300",
    desc: "Model conflated which clock indicates what — got accelerated_aging wrong but fast_pacer right (or vice versa)." },
  direction_over:            { label: "Direction Error (over)", color: "text-orange-300",
    desc: "Predicted accelerated when ground truth says normal/decelerated." },
  direction_under:           { label: "Direction Error (under)", color: "text-orange-300",
    desc: "Predicted normal/decelerated when ground truth says accelerated." },
  missed_discordance:        { label: "Missed Discordance",   color: "text-purple-300",
    desc: "Ground truth flagged clock discordance but the model missed it." },
  hallucinated_discordance:  { label: "Hallucinated Discordance", color: "text-purple-300",
    desc: "Model claimed clocks disagreed when they actually agreed." },
  confounder_blind:          { label: "Confounder Blind",     color: "text-rose-300",
    desc: "Failed on a Type D scenario — treated technical artifact as true biological signal." },
  hallucinated_intervention: { label: "Hallucinated Intervention", color: "text-amber-300",
    desc: "Claimed intervention worked when ground truth says it didn't." },
  missed_intervention:       { label: "Missed Intervention",  color: "text-amber-300",
    desc: "Said intervention didn't work when it actually did." },
  error_or_parse_fail:       { label: "Parse / API Failure",  color: "text-rose-400",
    desc: "Model response was malformed or the API call errored." },
  other:                     { label: "Other",                color: "text-zinc-400",
    desc: "Wrong answers that don't match the above patterns." },
};

const MODEL_LABELS: Record<string, string> = {
  claude: "Claude Sonnet 4.6",
  gemini: "Gemini Flash",
  biollm: "BioLLM (Longevity-Tuned)",
};

export default function ErrorAnalysis() {
  const [rows, setRows] = useState<ErrorBreakdownRow[]>([]);
  useEffect(() => { api.errorBreakdown().then(d => setRows(d.rows)).catch(() => {}); }, []);

  // Group rows by model
  const byModel = useMemo(() => {
    const out: Record<string, ErrorBreakdownRow[]> = {};
    for (const r of rows) {
      if (!out[r.model]) out[r.model] = [];
      out[r.model].push(r);
    }
    return out;
  }, [rows]);

  const models = Object.keys(byModel).sort();

  // Insight: highest parse-fail model
  const parseFailModel = models
    .map(m => ({ m, n: byModel[m].find(r => r.category === "error_or_parse_fail")?.count ?? 0 }))
    .sort((a, b) => b.n - a.n)[0];

  return (
    <section className="mb-16">
      <div className="section-label mb-1">SECTION 06</div>
      <h2 className="text-3xl font-bold mb-2">Error Analysis</h2>
      <p className="text-zinc-500 text-sm mb-6">
        Model failure patterns across {rows.length} categorized responses
      </p>

      {models.length === 0 && (
        <div className="panel text-zinc-500 text-sm">
          No error breakdown yet. Run <code>python -m eval.error_analysis</code> after an eval.
        </div>
      )}

      <div className={`grid gap-4 ${models.length === 1 ? "" : models.length === 2 ? "md:grid-cols-2" : "md:grid-cols-3"}`}>
        {models.map(m => {
          const cats = byModel[m];
          const parseFails = cats.find(r => r.category === "error_or_parse_fail")?.count ?? 0;
          return (
            <div key={m}>
              <div className="flex items-center justify-between mb-3">
                <div className="font-bold">{MODEL_LABELS[m] ?? m}</div>
                <div className="text-xs text-zinc-500">
                  Parse fails: <span className={parseFails > 0 ? "text-rose-400 font-bold" : "text-emerald-400 font-bold"}>{parseFails}</span>
                </div>
              </div>
              <div className="flex flex-col gap-2">
                {Object.keys(CATEGORY_INFO).map(catKey => {
                  const info = CATEGORY_INFO[catKey];
                  const cnt = cats.find(c => c.category === catKey)?.count ?? 0;
                  return (
                    <div key={catKey} className="panel py-3">
                      <div className="flex items-center justify-between">
                        <div className={`font-bold text-sm ${info.color}`}>{info.label}</div>
                        <div className={`font-bold text-lg ${cnt > 0 ? info.color : "text-zinc-700"}`}>{cnt}</div>
                      </div>
                      <div className="text-zinc-500 text-xs mt-1 leading-snug">{info.desc}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      {parseFailModel && parseFailModel.n > 0 && (
        <div className="mt-5 panel border-l-4 border-amber-500 text-sm">
          <span className="text-amber-300">Insight:</span> Parse failures (
          {models.map(m => `${MODEL_LABELS[m] ?? m}: ${byModel[m].find(r => r.category === "error_or_parse_fail")?.count ?? 0}`).join(", ")}
          ) indicate {MODEL_LABELS[parseFailModel.m] ?? parseFailModel.m} occasionally produces malformed JSON responses,
          reducing its effective accuracy beyond raw scoring.
        </div>
      )}
    </section>
  );
}
