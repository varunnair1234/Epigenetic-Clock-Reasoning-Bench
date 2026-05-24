"""Statistical-rigor add-ons: baselines + per-label confusion / F1 / balanced-acc.

Why this exists
---------------
Raw `leaderboard.csv` reports weighted-dimension % per (model, task). With
heavily imbalanced labels (e.g. `high_mortality_risk` True in 84% of scenarios)
that percentage is hard to interpret. This module adds:

  1. THREE NAIVE BASELINES (scored with the same harness rubric):
     - always_true:    predict True for every label
     - always_false:   predict False for every label
     - majority_class: predict the majority class per label (data-driven)
     Their leaderboard rows make the headline number interpretable.

  2. PER-LABEL CONFUSION MATRICES + F1 + BALANCED ACCURACY for every model.
     Reveals which models truly reason vs. which match the majority class.

  3. CLASS DISTRIBUTION for the benchmark — surfaces the imbalance honestly.

Outputs (in --out, default eval_outputs/):
  per_label_metrics.csv      flat rows (model, label, tp, fp, tn, fn, ...)
  baseline_leaderboard.csv   same schema as leaderboard.csv, baselines only
  metrics.json               nested: per_label + class_distribution + baselines
  class_distribution.json    label True/False counts from benchmark

Usage:
  python -m eval.metrics
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from eval import scorer

# Labels we evaluate against. `intervention_effective` is null for many
# scenarios (no intervention described) — we still include it but treat null
# as a separate non-applicable case.
BINARY_LABELS = [
    "accelerated_aging",
    "fast_pacer",
    "high_mortality_risk",
    "clock_discordance",
]
TERNARY_LABELS = ["intervention_effective"]  # True | False | None


# ---------- Baseline prediction strategies ----------

def _majority_per_label(benchmark: list[dict]) -> dict[str, bool]:
    """Return {label: majority_value} from ground-truth across the benchmark."""
    out: dict[str, bool] = {}
    for label in BINARY_LABELS + TERNARY_LABELS:
        true_count = sum(1 for s in benchmark
                         if s.get("ground_truth", {}).get(label) is True)
        false_count = sum(1 for s in benchmark
                          if s.get("ground_truth", {}).get(label) is False)
        out[label] = true_count >= false_count
    return out


def baseline_prediction(strategy: str, scenario: dict, majority: dict | None = None) -> dict:
    """Return a predicted-labels dict for one scenario under a given strategy."""
    if strategy == "always_true":
        labels = {k: True for k in BINARY_LABELS}
    elif strategy == "always_false":
        labels = {k: False for k in BINARY_LABELS}
    elif strategy == "majority_class":
        assert majority is not None, "majority_class requires the majority dict"
        labels = {k: majority[k] for k in BINARY_LABELS}
    else:
        raise ValueError(f"unknown strategy: {strategy}")
    # intervention_effective: only meaningful when intervention is described.
    gt_int = scenario.get("ground_truth", {}).get("intervention_effective")
    if gt_int is None:
        labels["intervention_effective"] = None  # don't claim what isn't there
    else:
        if strategy == "always_true":
            labels["intervention_effective"] = True
        elif strategy == "always_false":
            labels["intervention_effective"] = False
        else:
            labels["intervention_effective"] = majority["intervention_effective"]
    return labels


# ---------- Per-label confusion + metrics ----------

def confusion_for_label(predictions: list[dict], ground_truths: list[dict], label: str) -> dict:
    """Return TP/FP/TN/FN counts + derived metrics for one label.

    Only scenarios where ground truth is non-null contribute to confusion math.
    """
    tp = fp = tn = fn = 0
    skipped = 0
    for p, g in zip(predictions, ground_truths):
        gv = g.get(label)
        pv = (p or {}).get(label) if p else None
        if gv is None:
            skipped += 1
            continue
        if pv is True and gv is True:
            tp += 1
        elif pv is False and gv is False:
            tn += 1
        elif pv is True and gv is False:
            fp += 1
        elif pv is False and gv is True:
            fn += 1
        else:
            # pv is None (model didn't emit / parse-fail) — count as wrong vs
            # ground truth; treat as the OPPOSITE of gv for accuracy purposes.
            if gv is True:
                fn += 1
            else:
                fp += 1
    n = tp + fp + tn + fn
    if n == 0:
        return {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "n": 0, "skipped": skipped,
                "precision": None, "recall": None, "f1": None,
                "balanced_accuracy": None, "accuracy": None}
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    sensitivity = tp / (tp + fn) if (tp + fn) else 0.0
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    balanced_acc = (sensitivity + specificity) / 2
    accuracy = (tp + tn) / n
    return {
        "tp": tp, "fp": fp, "tn": tn, "fn": fn, "n": n, "skipped": skipped,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "balanced_accuracy": round(balanced_acc, 4),
        "accuracy": round(accuracy, 4),
    }


# ---------- Class distribution ----------

def class_distribution(benchmark: list[dict]) -> dict:
    """Per-label counts of True / False / None in ground truth."""
    out = {}
    for label in BINARY_LABELS + TERNARY_LABELS:
        t = sum(1 for s in benchmark if s.get("ground_truth", {}).get(label) is True)
        f = sum(1 for s in benchmark if s.get("ground_truth", {}).get(label) is False)
        n = sum(1 for s in benchmark if s.get("ground_truth", {}).get(label) is None)
        total_non_null = t + f
        out[label] = {
            "true": t,
            "false": f,
            "null": n,
            "pct_true": round(100 * t / total_non_null, 2) if total_non_null else None,
            "imbalance_ratio": round(max(t, f) / max(1, min(t, f)), 2) if min(t, f) > 0 else None,
        }
    return out


# ---------- Baseline leaderboard rows ----------

def score_baseline(strategy: str, benchmark: list[dict], majority: dict) -> dict:
    """Apply the eval-harness scoring rubric to a baseline strategy.

    Returns (leaderboard_rows, per_scenario_predictions).
    Leaderboard rows match the schema produced by run_eval.py.
    """
    agg = defaultdict(lambda: {"earned": 0, "max": 0, "n": 0})
    predictions = []
    for scenario in benchmark:
        labels = baseline_prediction(strategy, scenario, majority)
        predictions.append(labels)
        # Mimic a model response so we can reuse scorer.score
        parsed = {"labels": labels, "explanation": "", "confidence": 0.0}
        sc = scorer.score(parsed, scenario.get("ground_truth", {}),
                          scenario.get("task_type", ""))
        task_full = scorer.task_full_name(scenario.get("task_type", ""))
        for key in (("ALL", strategy), (task_full, strategy)):
            row = agg[key]
            row["earned"] += sc["earned"]
            row["max"] += sc["max"]
            row["n"] += 1

    leaderboard_rows = []
    for (task, model), row in sorted(agg.items()):
        pct = (row["earned"] / row["max"] * 100) if row["max"] else 0
        leaderboard_rows.append({
            "task_type": task, "model": model, "n_scenarios": row["n"],
            "earned": row["earned"], "max": row["max"], "pct": round(pct, 1),
            "errors": 0, "parse_fails": 0,
        })
    return {"leaderboard": leaderboard_rows, "predictions": predictions}


# ---------- Main ----------

def main() -> int:
    ap = argparse.ArgumentParser(description="Baselines + per-label F1 / confusion / class dist.")
    ap.add_argument("--benchmark", type=Path, default=Path("benchmark/benchmark.json"))
    ap.add_argument("--details",  type=Path, default=Path("eval_outputs/details.json"))
    ap.add_argument("--out",      type=Path, default=Path("eval_outputs"))
    args = ap.parse_args()

    if not args.benchmark.exists():
        raise SystemExit(f"benchmark not found: {args.benchmark}")
    benchmark = json.loads(args.benchmark.read_text())
    if not isinstance(benchmark, list):
        benchmark = benchmark.get("scenarios", [])

    ground_truths = [s.get("ground_truth", {}) for s in benchmark]

    # ----- Per-label metrics for each real model (from details.json) -----
    per_label_rows: list[dict] = []
    metrics_json: dict[str, Any] = {"models": {}, "baselines": {},
                                    "class_distribution": class_distribution(benchmark)}

    if args.details.exists():
        details = json.loads(args.details.read_text())
        # Group details by model so predictions align with benchmark order.
        by_model: dict[str, list[dict | None]] = defaultdict(lambda: [None] * len(benchmark))
        scen_index = {str(s.get("scenario_id")): i for i, s in enumerate(benchmark)}
        for d in details:
            i = scen_index.get(str(d.get("scenario_id")))
            if i is None:
                continue
            by_model[d["model"]][i] = d.get("predicted_labels")

        for model, preds in by_model.items():
            metrics_json["models"][model] = {}
            for label in BINARY_LABELS + TERNARY_LABELS:
                cm = confusion_for_label(preds, ground_truths, label)
                metrics_json["models"][model][label] = cm
                per_label_rows.append({
                    "model": model, "label": label, **cm,
                })
    else:
        print(f"⚠ details.json not found at {args.details} — skipping real-model metrics")

    # ----- Baselines: run all 3, score, compute per-label metrics -----
    majority = _majority_per_label(benchmark)
    baseline_lb_rows: list[dict] = []
    for strategy in ["always_true", "always_false", "majority_class"]:
        result = score_baseline(strategy, benchmark, majority)
        baseline_lb_rows.extend(result["leaderboard"])
        metrics_json["baselines"][strategy] = {
            "leaderboard": result["leaderboard"],
            "per_label": {},
        }
        for label in BINARY_LABELS + TERNARY_LABELS:
            cm = confusion_for_label(result["predictions"], ground_truths, label)
            metrics_json["baselines"][strategy]["per_label"][label] = cm
            per_label_rows.append({
                "model": strategy, "label": label, **cm,
            })

    metrics_json["majority_per_label"] = majority

    # ----- Write outputs -----
    args.out.mkdir(parents=True, exist_ok=True)

    per_label_csv = args.out / "per_label_metrics.csv"
    with per_label_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "label", "n", "tp", "fp", "tn", "fn",
                    "accuracy", "balanced_accuracy", "precision", "recall", "f1"])
        for r in per_label_rows:
            w.writerow([r["model"], r["label"], r["n"],
                        r["tp"], r["fp"], r["tn"], r["fn"],
                        r["accuracy"], r["balanced_accuracy"],
                        r["precision"], r["recall"], r["f1"]])

    baseline_lb_csv = args.out / "baseline_leaderboard.csv"
    with baseline_lb_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["task_type", "model", "n_scenarios", "earned", "max",
                    "pct", "errors", "parse_fails"])
        for r in baseline_lb_rows:
            w.writerow([r["task_type"], r["model"], r["n_scenarios"],
                        r["earned"], r["max"], r["pct"],
                        r["errors"], r["parse_fails"]])

    (args.out / "metrics.json").write_text(json.dumps(metrics_json, indent=2))
    (args.out / "class_distribution.json").write_text(
        json.dumps(metrics_json["class_distribution"], indent=2))

    print(f"Wrote: {per_label_csv}")
    print(f"Wrote: {baseline_lb_csv}")
    print(f"Wrote: {args.out / 'metrics.json'}")
    print(f"Wrote: {args.out / 'class_distribution.json'}")

    # ----- Console summary -----
    print()
    print("=" * 70)
    print("BASELINE LEADERBOARD")
    print("=" * 70)
    print(f"{'task_type':<32} {'baseline':<16} {'pts':>10}  {'pct':>6}")
    for r in baseline_lb_rows:
        if r["task_type"] != "ALL":
            continue
        print(f"{r['task_type']:<32} {r['model']:<16} {r['earned']:>4}/{r['max']:<4}  {r['pct']:>5.1f}%")
    print()
    print("=" * 70)
    print("CLASS IMBALANCE (% True in ground truth)")
    print("=" * 70)
    cd = metrics_json["class_distribution"]
    for label in BINARY_LABELS + TERNARY_LABELS:
        d = cd[label]
        t, f, n_ = d["true"], d["false"], d.get("null", 0)
        pct = d["pct_true"]
        marker = "  ⚠ SEVERE" if pct is not None and (pct < 15 or pct > 85) else ""
        print(f"  {label:<26}  True={t:>4}  False={f:>4}  null={n_:>4}  "
              f"pct_true={pct if pct is not None else 'n/a'}%{marker}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
