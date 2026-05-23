"""Epigenetic clock implementations.

* Horvath 2013 — implemented exactly from the published coefficients
  (vendored as ``horvath_coefficients.csv``) and anti-transform.
* GrimAge & DunedinPACE — v1 proxy formulas per the project spec. These map
  tissue-level state (senescent fraction, mean damage, SASP burden) to clock
  values via linear approximations. Real GrimAge needs ~1030 CpGs and plasma
  protein proxies; real DunedinPACE needs 173 specific CpGs. Both are stretch
  goals; see TODOs below.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import params as P

# ---------------------------------------------------------------------------
# Horvath coefficients (load once on import)
# ---------------------------------------------------------------------------

_HORVATH_PATH = Path(__file__).parent / "horvath_coefficients.csv"
_HORVATH_COEFS: dict[str, float] = {}


def _load_horvath_coefficients() -> dict[str, float]:
    df = pd.read_csv(_HORVATH_PATH)
    return dict(zip(df["CpGmarker"], df["CoefficientTraining"], strict=True))


_HORVATH_COEFS = _load_horvath_coefficients()
HORVATH_CPG_IDS: list[str] = list(_HORVATH_COEFS.keys())


def horvath_age(bulk_betas: np.ndarray, cpg_ids: list[str]) -> float:
    """Predict Horvath biological age from a bulk-tissue methylation vector.

    Parameters
    ----------
    bulk_betas
        1-D array of beta values aligned with ``cpg_ids``.
    cpg_ids
        CpG IDs corresponding to the columns of ``bulk_betas``.

    Returns
    -------
    Predicted age in years.
    """
    if len(bulk_betas) != len(cpg_ids):
        raise ValueError(
            f"length mismatch: bulk_betas={len(bulk_betas)} vs cpg_ids={len(cpg_ids)}"
        )

    score = P.HORVATH_INTERCEPT
    for cpg, beta in zip(cpg_ids, bulk_betas, strict=True):
        coef = _HORVATH_COEFS.get(cpg)
        if coef is not None:
            score += beta * coef
    return _anti_trafo(score, adult_age=P.HORVATH_ADULT_AGE)


def _anti_trafo(x: float, adult_age: int = 20) -> float:
    """Inverse of the Horvath training transform (Horvath 2013, Supplement)."""
    if x < 0:
        return (1 + adult_age) * np.exp(x) - 1
    return (1 + adult_age) * x + adult_age


# ---------------------------------------------------------------------------
# GrimAge proxy (v1)  -- per project spec
# ---------------------------------------------------------------------------

def grimage_proxy(
    chronological_age: float,
    senescent_fraction: float,
    mean_sasp_burden: float,
) -> float:
    """Approximate GrimAge from tissue state.

    Per the project spec: ``senescent cell fraction + total SASP → GrimAge``.
    Calibrated so that a tissue at 12% senescent + moderate SASP gives ~+5y
    acceleration vs chronological age.

    TODO(stretch): replace with the real GrimAge model (needs ~1030 CpGs +
    plasma protein proxies; requires expanded CellAgent methylation state).
    """
    acceleration = (senescent_fraction - 0.05) * 60.0 + mean_sasp_burden * 0.4
    return chronological_age + acceleration


# ---------------------------------------------------------------------------
# DunedinPACE proxy (v1)  -- per project spec
# ---------------------------------------------------------------------------

def dunedinpace_proxy(mean_damage: float, senescent_fraction: float) -> float:
    """Approximate DunedinPACE (pace-of-aging) from tissue state.

    Per the project spec: ``mean DNA damage + senescent fraction → PACE``.
    Belsky 2022 reports PACE mean = 1.0, σ ≈ 0.1. We anchor "average" pace at
    a young-tissue baseline (low damage, low senescence) and scale linearly.

    TODO(stretch): replace with the real DunedinPACE model (173-CpG ridge
    regression with published weights).
    """
    return 1.0 + (mean_damage - 0.15) * 2.0 + (senescent_fraction - 0.05) * 2.0
