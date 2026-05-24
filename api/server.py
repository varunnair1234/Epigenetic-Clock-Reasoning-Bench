"""FastAPI bridge between the calibrated simulator + eval outputs and the
React/deck.gl frontend.

Run from repo root:
    uvicorn api.server:app --reload --port 8000

Endpoints
---------
GET  /api/health                              liveness check
GET  /api/stats                               summary counters for hero cards
GET  /api/simulate?seed=42&steps=200          full trajectory: snapshots + grids
GET  /api/snapshot?seed=42&step=199           one snapshot (cheap)
GET  /api/leaderboard                         leaderboard.csv as JSON rows
GET  /api/benchmark                           benchmark.json scenarios
GET  /api/error_breakdown                     error_breakdown.csv as JSON rows
GET  /api/calibration                         calibration.json (or partial)
"""

from __future__ import annotations

import csv
import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# Make repo root importable when the server is launched from anywhere.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from simulation.tissue_model import TissueModel  # noqa: E402


app = FastAPI(title="Epigenetic Clock Reasoning Bench API")

# Frontend dev servers (Vite default 5173, plus a couple of common fallbacks).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://localhost:4173",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ---------- File-backed data (lazy reload on every request — files are small) -

EVAL_OUT = _REPO_ROOT / "eval_outputs"
BENCHMARK_JSON = _REPO_ROOT / "benchmark" / "benchmark.json"


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open() as f:
        return list(csv.DictReader(f))


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text())


# ---------- Simulation cache ------------------------------------------------
#
# Keying on (seed, steps) so a given (seed, steps) tuple is computed once and
# subsequent requests for any prefix are O(1) slice. 200 steps × 900 cells ≈
# small enough to keep many cached in memory.

_SIM_CACHE: dict[tuple[int, int], list[dict[str, Any]]] = {}


def _run_simulation(seed: int, steps: int) -> list[dict[str, Any]]:
    """Run a full trajectory and return (steps+1) snapshots, each with `grid`."""
    key = (seed, steps)
    if key in _SIM_CACHE:
        return _SIM_CACHE[key]

    model = TissueModel(seed=seed)
    trajectory: list[dict[str, Any]] = []

    snap = model.snapshot()
    snap["grid"] = model.get_grid_state()
    trajectory.append(snap)

    for _ in range(steps):
        model.step()
        snap = model.snapshot()
        snap["grid"] = model.get_grid_state()
        trajectory.append(snap)

    _SIM_CACHE[key] = trajectory
    return trajectory


# ---------- Endpoints --------------------------------------------------------

@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/stats")
def stats() -> dict:
    """High-level counters for the hero section of the dashboard."""
    leaderboard = _read_csv(EVAL_OUT / "leaderboard.csv")
    benchmark = _read_json(BENCHMARK_JSON) or []
    n_scenarios = len(benchmark) if isinstance(benchmark, list) else 0
    n_models = len({r["model"] for r in leaderboard}) if leaderboard else 0
    best_acc = 0.0
    for r in leaderboard:
        if r.get("task_type") == "ALL":
            try:
                best_acc = max(best_acc, float(r["pct"]))
            except (KeyError, ValueError):
                pass
    return {
        "n_scenarios": n_scenarios,
        "n_models": n_models,
        "best_accuracy_pct": round(best_acc, 1),
        "n_task_types": 4,
        "data_source": "GSE40279 · 656",
    }


@app.get("/api/simulate")
def simulate(
    seed: int = Query(7, ge=0, le=2**31 - 1),
    steps: int = Query(200, ge=1, le=200),
) -> dict:
    """Full trajectory of (steps + 1) snapshots.

    Each snapshot contains the standard summary fields plus `grid`, a
    30×30 array of state codes (0=normal, 1=stressed, 2=senescent, 3=dead).
    """
    traj = _run_simulation(seed, steps)
    return {
        "seed": seed,
        "steps": steps,
        "tissue": "blood",
        "grid_size": len(traj[0]["grid"]) if traj else 0,
        "trajectory": traj[: steps + 1],
    }


@app.get("/api/snapshot")
def snapshot(
    seed: int = Query(7, ge=0, le=2**31 - 1),
    step: int = Query(0, ge=0, le=200),
) -> dict:
    """Single snapshot (cheap; sliced from cached trajectory)."""
    traj = _run_simulation(seed, max(step, 1))
    if step >= len(traj):
        raise HTTPException(status_code=404, detail=f"step {step} out of range")
    return traj[step]


@app.get("/api/leaderboard")
def leaderboard() -> dict:
    rows = _read_csv(EVAL_OUT / "leaderboard.csv")
    # Coerce numeric columns
    for r in rows:
        for k in ("n_scenarios", "earned", "max", "errors", "parse_fails"):
            if k in r:
                try:
                    r[k] = int(r[k])
                except ValueError:
                    pass
        if "pct" in r:
            try:
                r["pct"] = float(r["pct"])
            except ValueError:
                pass
    return {"rows": rows}


@app.get("/api/benchmark")
def benchmark(
    limit: int = Query(50, ge=1, le=500),
    task_type: str | None = Query(None, description="Filter by 'A'/'B'/'C'/'D'."),
    status: str | None = Query(None, description="Filter by overall_status."),
) -> dict:
    """Benchmark scenarios, with optional task_type / status filters."""
    data = _read_json(BENCHMARK_JSON) or []
    if not isinstance(data, list):
        return {"total": 0, "scenarios": []}

    filtered = data
    if task_type:
        t = task_type.strip().upper()[:1]
        filtered = [s for s in filtered if (s.get("task_type") or "").upper().startswith(t)]
    if status:
        filtered = [s for s in filtered if s.get("ground_truth", {}).get("overall_status") == status]

    return {"total": len(filtered), "scenarios": filtered[:limit]}


@app.get("/api/error_breakdown")
def error_breakdown() -> dict:
    rows = _read_csv(EVAL_OUT / "error_breakdown.csv")
    for r in rows:
        for k in ("count",):
            if k in r:
                try:
                    r[k] = int(r[k])
                except ValueError:
                    pass
        if "pct_of_wrong" in r:
            try:
                r["pct_of_wrong"] = float(r["pct_of_wrong"])
            except ValueError:
                pass
    return {"rows": rows}


@app.get("/api/calibration")
def calibration() -> dict:
    data = _read_json(EVAL_OUT / "calibration.json")
    if data is None:
        return {"models": {}, "per_task": {}, "n_bins": 0}
    return data


@app.get("/api/sim_cache_clear")
def clear_cache() -> dict:
    n = len(_SIM_CACHE)
    _SIM_CACHE.clear()
    return {"cleared": n}
