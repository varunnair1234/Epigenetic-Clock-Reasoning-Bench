"""Scenario generator — converts MESA simulation outputs into natural-language
benchmark scenarios via Claude API.

Simulation notes:
  - TissueModel uses a fixed 30x30 grid (params.GRID_SIZE); no grid_size arg.
  - No tissue_type parameter; tissue differences are simulated via step count.
  - For Type B, ROS damage rate is temporarily monkey-patched (-30%) on the
    post-intervention model; cell_agent reads params at runtime so this works.
"""

from __future__ import annotations

import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure repo root is importable whether run from repo root or benchmark/.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import anthropic
from tqdm import tqdm

from simulation.tissue_model import TissueModel
import simulation.params as _params
from benchmark.ground_truth import derive_ground_truth, validate_sim_output

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TISSUE_TYPES = ["blood", "saliva", "buccal", "adipose"]

_INTERVENTIONS = [
    "caloric restriction",
    "senolytic therapy (D+Q)",
    "rapamycin",
    "aerobic exercise program",
    "NAD+ supplementation",
]

_CONFOUNDERS = [
    "Patient started metformin 6 months ago",
    "Recent chemotherapy altered cell composition",
    "Sample was stored for 48 hours before processing",
    "Patient has been on SSRIs for 1 year",
    "Patient lost 15% body weight in past 6 months",
    "Patient recovered from severe COVID-19 3 months ago",
    "Blood sample drawn during acute infection (elevated WBC)",
    "Patient is a current smoker (20 pack-years)",
]

