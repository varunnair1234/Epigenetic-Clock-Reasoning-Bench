"""Individual cell agent.

Each agent represents a single cell in a tissue patch and tracks:

* Methylation state at the canonical Horvath 353 CpGs
* Telomere length (normalized)
* DNA damage counter
* Senescence state machine: ``normal → stressed → senescent → dead``
* SASP signal received from senescent neighbors during the current step

SASP *emission* is handled by the tissue model after all cells have stepped,
so neighbor lookups happen in a single pass.
"""

from __future__ import annotations

import numpy as np
import mesa

from . import params as P


class CellAgent(mesa.Agent):
    """A single cell."""

    # Lifecycle states
    NORMAL = "normal"
    STRESSED = "stressed"
    SENESCENT = "senescent"
    DEAD = "dead"

    def __init__(
        self,
        model: mesa.Model,
        initial_betas: np.ndarray,
        drift_per_month: np.ndarray,
    ) -> None:
        super().__init__(model)
        # Per-cell methylation state at the Horvath 353 CpGs.
        self.betas: np.ndarray = initial_betas.astype(np.float32, copy=True)
        # Deterministic drift rates (shared across cells; pre-loaded by model).
        self._drift = drift_per_month.astype(np.float32, copy=False)

        rng = self.model.random
        self.telomere: float = max(
            0.0, rng.gauss(P.INITIAL_TELOMERE, P.INITIAL_TELOMERE_STD)
        )
        self.damage: float = rng.uniform(0.0, P.INITIAL_DAMAGE_MAX)
        self.state: str = self.NORMAL
        self.sasp_received_this_step: float = 0.0

    # ------------------------------------------------------------------ step
    def step(self) -> None:
        if self.state == self.DEAD:
            return

        self._drift_methylation()
        self._accumulate_damage()
        self._maybe_divide()
        self._update_senescence_state()

    # ----------------------------------------------------------- substeps
    def _drift_methylation(self) -> None:
        """Apply deterministic drift + Gaussian noise to each CpG."""
        rng = np.random.default_rng(self.model.random.randint(0, 2**32 - 1))
        noise = rng.normal(0.0, P.DRIFT_NOISE_STD, size=self.betas.shape).astype(
            np.float32
        )
        self.betas += self._drift + noise
        # Clamp into valid beta range [0, 1].
        np.clip(self.betas, 0.0, 1.0, out=self.betas)

    def _accumulate_damage(self) -> None:
        """Net damage change = ROS + SASP-amplification − DNA repair."""
        rng = self.model.random
        ros = rng.gauss(P.ROS_DAMAGE_PER_TIMESTEP_MEAN, P.ROS_DAMAGE_PER_TIMESTEP_STD)
        ros = max(0.0, ros)
        amplification = self.sasp_received_this_step * P.SASP_DAMAGE_AMPLIFIER
        # Repair: full rate for normal/stressed cells; senescent cells repair
        # less efficiently (well-documented hallmark of senescence).
        repair = (
            P.DAMAGE_REPAIR_PER_TIMESTEP * 0.5
            if self.state == self.SENESCENT
            else P.DAMAGE_REPAIR_PER_TIMESTEP
        )
        net = ros + amplification - repair
        self.damage = max(0.0, min(1.0, self.damage + net))
        self.sasp_received_this_step = 0.0

    def _maybe_divide(self) -> None:
        """Homeostatic turnover; only normal cells divide. Shortens telomere."""
        if self.state != self.NORMAL:
            return
        if self.model.random.random() < P.DIVISION_PROBABILITY:
            self.telomere = max(0.0, self.telomere - P.TELOMERE_SHORTENING_PER_DIVISION)

    def _update_senescence_state(self) -> None:
        # Senescent cells are apoptosis-resistant and persist through the
        # 16-year window; we don't model immune clearance here.
        if self.state == self.SENESCENT:
            return
        # Death from damage runaway only applies to non-senescent cells.
        if self.damage > P.DEATH_DAMAGE_THRESHOLD:
            self.state = self.DEAD
            return
        # Senescence: triggered either by telomere crisis or by damage.
        if (
            self.telomere < P.TELOMERE_CRISIS_THRESHOLD
            or self.damage > P.SENESCENCE_DAMAGE_THRESHOLD
        ):
            self.state = self.SENESCENT
            return
        # Stressed: damage above the lower threshold but not yet senescent.
        if self.damage > P.STRESS_DAMAGE_THRESHOLD:
            self.state = self.STRESSED
            return
        # Otherwise: hold current state (don't spontaneously de-stress).
