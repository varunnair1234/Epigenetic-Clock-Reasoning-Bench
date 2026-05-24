"""Ground-truth label derivation from simulation snapshots.

Snapshot key reference (from tissue_model.TissueModel.snapshot()):
    sim_output["senescent_fraction"]          float
    sim_output["clocks"]["horvath"]           float  — Horvath biological age (years)
    sim_output["clocks"]["grimage_proxy"]     float  — GrimAge proxy (years)
    sim_output["clocks"]["dunedinpace_proxy"] float  — DunedinPACE proxy
"""

from __future__ import annotations

_EXPECTED_TOP_KEYS = [
    "step", "chronological_age_years", "n_total", "n_live",
    "n_senescent", "n_stressed", "n_dead", "senescent_fraction",
    "mean_damage", "mean_telomere", "sasp_burden", "bulk_methylation_mean", "clocks",
]
_EXPECTED_CLOCK_KEYS = ["horvath", "grimage_proxy", "dunedinpace_proxy"]


def derive_ground_truth(
    sim_output: dict,
    patient_age: int,
    scenario: dict | None = None,
) -> dict:
    """Derive binary labels and overall status from a simulation snapshot.

    Parameters
    ----------
    sim_output:
        A dict returned by ``TissueModel.snapshot()``.
    patient_age:
        Chronological age of the patient in years.
    scenario:
        Optional full scenario dict (as stored in benchmark.json).
        When provided for Type B scenarios, ``intervention_effective`` is
        derived from the stored ``pre_intervention`` / ``post_intervention``
        data: effective if post DunedinPACE dropped ≥5% vs pre, or if post
        senescent fraction dropped ≥20% vs pre.

    Returns
    -------
    Dict of ground-truth labels.
    """
    horvath_age: float = sim_output["clocks"]["horvath"]
    grimace_age: float = sim_output["clocks"]["grimage_proxy"]
    dunedin_pace: float = sim_output["clocks"]["dunedinpace_proxy"]
    senescent_fraction: float = sim_output["senescent_fraction"]

    accelerated_aging = horvath_age > patient_age + 5
    fast_pacer = dunedin_pace > 1.1
    high_mortality_risk = grimace_age > patient_age + 7
    clock_discordance = abs(horvath_age - grimace_age) > 5
    high_senescence = senescent_fraction > 0.12

    if accelerated_aging and fast_pacer:
        overall_status = "accelerated"
    elif high_mortality_risk or high_senescence:
        overall_status = "at_risk"
    elif dunedin_pace < 0.95:
        overall_status = "decelerated"
    else:
        overall_status = "normal"

    # Intervention effectiveness — only computable for Type B scenarios that
    # carry pre/post simulation snapshots.
    intervention_effective: bool | None = None
    if scenario is not None and str(scenario.get("task_type", "")).startswith("B"):
        pre = scenario.get("pre_intervention", {})
        post = scenario.get("post_intervention", {})
        pre_dunedin = pre.get("dunedinpace_proxy")
        post_dunedin = post.get("dunedinpace_proxy")
        pre_sen = pre.get("senescent_fraction")
        post_sen = post.get("senescent_fraction")
        if pre_dunedin is not None and post_dunedin is not None:
            intervention_effective = post_dunedin < (pre_dunedin * 0.95)
        elif pre_sen is not None and post_sen is not None:
            intervention_effective = post_sen < (pre_sen * 0.80)

    return {
        "accelerated_aging": accelerated_aging,
        "fast_pacer": fast_pacer,
        "high_mortality_risk": high_mortality_risk,
        "clock_discordance": clock_discordance,
        "high_senescence": high_senescence,
        "intervention_effective": intervention_effective,
        "overall_status": overall_status,
    }


def validate_sim_output(sim_output: dict) -> tuple[bool, list[str]]:
    """Check that a simulation snapshot is structurally valid and in-range.

    Returns
    -------
    (is_valid, issues)
        ``is_valid`` is True iff ``issues`` is empty.
    """
    issues: list[str] = []

    for key in _EXPECTED_TOP_KEYS:
        if key not in sim_output:
            issues.append(f"missing key: '{key}'")

    if "clocks" in sim_output:
        for key in _EXPECTED_CLOCK_KEYS:
            if key not in sim_output["clocks"]:
                issues.append(f"missing clocks key: '{key}'")

    if "senescent_fraction" in sim_output:
        sf = sim_output["senescent_fraction"]
        if not (0.0 <= sf <= 0.5):
            issues.append(f"senescent_fraction {sf:.4f} outside [0.0, 0.5]")

    if "clocks" in sim_output:
        clocks = sim_output["clocks"]
        if "dunedinpace_proxy" in clocks:
            pace = clocks["dunedinpace_proxy"]
            if not (0.5 <= pace <= 3.0):
                issues.append(f"dunedinpace_proxy {pace:.4f} outside [0.5, 3.0]")
        if "horvath" in clocks:
            horvath = clocks["horvath"]
            if not (0.0 <= horvath <= 120.0):
                issues.append(f"horvath {horvath:.2f} outside [0, 120]")

    return len(issues) == 0, issues
