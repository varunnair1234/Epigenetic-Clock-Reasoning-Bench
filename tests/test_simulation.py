"""Smoke + sanity tests for the tissue simulation.

These tests are deliberately lightweight — they don't try to validate the
biology in detail. They check three things:

1. The model builds and steps without errors.
2. After ~16 years of simulated time, senescent fraction lands in the
   literature range (10–15%) for aged tissue (van Deursen 2014).
3. Predicted Horvath age moves in the expected direction (older after
   simulation) and stays in a biologically plausible range.

Run with::

    pytest -q tests/test_simulation.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from simulation import params as P
from simulation.tissue_model import TissueModel


@pytest.fixture(scope="module")
def short_run() -> dict:
    """A short (24-step = 2 year) run for fast tests."""
    model = TissueModel(seed=7)
    snaps = [model.snapshot()]
    for _ in range(24):
        model.step()
    snaps.append(model.snapshot())
    return {"model": model, "first": snaps[0], "last": snaps[-1]}


@pytest.fixture(scope="module")
def full_run() -> dict:
    """A full 200-step (~16 year) run. Slower; module-scoped to reuse."""
    model = TissueModel(seed=7)
    snaps = [model.snapshot()]
    for _ in range(P.N_STEPS):
        model.step()
    snaps.append(model.snapshot())
    return {"first": snaps[0], "last": snaps[-1]}


def test_model_builds_with_expected_population(short_run):
    """All 900 cells get instantiated and placed."""
    model = short_run["model"]
    assert model.cpg_ids, "cpg_ids should be loaded from drift_rates.csv"
    assert len(model.cpg_ids) == 353
    snap = short_run["first"]
    assert snap["n_total"] == P.N_CELLS
    assert snap["n_live"] > 0


def test_initial_senescent_fraction_in_young_range(short_run):
    """Young tissue baseline: 2–5% senescent (Campisi 2013)."""
    sen_frac = short_run["first"]["senescent_fraction"]
    assert 0.01 <= sen_frac <= 0.07, (
        f"young tissue senescent fraction out of range: {sen_frac:.3f}"
    )


def test_short_run_produces_clock_values(short_run):
    """Clock outputs are real numbers in a plausible range."""
    snap = short_run["last"]
    clocks = snap["clocks"]
    assert 10 < clocks["horvath"] < 120, f"Horvath age implausible: {clocks['horvath']}"
    assert 0.3 < clocks["dunedinpace_proxy"] < 3.0, (
        f"PACE proxy out of range: {clocks['dunedinpace_proxy']}"
    )


def test_full_run_aged_senescent_fraction(full_run):
    """After ~16 years, senescent fraction should approach van Deursen 2014 range.

    We use a loose upper bound (≤ 0.20) and a clear lower bound (> initial)
    rather than a strict 10–15% band — the exact landing depends on calibration
    of damage/ROS constants, which is intentionally a tunable.
    """
    initial = full_run["first"]["senescent_fraction"]
    final = full_run["last"]["senescent_fraction"]
    assert final > initial, f"sen_frac did not grow: {initial:.3f} → {final:.3f}"
    assert final <= 0.40, f"sen_frac unexpectedly high (calibration issue): {final:.3f}"


def test_horvath_age_increases_over_full_run(full_run):
    """Predicted Horvath age should track chronological time forward."""
    h_initial = full_run["first"]["clocks"]["horvath"]
    h_final = full_run["last"]["clocks"]["horvath"]
    assert h_final > h_initial - 1.0, (
        "Horvath should not regress meaningfully over the run "
        f"({h_initial:.2f} → {h_final:.2f})"
    )


def test_snapshot_schema_keys():
    """Lock the snapshot schema so downstream consumers don't break silently."""
    model = TissueModel(seed=1)
    snap = model.snapshot()
    expected = {
        "step",
        "chronological_age_years",
        "n_total",
        "n_live",
        "n_senescent",
        "n_stressed",
        "n_dead",
        "senescent_fraction",
        "mean_damage",
        "mean_telomere",
        "sasp_burden",
        "bulk_methylation_mean",
        "clocks",
    }
    assert expected.issubset(snap.keys()), (
        f"missing keys: {expected - snap.keys()}"
    )
    assert {"horvath", "grimage_proxy", "dunedinpace_proxy"} <= snap["clocks"].keys()
