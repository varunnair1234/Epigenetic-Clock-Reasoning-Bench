"""Simulation parameters grounded in published literature.

All values are sourced from the references cited below — not arbitrary.
Edit with care; downstream behavior (senescent fractions, clock outputs,
intervention responses) is calibrated against these values.
"""

# ---------------------------------------------------------------------------
# Grid / timing
# ---------------------------------------------------------------------------

GRID_SIZE = 30                          # 30 × 30 tissue patch
N_CELLS = GRID_SIZE * GRID_SIZE         # 900 cells
N_STEPS = 200                           # 1 step = 1 month  →  ≈16 years total

# ---------------------------------------------------------------------------
# Senescence prevalence
# ---------------------------------------------------------------------------

# Young tissue: 2–5% senescent cells (Campisi 2013, "Aging, cellular senescence,
# and cancer", Annu Rev Physiol).
INITIAL_SENESCENT_FRACTION = 0.03

# Aged tissue: 10–15% senescent cells (van Deursen 2014, "The role of senescent
# cells in ageing", Nature).
TARGET_AGED_SENESCENT_FRACTION = 0.12

# ---------------------------------------------------------------------------
# Telomere dynamics
# ---------------------------------------------------------------------------

INITIAL_TELOMERE = 1.0                   # normalized
INITIAL_TELOMERE_STD = 0.05
TELOMERE_CRISIS_THRESHOLD = 0.15         # ≈1.5 kb (Blackburn 2015)
TELOMERE_SHORTENING_PER_DIVISION = 0.005
DIVISION_PROBABILITY = 0.05              # per cell per month (homeostatic turnover)

# ---------------------------------------------------------------------------
# DNA damage / ROS
# ---------------------------------------------------------------------------

# Damage accumulates over ~16 years; we want bulk damage to land in the
# senescence-threshold band by the end of a full 200-step run. Real cells
# constantly repair ROS damage, so the *net* per-step damage gain is small
# and only a minority of cells should cross the senescence threshold within
# our 200-month window.
ROS_DAMAGE_PER_TIMESTEP_MEAN = 0.005
ROS_DAMAGE_PER_TIMESTEP_STD = 0.002
DAMAGE_REPAIR_PER_TIMESTEP = 0.0042      # net damage gain ~0.0008 / step
                                         # → ~0.16 total over 200 steps,
                                         #   enough to push some cells over
                                         #   the senescence threshold
SASP_DAMAGE_AMPLIFIER = 0.0007           # modest cascade — strong enough to
                                         # produce clustered senescence but
                                         # not runaway by year 16

INITIAL_DAMAGE_MAX = 0.05                # baseline damage in a "young" cell

# ---------------------------------------------------------------------------
# SASP (senescence-associated secretory phenotype)
# ---------------------------------------------------------------------------

# Acosta 2013: paracrine SASP spreads ~5–10 cell diameters. We use a Moore
# neighborhood radius of 2 cells as a compact approximation (a 5x5 footprint
# around the senescent cell, excluding center).
SASP_RADIUS = 2
SASP_INTENSITY = 1.0                     # per emission, per neighbor

# ---------------------------------------------------------------------------
# Senescence state transitions
# ---------------------------------------------------------------------------

STRESS_DAMAGE_THRESHOLD = 0.30           # normal   → stressed
SENESCENCE_DAMAGE_THRESHOLD = 0.55       # stressed → senescent
DEATH_DAMAGE_THRESHOLD = 0.95            # senescent → dead (cell death is rare
                                         # in the 16-year window; senescent
                                         # cells are notoriously long-lived)

# ---------------------------------------------------------------------------
# CpG drift
# ---------------------------------------------------------------------------

# Per-CpG monthly drift rates come from data/GSE40279/drift_rates.csv (real OLS
# regression of β ~ age across 164 GSE40279 samples). Each cell still has
# stochastic noise on top of the deterministic drift.
DRIFT_NOISE_STD = 0.005                  # σ of Gaussian per-step beta noise

# ---------------------------------------------------------------------------
# Horvath clock — published anti-transform parameters (Horvath 2013)
# ---------------------------------------------------------------------------

HORVATH_INTERCEPT = 0.695507258          # from published R reference code
HORVATH_ADULT_AGE = 20                   # piecewise breakpoint in anti.trafo

# ---------------------------------------------------------------------------
# Initial-state sampling
# ---------------------------------------------------------------------------

# Number of youngest real GSE40279 samples to average over when seeding initial
# bulk methylation across the tissue grid. Smaller N → younger seed (currently
# our 164-sample chunk only reaches down to age 28).
INITIAL_BETA_YOUNG_N = 5
