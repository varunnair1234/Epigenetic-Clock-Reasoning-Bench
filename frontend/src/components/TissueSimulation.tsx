import { useEffect, useMemo, useRef, useState } from "react";
import DeckGL from "@deck.gl/react";
import { OrthographicView } from "@deck.gl/core";
import { PolygonLayer } from "@deck.gl/layers";
import { api } from "../api";
import type { SimulateResponse, Snapshot } from "../types";

// Colors keyed to state codes: 0=normal, 1=stressed, 2=senescent, 3=dead.
const STATE_COLOR: [number, number, number][] = [
  [16, 185, 129],   // normal — emerald
  [251, 191, 36],   // stressed — amber
  [249, 115, 22],   // senescent — orange
  [127, 29, 29],    // dead — dark red
];

const STATE_LEGEND: { code: number; label: string; hex: string }[] = [
  { code: 0, label: "normal",    hex: "#10b981" },
  { code: 1, label: "stressed",  hex: "#fbbf24" },
  { code: 2, label: "senescent", hex: "#f97316" },
  { code: 3, label: "dead",      hex: "#7f1d1d" },
];

const CELL_SIZE = 18;  // px per cell in OrthographicView

interface GridCell {
  polygon: number[][];
  state: number;
}

function snapshotToCells(snap: Snapshot): GridCell[] {
  const cells: GridCell[] = [];
  for (let y = 0; y < snap.grid.length; y++) {
    const row = snap.grid[y];
    for (let x = 0; x < row.length; x++) {
      const px = x * CELL_SIZE;
      const py = y * CELL_SIZE;
      // Small inset so cells appear as distinct squares
      const inset = 1.5;
      cells.push({
        state: row[x],
        polygon: [
          [px + inset, py + inset],
          [px + CELL_SIZE - inset, py + inset],
          [px + CELL_SIZE - inset, py + CELL_SIZE - inset],
          [px + inset, py + CELL_SIZE - inset],
        ],
      });
    }
  }
  return cells;
}