_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM_PROMPT = (
    "You are generating benchmark scenarios to test LLM reasoning about epigenetic "
    "aging clocks. Generate a realistic clinical vignette. Use real clock names: "
    "Horvath, GrimAge, DunedinPACE. Respond ONLY in valid JSON with no markdown "
    "backticks or code fences."
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run_model(start_age: float, n_steps: int, seed: int) -> dict[str, Any]:
    """Build and run a TissueModel; return the final snapshot."""
    model = TissueModel(chronological_start_age=start_age, seed=seed)
    for _ in range(n_steps):
        model.step()
    return model.snapshot()


# ---------------------------------------------------------------------------
# ScenarioGenerator
# ---------------------------------------------------------------------------

class ScenarioGenerator:
    def __init__(self) -> None:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self.client = anthropic.Anthropic(api_key=api_key)

    # ------------------------------------------------------------------ private

    def _call_claude(self, user_prompt: str, max_retries: int = 3) -> dict | None:
        """Call Claude and parse JSON response; retry up to max_retries."""
        for attempt in range(max_retries):
            try:
                msg = self.client.messages.create(
                    model=_MODEL,
                    max_tokens=1024,
                    system=_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                raw = msg.content[0].text.strip()
                # Strip accidental fences just in case
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                return json.loads(raw.strip())
            except Exception:
                if attempt == max_retries - 1:
                    return None
        return None

    def _fallback_vignette(
        self,
        patient_age: int,
        horvath: float,
        grimace: float,
        dunedin: float,
        sen_pct: float = 0.0,
    ) -> dict:
        return {
            "patient_context": (
                f"A {patient_age}-year-old patient underwent epigenetic clock testing."
            ),
            "clock_values": {
                "horvath": round(horvath, 1),
                "grimage": round(grimace, 1),
                "dunedin_pace": round(dunedin, 3),
                "senescent_fraction_pct": round(sen_pct, 1),
            },
            "question": (
                f"Given Horvath age {horvath:.1f}, GrimAge {grimace:.1f}, and "
                f"DunedinPACE {dunedin:.3f}, what does this clock profile suggest "
                "about this patient's aging trajectory?"
            ),
        }

    # ------------------------------------------------------------------ task A

    def _generate_type_a(self, scenario_id: int) -> dict | None:
        """Clock Interpretation — single tissue, read all three clocks."""
        patient_age = random.randint(30, 75)
        n_steps = random.randint(60, 200)
        tissue_type = random.choice(_TISSUE_TYPES)
        seed = random.randint(0, 2**31 - 1)

        snap = _run_model(start_age=float(patient_age), n_steps=n_steps, seed=seed)
        valid, _ = validate_sim_output(snap)
        if not valid:
            return None

        gt = derive_ground_truth(snap, patient_age)
        horvath = snap["clocks"]["horvath"]
        grimace = snap["clocks"]["grimage_proxy"]
        dunedin = snap["clocks"]["dunedinpace_proxy"]
        sen_pct = snap["senescent_fraction"] * 100

        user_prompt = (
            f"A {patient_age}-year-old patient had epigenetic clock testing on a "
            f"{tissue_type} sample. Results:\n"
            f"- Horvath clock biological age: {horvath:.1f} years\n"
            f"- GrimAge estimate: {grimace:.1f} years\n"
            f"- DunedinPACE (pace of aging): {dunedin:.3f}\n"
            f"- Senescent cell fraction: {sen_pct:.1f}%\n\n"
            "Generate a JSON object with exactly these fields:\n"
            "{\n"
            '  "patient_context": "One sentence describing the patient including age, '
            'sex, and reason for testing",\n'
            '  "clock_values": {\n'
            f'    "horvath": {horvath:.1f},\n'
            f'    "grimage": {grimace:.1f},\n'
            f'    "dunedin_pace": {dunedin:.3f},\n'
            f'    "senescent_fraction_pct": {sen_pct:.1f}\n'
            "  },\n"
            '  "question": "A specific question that requires reasoning about multiple '
            "clocks together. Ask about what the pattern of results indicates about aging "
            'trajectory, discordance between clocks, or what the most important finding is."\n'
            "}"
        )

        vignette = self._call_claude(user_prompt)
        if vignette is None:
            vignette = self._fallback_vignette(patient_age, horvath, grimace, dunedin, sen_pct)

        return {
            "scenario_id": scenario_id,
            "task_type": "A",
            "patient_age": patient_age,
            "patient_context": vignette.get("patient_context", ""),
            "clock_values": vignette.get("clock_values", {}),
            "question": vignette.get("question", ""),
            "ground_truth": gt,
            "simulation_params": {
                "steps": n_steps,
                "grid": "30x30",
                "tissue_type": tissue_type,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------ task B

    def _generate_type_b(self, scenario_id: int) -> dict | None:
        """Intervention Reasoning — pre/post clock comparison."""
        patient_age = random.randint(30, 75)
        n_steps_pre = random.randint(60, 100)
        n_steps_post = random.randint(40, 80)
        intervention = random.choice(_INTERVENTIONS)
        tissue_type = random.choice(_TISSUE_TYPES)
        seed = random.randint(0, 2**31 - 1)

        # Phase 1: pre-intervention baseline
        snap_pre = _run_model(
            start_age=float(patient_age), n_steps=n_steps_pre, seed=seed
        )
        valid1, _ = validate_sim_output(snap_pre)
        if not valid1:
            return None

        # Phase 2: post-intervention — temporarily reduce ROS damage by 30%.
        # cell_agent reads P.ROS_DAMAGE_PER_TIMESTEP_MEAN at call time via module
        # reference, so patching the module attribute is sufficient.
        orig_ros = _params.ROS_DAMAGE_PER_TIMESTEP_MEAN
        _params.ROS_DAMAGE_PER_TIMESTEP_MEAN = orig_ros * 0.7
        try:
            post_start_age = snap_pre["chronological_age_years"]
            snap_post = _run_model(
                start_age=post_start_age, n_steps=n_steps_post, seed=seed + 1
            )
        finally:
            _params.ROS_DAMAGE_PER_TIMESTEP_MEAN = orig_ros

        valid2, _ = validate_sim_output(snap_post)
        if not valid2:
            return None

        gt = derive_ground_truth(snap_post, patient_age)

        pre_h = snap_pre["clocks"]["horvath"]
        pre_g = snap_pre["clocks"]["grimage_proxy"]
        pre_d = snap_pre["clocks"]["dunedinpace_proxy"]
        post_h = snap_post["clocks"]["horvath"]
        post_g = snap_post["clocks"]["grimage_proxy"]
        post_d = snap_post["clocks"]["dunedinpace_proxy"]
        sen_pct = snap_post["senescent_fraction"] * 100

        user_prompt = (
            f"A {patient_age}-year-old patient had epigenetic clock testing before and "
            f"after {intervention} for {n_steps_post} months.\n\n"
            f"Pre-intervention: Horvath {pre_h:.1f}, GrimAge {pre_g:.1f}, "
            f"DunedinPACE {pre_d:.3f}\n"
            f"Post-intervention: Horvath {post_h:.1f}, GrimAge {post_g:.1f}, "
            f"DunedinPACE {post_d:.3f}\n"
            f"Senescent cell fraction post: {sen_pct:.1f}%\n\n"
            "Generate a JSON object with exactly these fields:\n"
            "{\n"
            '  "patient_context": "One sentence describing the patient, intervention, '
            'and duration",\n'
            '  "clock_values": {\n'
            f'    "horvath": {post_h:.1f},\n'
            f'    "grimage": {post_g:.1f},\n'
            f'    "dunedin_pace": {post_d:.3f},\n'
            f'    "senescent_fraction_pct": {sen_pct:.1f}\n'
            "  },\n"
            '  "question": "A specific question asking whether the intervention is '
            "working and what the pattern of clock changes indicates about the "
            'patient\'s biological response."\n'
            "}"
        )

        vignette = self._call_claude(user_prompt)
        if vignette is None:
            vignette = self._fallback_vignette(patient_age, post_h, post_g, post_d, sen_pct)

        return {
            "scenario_id": scenario_id,
            "task_type": "B",
            "patient_age": patient_age,
            "patient_context": vignette.get("patient_context", ""),
            "clock_values": vignette.get("clock_values", {}),
            "question": vignette.get("question", ""),
            "ground_truth": gt,
            "pre_intervention": {
                "horvath": pre_h,
                "grimage_proxy": pre_g,
                "dunedinpace_proxy": pre_d,
            },
            "post_intervention": {
                "horvath": post_h,
                "grimage_proxy": post_g,
                "dunedinpace_proxy": post_d,
            },
            "intervention_type": intervention,
            "simulation_params": {
                "steps": n_steps_pre + n_steps_post,
                "grid": "30x30",
                "tissue_type": tissue_type,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------ task C

    def _generate_type_c(self, scenario_id: int) -> dict | None:
        """Multi-Tissue Discordance — same patient, two tissue types."""
        patient_age = random.randint(30, 75)
        n_steps = random.randint(60, 200)
        seed = random.randint(0, 2**31 - 1)

        tissue_1_type = "blood"
        tissue_2_type = random.choice(["brain", "saliva"])

        # Tissue 1: blood — standard run
        snap_1 = _run_model(
            start_age=float(patient_age), n_steps=n_steps, seed=seed
        )
        valid1, _ = validate_sim_output(snap_1)
        if not valid1:
            return None

        # Tissue 2: brain ages faster (1.5x steps); saliva uses same step count
        n_steps_2 = int(n_steps * 1.5) if tissue_2_type == "brain" else n_steps
        snap_2 = _run_model(
            start_age=float(patient_age), n_steps=n_steps_2, seed=seed + 100
        )
        valid2, _ = validate_sim_output(snap_2)
        if not valid2:
            return None

        gt = derive_ground_truth(snap_1, patient_age)

        h1 = snap_1["clocks"]["horvath"]
        g1 = snap_1["clocks"]["grimage_proxy"]
        d1 = snap_1["clocks"]["dunedinpace_proxy"]
        h2 = snap_2["clocks"]["horvath"]
        g2 = snap_2["clocks"]["grimage_proxy"]
        d2 = snap_2["clocks"]["dunedinpace_proxy"]
        sen1 = snap_1["senescent_fraction"] * 100
        sen2 = snap_2["senescent_fraction"] * 100

        user_prompt = (
            f"A {patient_age}-year-old patient had epigenetic clock testing on two "
            f"tissue types.\n\n"
            f"{tissue_1_type.capitalize()} sample:\n"
            f"  Horvath {h1:.1f}, GrimAge {g1:.1f}, DunedinPACE {d1:.3f}, "
            f"senescent fraction {sen1:.1f}%\n\n"
            f"{tissue_2_type.capitalize()} sample:\n"
            f"  Horvath {h2:.1f}, GrimAge {g2:.1f}, DunedinPACE {d2:.3f}, "
            f"senescent fraction {sen2:.1f}%\n\n"
            "Generate a JSON object with exactly these fields:\n"
            "{\n"
            '  "patient_context": "One sentence describing the patient and the '
            'multi-tissue testing context",\n'
            '  "clock_values": {\n'
            f'    "horvath": {h1:.1f},\n'
            f'    "grimage": {g1:.1f},\n'
            f'    "dunedin_pace": {d1:.3f},\n'
            f'    "senescent_fraction_pct": {sen1:.1f}\n'
            "  },\n"
            '  "question": "A specific question about the tissue-specific discordance '
            "and what the difference in clock readings between tissues indicates about "
            'organ-level aging differences in this patient."\n'
            "}"
        )

        vignette = self._call_claude(user_prompt)
        if vignette is None:
            vignette = self._fallback_vignette(patient_age, h1, g1, d1, sen1)

        return {
            "scenario_id": scenario_id,
            "task_type": "C",
            "patient_age": patient_age,
            "patient_context": vignette.get("patient_context", ""),
            "clock_values": vignette.get("clock_values", {}),
            "question": vignette.get("question", ""),
            "ground_truth": gt,
            "tissue_1": {
                "type": tissue_1_type,
                "clocks": {"horvath": h1, "grimage_proxy": g1, "dunedinpace_proxy": d1},
            },
            "tissue_2": {
                "type": tissue_2_type,
                "clocks": {"horvath": h2, "grimage_proxy": g2, "dunedinpace_proxy": d2},
            },
            "simulation_params": {
                "steps": n_steps,
                "grid": "30x30",
                "tissue_type": f"{tissue_1_type}+{tissue_2_type}",
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------ task D

    def _generate_type_d(self, scenario_id: int) -> dict | None:
        """Confounders & Artifacts — clock values plus a confounding factor."""
        patient_age = random.randint(30, 75)
        n_steps = random.randint(60, 200)
        tissue_type = random.choice(_TISSUE_TYPES)
        confounder = random.choice(_CONFOUNDERS)
        seed = random.randint(0, 2**31 - 1)

        snap = _run_model(start_age=float(patient_age), n_steps=n_steps, seed=seed)
        valid, _ = validate_sim_output(snap)
        if not valid:
            return None

        gt = derive_ground_truth(snap, patient_age)
        horvath = snap["clocks"]["horvath"]
        grimace = snap["clocks"]["grimage_proxy"]
        dunedin = snap["clocks"]["dunedinpace_proxy"]
        sen_pct = snap["senescent_fraction"] * 100

        user_prompt = (
            f"A {patient_age}-year-old patient had epigenetic clock testing on a "
            f"{tissue_type} sample.\n\n"
            f"Clock results:\n"
            f"- Horvath clock biological age: {horvath:.1f} years\n"
            f"- GrimAge estimate: {grimace:.1f} years\n"
            f"- DunedinPACE: {dunedin:.3f}\n"
            f"- Senescent cell fraction: {sen_pct:.1f}%\n\n"
            f"Clinical note: {confounder}\n\n"
            "Generate a JSON object with exactly these fields:\n"
            "{\n"
            '  "patient_context": "One sentence describing the patient, including the '
            'relevant clinical factor",\n'
            '  "clock_values": {\n'
            f'    "horvath": {horvath:.1f},\n'
            f'    "grimage": {grimace:.1f},\n'
            f'    "dunedin_pace": {dunedin:.3f},\n'
            f'    "senescent_fraction_pct": {sen_pct:.1f}\n'
            "  },\n"
            '  "question": "A specific question asking whether these clock readings '
            "reflect true biological aging or a confounding artifact, and how the "
            'clinician should interpret them given the clinical note."\n'
            "}"
        )

        vignette = self._call_claude(user_prompt)
        if vignette is None:
            vignette = self._fallback_vignette(patient_age, horvath, grimace, dunedin, sen_pct)

        return {
            "scenario_id": scenario_id,
            "task_type": "D",
            "patient_age": patient_age,
            "patient_context": vignette.get("patient_context", ""),
            "clock_values": vignette.get("clock_values", {}),
            "question": vignette.get("question", ""),
            "ground_truth": gt,
            "confounder": confounder,
            "simulation_params": {
                "steps": n_steps,
                "grid": "30x30",
                "tissue_type": tissue_type,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------ public

    def generate_single_scenario(self, task_type: str, scenario_id: int) -> dict | None:
        """Generate one scenario of the given task type. Returns None on failure."""
        return {
            "A": self._generate_type_a,
            "B": self._generate_type_b,
            "C": self._generate_type_c,
            "D": self._generate_type_d,
        }[task_type](scenario_id)

    def generate_benchmark(
        self,
        n_scenarios: int = 200,
        output_path: str = "benchmark/benchmark.json",
    ) -> None:
        """Generate n_scenarios and write to output_path as JSON."""
        # Use max(1, ...) so small n (e.g. 4) still produces 1 of each type.
        task_counts = {
            "A": max(1, int(n_scenarios * 0.40)),
            "B": max(1, int(n_scenarios * 0.25)),
            "C": max(1, int(n_scenarios * 0.20)),
        }
        task_counts["D"] = max(1, n_scenarios - sum(task_counts.values()))

        task_order: list[str] = []
        for t, count in task_counts.items():
            task_order.extend([t] * count)

        scenarios: list[dict] = []
        scenario_id = 0
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        for task_type in tqdm(task_order, desc="Generating scenarios"):
            result = None
            for _ in range(3):
                result = self.generate_single_scenario(task_type, scenario_id)
                if result is not None:
                    break
            if result is None:
                print(
                    f"\nWarning: scenario {scenario_id} (type {task_type}) "
                    "failed after 3 retries — skipping."
                )
            else:
                scenarios.append(result)
            scenario_id += 1

            # Incremental save every 10 scenarios
            if scenario_id % 10 == 0:
                out.write_text(json.dumps(scenarios, indent=2, default=str))

        out.write_text(json.dumps(scenarios, indent=2, default=str))

        type_counts = {t: sum(1 for s in scenarios if s["task_type"] == t) for t in "ABCD"}
        print(f"\nGenerated {len(scenarios)} scenarios")
        print(f"  Type A: {type_counts['A']}")
        print(f"  Type B: {type_counts['B']}")
        print(f"  Type C: {type_counts['C']}")
        print(f"  Type D: {type_counts['D']}")
        print(f"Saved to {output_path}")
