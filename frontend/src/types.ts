// Types match api/server.py response shapes.

export interface Stats {
  n_scenarios: number;
  n_models: number;
  best_accuracy_pct: number;
  n_task_types: number;
  data_source: string;
}

export interface Snapshot {
  step: number;
  chronological_age_years: number;
  n_total: number;
  n_live: number;
  n_senescent: number;
  n_stressed: number;
  n_dead: number;
  senescent_fraction: number;
  mean_damage: number;
  mean_telomere: number;
  sasp_burden: number;
  bulk_methylation_mean: number;
  clocks: {
    horvath: number;
    grimage_proxy: number;
    dunedinpace_proxy: number;
  };
  grid: number[][];  // GRID_SIZE × GRID_SIZE, codes 0..3
}

export interface SimulateResponse {
  seed: number;
  steps: number;
  tissue: string;
  grid_size: number;
  trajectory: Snapshot[];
}

export interface LeaderboardRow {
  task_type: string;
  model: string;
  n_scenarios: number;
  earned: number;
  max: number;
  pct: number;
  errors: number;
  parse_fails: number;
}

export interface ErrorBreakdownRow {
  model: string;
  category: string;
  count: number;
  pct_of_wrong: number;
}

export interface BenchmarkScenario {
  scenario_id: number;
  task_type: string;          // "A" | "B" | "C" | "D"
  patient_age: number;
  patient_context: string;
  clock_values: Record<string, number>;
  question: string;
  ground_truth: {
    accelerated_aging: boolean;
    fast_pacer: boolean;
    high_mortality_risk: boolean;
    clock_discordance: boolean;
    high_senescence: boolean;
    intervention_effective: boolean | null;
    overall_status: string;   // "accelerated" | "normal" | "decelerated" | "at_risk"
  };
}