export default function TissueSimulation() {
  const [data, setData] = useState<SimulateResponse | null>(null);
  const [step, setStep] = useState(0);
  const [seed, setSeed] = useState(7);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<1 | 2 | 5>(2);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const playRef = useRef<number | null>(null);

  // Fetch trajectory whenever seed changes.
  useEffect(() => {
    setLoading(true); setErr(null); setData(null); setStep(0);
    api.simulate(seed, 200)
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setErr(String(e)); setLoading(false); });
  }, [seed]);

  // Playback loop.
  useEffect(() => {
    if (!playing || !data) return;
    const interval = Math.max(20, 200 / speed);  // ms per step
    playRef.current = window.setInterval(() => {
      setStep(s => {
        if (s >= data.trajectory.length - 1) {
          setPlaying(false);
          return s;
        }
        return s + 1;
      });
    }, interval);
    return () => {
      if (playRef.current != null) window.clearInterval(playRef.current);
    };
  }, [playing, data, speed]);

  const snap = data?.trajectory[step];
  const cells = useMemo(() => (snap ? snapshotToCells(snap) : []), [snap]);

  const gridPx = (snap?.grid.length ?? 30) * CELL_SIZE;
  const layers = useMemo(
    () => [
      new PolygonLayer({
        id: "cells",
        data: cells,
        getPolygon: (d: GridCell) => d.polygon,
        getFillColor: (d: GridCell) => STATE_COLOR[d.state] ?? [50, 50, 50],
        stroked: false,
        filled: true,
        pickable: false,
      }),
    ],
    [cells]
  );

  return (
    <section className="mb-16">
      <div className="section-label mb-1">SECTION 02</div>
      <h2 className="text-3xl font-bold mb-6">Tissue simulation</h2>

      <div className="grid lg:grid-cols-[2fr,1fr] gap-6">
        {/* === Grid view === */}
        <div className="panel relative aspect-square min-h-[450px]">
          <div className="absolute top-3 left-3 z-10 stat-label">
            MONTH {step} / {(data?.trajectory.length ?? 1) - 1}
          </div>

          {loading && (
            <div className="absolute inset-0 flex items-center justify-center text-zinc-500">
              running 200 simulated months…
            </div>
          )}
          {err && (
            <div className="absolute inset-0 flex items-center justify-center text-rose-400 text-sm p-6 text-center">
              {err}<br />Is the API running? <code>uvicorn api.server:app --port 8000</code>
            </div>
          )}

          {snap && (
            <DeckGL
              views={new OrthographicView({ id: "ortho", flipY: true })}
              initialViewState={{
                target: [gridPx / 2, gridPx / 2, 0],
                zoom: Math.log2(450 / gridPx),
              }}
              controller={false}
              layers={layers}
              style={{
                position: "absolute",
                top: 0, left: 0, width: "100%", height: "100%",
                background: "transparent",
              }}
            />
          )}

          {/* Legend */}
          <div className="absolute bottom-3 left-3 flex gap-4 text-xs z-10">
            {STATE_LEGEND.map(s => (
              <span key={s.code} className="flex items-center gap-1.5 text-zinc-400">
                <span
                  className="inline-block w-2.5 h-2.5 rounded-full"
                  style={{ background: s.hex }}
                />
                {s.label}
              </span>
            ))}
          </div>
        </div>

        {/* === Side panel: clocks + controls === */}
        <div className="flex flex-col gap-4">
          <div className="panel">
            <div className="stat-label mb-3">EPIGENETIC CLOCKS</div>
            <ClockRow label="Horvath Age"
                      value={snap ? `${snap.clocks.horvath.toFixed(1)} yr` : "—"}
                      color="text-emerald-400" />
            <ClockRow label="GrimAge"
                      value={snap ? `${snap.clocks.grimage_proxy.toFixed(1)} yr` : "—"}
                      color="text-orange-400" />
            <ClockRow label="DunedinPACE"
                      value={snap ? snap.clocks.dunedinpace_proxy.toFixed(3) : "—"}
                      color="text-amber-300" />
            <ClockRow label="Senescent %"
                      value={snap ? `${(snap.senescent_fraction * 100).toFixed(1)}%` : "—"}
                      color="text-pink-400" />
          </div>

          <div className="panel">
            <div className="flex gap-2 mb-4">
              <button
                onClick={() => setPlaying(p => !p)}
                className="btn btn-primary flex-1"
                disabled={!data}
              >
                {playing ? "Pause" : "Play"}
              </button>
              <button
                onClick={() => { setStep(0); setPlaying(false); }}
                className="btn"
                disabled={!data}
              >
                Reset
              </button>
            </div>

            <div className="text-xs text-zinc-400 mb-1">Speed: {speed}×</div>
            <div className="flex gap-2 mb-4">
              {[1, 2, 5].map(s => (
                <button
                  key={s}
                  onClick={() => setSpeed(s as 1 | 2 | 5)}
                  className={`btn flex-1 ${speed === s ? "btn-active" : ""}`}
                >
                  {s}×
                </button>
              ))}
            </div>

            <div className="text-xs text-zinc-400 mb-1">Patient</div>
            <div className="flex gap-2 mb-4">
              {[
                { seed: 7, label: "A" },
                { seed: 13, label: "B" },
                { seed: 42, label: "C" },
                { seed: 99, label: "D" }
              ].map(p => (
                <button
                  key={p.seed}
                  onClick={() => setSeed(p.seed)}
                  className={`btn flex-1 ${seed === p.seed ? "btn-active" : ""}`}
                >
                  {p.label}
                </button>
              ))}
            </div>

            <input
              type="range"
              min={0}
              max={(data?.trajectory.length ?? 1) - 1}
              value={step}
              onChange={e => setStep(parseInt(e.target.value))}
              className="w-full"
              disabled={!data}
            />
          </div>
        </div>
      </div>
    </section>
  );
}

function ClockRow({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="flex justify-between items-center py-1.5 text-sm">
      <span className="text-zinc-400">{label}</span>
      <span className={`font-bold ${color}`}>{value}</span>
    </div>
  );
}
