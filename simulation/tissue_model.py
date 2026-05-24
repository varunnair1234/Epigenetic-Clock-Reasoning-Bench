"""Tissue model — the MESA Model that owns the grid and the cell population.

Responsibilities
----------------
* Load real per-CpG drift rates from ``data/GSE40279/drift_rates.csv``.
* Seed initial methylation state from the average of the youngest GSE40279
  samples (real biology, not random).
* Place 900 ``CellAgent``s on a 30×30 Moore grid.
* Each step: (1) advance every agent, (2) propagate SASP from senescent
  cells to neighbors within ``params.SASP_RADIUS``.
* Provide a ``snapshot()`` method that summarizes tissue state and computes
  Horvath / GrimAge / DunedinPACE values at the bulk level.

The model is deterministic given a seed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import mesa

from . import params as P
from .cell_agent import CellAgent
from . import clocks


# Default paths — overridable from the run script for tests / alt datasets.
DEFAULT_DRIFT_RATES = Path("data/GSE40279/drift_rates.csv")
DEFAULT_BETAS = Path("data/GSE40279/horvath_betas.csv")
DEFAULT_METADATA = Path("data/GSE40279/metadata.csv")


class TissueModel(mesa.Model):
    """A 30×30 tissue patch of cells aging over monthly timesteps."""

    def __init__(
        self,
        *,
        drift_rates_path: Path = DEFAULT_DRIFT_RATES,
        betas_path: Path = DEFAULT_BETAS,
        metadata_path: Path = DEFAULT_METADATA,
        chronological_start_age: float | None = None,
        seed: int | None = None,
    ) -> None:
        super().__init__(seed=seed)

        # --- 1. Load drift rates (real OLS slopes from GSE40279) ------------
        drift_df = pd.read_csv(drift_rates_path)
        # Sort by cpg_id so per-cell beta vectors line up with coefficients.
        drift_df = drift_df.sort_values("cpg_id").reset_index(drop=True)
        self.cpg_ids: list[str] = drift_df["cpg_id"].tolist()
        self.drift_per_month: np.ndarray = drift_df["drift_per_month"].to_numpy(
            dtype=np.float32
        )

        # --- 2. Seed initial bulk methylation from young real samples -------
        initial_mean, seed_mean_age = self._compute_young_template(
            betas_path=betas_path,
            metadata_path=metadata_path,
            n_youngest=P.INITIAL_BETA_YOUNG_N,
        )
        self.seed_mean_age: float = seed_mean_age
        # If the caller doesn't supply a chronological age, default to the
        # actual age of the cohort samples we used to seed methylation —
        # otherwise the Horvath readout disagrees with our claimed age.
        self.chronological_start_age: float = (
            chronological_start_age
            if chronological_start_age is not None
            else seed_mean_age
        )

        # --- 3. Build grid and populate it ----------------------------------
        # SingleGrid: one agent per cell, no movement needed.
        self.grid = mesa.space.SingleGrid(P.GRID_SIZE, P.GRID_SIZE, torus=False)

        for x in range(P.GRID_SIZE):
            for y in range(P.GRID_SIZE):
                cell = CellAgent(self, initial_mean, self.drift_per_month)
                self.grid.place_agent(cell, (x, y))

        # --- 4. Mark the initial senescent fraction (young tissue baseline) -
        initial_senescent_count = int(P.N_CELLS * P.INITIAL_SENESCENT_FRACTION)
        for cell in self.random.sample(list(self.agents), initial_senescent_count):
            cell.state = CellAgent.SENESCENT

    # ----------------------------------------------------------------- step
    def step(self) -> None:
        """One simulated month."""
        # 1. Each agent updates its own state (methylation, damage, etc.).
        self.agents.shuffle_do("step")

        # 2. SASP propagation from senescent cells to neighbors.
        self._propagate_sasp()

    # ----------------------------------------------------------- snapshots
    def snapshot(self) -> dict[str, Any]:
        """Summarize current tissue state and compute clock values."""
        # Cells that haven't died contribute to bulk methylation.
        live = [a for a in self.agents if a.state != CellAgent.DEAD]
        n_total = len(list(self.agents))

        states = [a.state for a in self.agents]
        n_senescent = sum(1 for s in states if s == CellAgent.SENESCENT)
        n_stressed = sum(1 for s in states if s == CellAgent.STRESSED)
        n_dead = sum(1 for s in states if s == CellAgent.DEAD)

        if live:
            beta_matrix = np.array([a.betas for a in live], dtype=np.float32)
            bulk_betas = beta_matrix.mean(axis=0)
            mean_damage = float(np.mean([a.damage for a in live]))
            mean_telomere = float(np.mean([a.telomere for a in live]))
        else:
            bulk_betas = np.full(len(self.cpg_ids), 0.5, dtype=np.float32)
            mean_damage = 0.0
            mean_telomere = 0.0

        senescent_fraction = n_senescent / n_total
        # Months elapsed → years for chronological age tracking.
        chrono_age = self.chronological_start_age + (self.steps / 12.0)

        # SASP burden proxy: senescent cells × radius coverage.
        sasp_burden = float(n_senescent) * (2 * P.SASP_RADIUS + 1) ** 2 / n_total

        horvath = float(clocks.horvath_age(bulk_betas, self.cpg_ids))
        grimage = float(
            clocks.grimage_proxy(
                chronological_age=chrono_age,
                senescent_fraction=senescent_fraction,
                mean_sasp_burden=sasp_burden,
            )
        )
        pace = float(
            clocks.dunedinpace_proxy(
                mean_damage=mean_damage,
                senescent_fraction=senescent_fraction,
            )
        )

        return {
            "step": int(self.steps),
            "chronological_age_years": chrono_age,
            "n_total": n_total,
            "n_live": len(live),
            "n_senescent": n_senescent,
            "n_stressed": n_stressed,
            "n_dead": n_dead,
            "senescent_fraction": senescent_fraction,
            "mean_damage": mean_damage,
            "mean_telomere": mean_telomere,
            "sasp_burden": sasp_burden,
            "bulk_methylation_mean": float(np.mean(bulk_betas)),
            "clocks": {
                "horvath": horvath,
                "grimage_proxy": grimage,
                "dunedinpace_proxy": pace,
            },
        }

    # ----------------------------------------------------------------- grid
    _STATE_CODE = {
        CellAgent.NORMAL: 0,
        CellAgent.STRESSED: 1,
        CellAgent.SENESCENT: 2,
        CellAgent.DEAD: 3,
    }

    def get_grid_state(self) -> list[list[int]]:
        """Return a GRID_SIZE × GRID_SIZE matrix of state codes.

        0=normal, 1=stressed, 2=senescent, 3=dead. Empty cells (shouldn't
        happen with SingleGrid + full placement) are emitted as 0.
        """
        n = P.GRID_SIZE
        grid: list[list[int]] = [[0 for _ in range(n)] for _ in range(n)]
        for agent in self.agents:
            x, y = agent.pos
            grid[y][x] = self._STATE_CODE.get(agent.state, 0)
        return grid

    # -------------------------------------------------------------- helpers
    def _propagate_sasp(self) -> None:
        """Senescent cells deliver SASP signal to neighbors in radius."""
        senescent_cells = [
            a for a in self.agents if a.state == CellAgent.SENESCENT
        ]
        for cell in senescent_cells:
            neighbors = self.grid.get_neighbors(
                cell.pos, moore=True, include_center=False, radius=P.SASP_RADIUS
            )
            for neighbor in neighbors:
                if neighbor.state != CellAgent.DEAD:
                    neighbor.sasp_received_this_step += P.SASP_INTENSITY

    def _compute_young_template(
        self,
        *,
        betas_path: Path,
        metadata_path: Path,
        n_youngest: int,
    ) -> tuple[np.ndarray, float]:
        """Mean betas across the ``n_youngest`` samples — used to seed cells.

        Returns the mean beta vector (aligned to ``self.cpg_ids``) and the mean
        chronological age of the samples used, so callers can anchor sim time
        to real biology.
        """
        meta = pd.read_csv(metadata_path)
        meta_avail = meta[meta["sample_id"].notna()].copy()

        beta_df = pd.read_csv(betas_path)
        # Restrict to samples that exist in both files, sort by age, take youngest.
        beta_df = beta_df.merge(
            meta_avail[["sample_id", "age"]], on="sample_id", how="inner"
        )
        youngest = beta_df.nsmallest(n_youngest, "age")
        mean_age = float(youngest["age"].mean())
        # Mean across the chosen samples, restricted to our cpg_ids order.
        means = youngest[self.cpg_ids].mean(axis=0).to_numpy(dtype=np.float32)
        # Defensive clamp in case of any NaNs (shouldn't occur with clean data).
        cleaned = np.nan_to_num(np.clip(means, 0.0, 1.0), nan=0.5)
        return cleaned, mean_age
