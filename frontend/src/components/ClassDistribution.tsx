import { useEffect, useState } from "react";
import { api } from "../api";
import type { ClassDistribution as Dist } from "../types";

export default function ClassDistribution() {
  const [dist, setDist] = useState<Dist | null>(null);
  useEffect(() => { api.classDistribution().then(setDist).catch(() => {}); }, []);
  if (!dist) return null;

  const labels = Object.keys(dist);
  return (
    <section className="mb-16">
      <div className="section-label mb-1">SECTION 07</div>
      <h2 className="text-3xl font-bold mb-2">Class distribution</h2>
      <p className="text-zinc-500 text-sm mb-6">
        Ground-truth True / False rates per label — surfaces imbalance honestly so the
        leaderboard numbers can be interpreted against the naive baselines below.
      </p>

      <div className="panel">
        <div className="flex flex-col gap-3">
          {labels.map(label => {
            const d = dist[label];
            const total = d.true + d.false;
            const pctTrue = d.pct_true ?? 0;
            const severe = d.pct_true !== null && (d.pct_true < 15 || d.pct_true > 85);
            return (
              <div key={label}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium">
                    {label}
                    {severe && <span className="ml-2 text-amber-400 text-xs">⚠ severe imbalance</span>}
                  </span>
                  <span className="text-xs text-zinc-500 font-mono">
                    True {d.true} · False {d.false}{d.null > 0 ? ` · null ${d.null}` : ""}
                  </span>
                </div>
                <div className="flex h-6 rounded overflow-hidden bg-zinc-900 border border-zinc-800">
                  {total > 0 && (
                    <>
                      <div className="bg-emerald-500/70 flex items-center justify-center text-xs"
                           style={{ width: `${(d.true / total) * 100}%` }}>
                        {pctTrue >= 12 && <span className="text-emerald-950 font-bold">True {pctTrue.toFixed(0)}%</span>}
                      </div>
                      <div className="bg-zinc-700 flex items-center justify-center text-xs"
                           style={{ width: `${(d.false / total) * 100}%` }}>
                        {(100 - pctTrue) >= 12 && <span className="text-zinc-300 font-bold">False {(100 - pctTrue).toFixed(0)}%</span>}
                      </div>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <div className="mt-5 text-xs text-zinc-500 italic border-t border-zinc-800 pt-4">
          <span className="text-amber-300">Why this matters:</span> a "majority-class baseline" that
          always predicts the more common value would still score in the 60s on raw accuracy
          for an imbalanced benchmark. We report it (next section) so the headline numbers are
          interpretable against trivial pattern-matching.
        </div>
      </div>
    </section>
  );
}
