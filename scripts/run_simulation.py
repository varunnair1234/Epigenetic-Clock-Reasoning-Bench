"""Run the tissue simulation and emit per-step snapshots as JSON.

Usage
-----
    python scripts/run_simulation.py \
        --steps 200 \
        --start-age 25 \
        --seed 42 \
        --out runs/run_seed42.json

Outputs a JSON file containing one snapshot per step:

    {
        "config": {...},
        "snapshots": [
            {"step": 0, "chronological_age_years": 25.0, ...},
            {"step": 1, ...},
            ...
        ]
    }

This is the Stage-1 deliverable: the simulation runs end-to-end and produces
real clock values from real-cohort-seeded methylation drift.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as ``python scripts/run_simulation.py`` from the repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from simulation.tissue_model import TissueModel  # noqa: E402
from simulation import params as P  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run the tissue aging simulation.")
    p.add_argument(
        "--steps",
        type=int,
        default=P.N_STEPS,
        help="Number of monthly steps to simulate (default: %(default)s).",
    )
    p.add_argument(
        "--start-age",
        type=float,
        default=None,
        help=(
            "Chronological age (years) at step 0. If omitted, the model uses "
            "the mean age of the youngest seed samples (real biology anchor)."
        ),
    )
    p.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: %(default)s).",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=Path("runs/latest.json"),
        help="Output JSON path (default: %(default)s).",
    )
    p.add_argument(
        "--snapshot-every",
        type=int,
        default=1,
        help="Emit a snapshot every N steps (default: every step).",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    print(
        f"Building TissueModel: {P.GRID_SIZE}×{P.GRID_SIZE} grid "
        f"({P.N_CELLS} cells), seed={args.seed}"
    )
    model = TissueModel(
        chronological_start_age=args.start_age,
        seed=args.seed,
    )
    print(
        f"  seed_mean_age={model.seed_mean_age:.1f}y  "
        f"start_age={model.chronological_start_age:.1f}y"
    )

    snapshots: list[dict] = []
    # Step 0: pre-step snapshot.
    snapshots.append(model.snapshot())

    for step_i in range(1, args.steps + 1):
        model.step()
        if step_i % args.snapshot_every == 0 or step_i == args.steps:
            snap = model.snapshot()
            snapshots.append(snap)
            if step_i % max(1, args.steps // 10) == 0:
                print(
                    f"  step {step_i:4d}/{args.steps}  "
                    f"sen_frac={snap['senescent_fraction']:.3f}  "
                    f"horvath={snap['clocks']['horvath']:.1f}  "
                    f"pace={snap['clocks']['dunedinpace_proxy']:.2f}"
                )

    output = {
        "config": {
            "steps": args.steps,
            "start_age": args.start_age,
            "seed": args.seed,
            "grid_size": P.GRID_SIZE,
            "n_cells": P.N_CELLS,
            "n_cpgs_tracked": len(model.cpg_ids),
        },
        "snapshots": snapshots,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2))
    print(f"\nWrote {len(snapshots)} snapshots → {args.out}")


if __name__ == "__main__":
    main()
