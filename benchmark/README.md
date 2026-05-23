# benchmark/

JSON benchmark file consumed by the eval harness. The schema is the **contract** that the scenario generator (Stage 2) and the eval harness (Stage 3) both depend on — so both sides can be built in parallel.

## Files

- **`benchmark.json`** — currently 5 hand-crafted "smoke" scenarios. Will be replaced by simulator-generated scenarios (500+) once the generator is built.
- **`ground_truth.py`** — derives the binary labels from a simulation snapshot (used by the generator).

## Schema

```json
{
  "schema_version": "0.1",
  "source": "hand_crafted_smoke | simulator_generated",
  "scoring_dimensions": { ... },        // global rubric, 100 pts
  "ground_truth_thresholds": { ... },   // the rules each label uses
  "scenarios": [
    {
      "scenario_id": "SMOKE-A1",
      "task_type": "A_clock_interpretation | B_intervention_reasoning | C_multi_tissue_discordance | D_confounders_artifacts",
      "patient_profile": {
        "chronological_age": int,
        "sex": "M" | "F",
        "tissue": string,
        "intervention": string | null,
        "intervention_months": int | null,
        "medical_history": string?      // optional, for Type D
      },
      "clock_values": {
        "baseline": {"horvath": float, "grimage": float, "dunedinpace": float},
        "post": {...}                   // present only for intervention scenarios
      },
      "question": string,
      "ground_truth": {
        "labels": {
          "accelerated_aging": bool,
          "fast_pacer": bool,
          "high_mortality_risk": bool,
          "clock_discordance": bool,
          "intervention_effective": bool | null
        },
        "primary_signal_clock": "horvath" | "grimage" | "dunedinpace" | null,
        "expected_keywords": [string, ...],  // explanation must mention at least N of these
        "explanation": string                // human-readable rationale
      },
      "scoring_weights": {
        "aging_status": int,               // 0 or 25
        "clock_discordance": int,          // 0 or 20
        "intervention_efficacy": int,      // 0 or 20
        "tissue_specificity": int,         // 0 or 20
        "confounder_awareness": int        // 0 or 15
      }
    }
  ]
}
```

### Scoring weights by task type

| Task | aging_status | discordance | intervention | tissue | confounder | max |
|------|-----:|------:|-----:|-----:|-----:|----:|
| A — Clock interpretation | 25 | 20 |  0 |  0 |  0 | 45 |
| B — Intervention reasoning |  0 | 20 | 20 |  0 |  0 | 40 |
| C — Multi-tissue discordance | 25 |  0 |  0 | 20 |  0 | 45 |
| D — Confounders & artifacts | 25 |  0 |  0 |  0 | 15 | 40 |

The harness scores per dimension and normalizes within task type, then aggregates to a model-level total.

### Ground-truth label rules

From `benchmark/ground_truth.py` (and the project PDF):

| Label | Rule |
|-------|------|
| `accelerated_aging` | `horvath_age > chronological_age + 5` |
| `fast_pacer` | `dunedinpace > 1.1` |
| `high_mortality_risk` | `grimage_age > chronological_age + 7` |
| `clock_discordance` | `abs(horvath_accel - grimage_accel) > 5` |
| `intervention_effective` | `post_senescent_fraction < 0.80 * baseline_senescent_fraction` |

For simulator-derived scenarios, these are computed mechanically from `TissueModel.snapshot()`. For the hand-crafted smoke scenarios in this file, the same rules were applied to the chosen clock values.

## How the harness uses this file

```
for scenario in benchmark.scenarios:
    prompt = build_prompt(scenario.patient_profile,
                          scenario.clock_values,
                          scenario.question)
    for model in [claude, gemini, biollm]:
        response = model(prompt)              # JSON {labels, explanation}
        score = score_response(response, scenario.ground_truth,
                               scenario.scoring_weights)
        leaderboard.append((scenario.scenario_id, model.name, score))
```

## How the generator will populate this file

```
for seed, intervention, task_type in scenario_specs:
    snap_baseline = run_simulator(seed=seed)
    snap_post = run_simulator(seed=seed, intervention=intervention) if intervention else None
    scenario = {
        "scenario_id": f"GEN-{task_type}-{i}",
        "patient_profile": derive_profile(snap_baseline, intervention),
        "clock_values": derive_clock_values(snap_baseline, snap_post),
        "question": template_for(task_type).format(...),
        "ground_truth": derive_ground_truth(snap_baseline, snap_post),
        "scoring_weights": WEIGHTS_BY_TASK[task_type],
    }
```

When the generator overwrites `benchmark.json`, the harness's behavior is unchanged — that's the point of locking the schema.
