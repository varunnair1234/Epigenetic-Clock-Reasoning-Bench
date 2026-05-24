"""Confidence-calibration analysis.

Reads ``eval_outputs/details.json`` (produced by run_eval.py *after* the
prompt change that asks for a ``confidence`` field). For each model, bins
the (predicted_confidence, was_correct) pairs and computes:

    - calibration curve (mean accuracy per confidence bucket)
    - Expected Calibration Error (ECE)
    - overconfidence rate  (high-confidence but wrong)
    - underconfidence rate (low-confidence but right)
    - per-task-type breakdown

"Was correct" = scenario earned full points across all applicable dimensions
(scores.earned == scores.max, and scores.max > 0).

Outputs:
    calibration.csv   — bin-level data, ready to plot
    calibration.md    — markdown summary with per-model ECE + key findings

Usage:
    python -m eval.calibration [--details eval_outputs/details.json] [--out DIR]
                               [--bins 5]              # number of confidence bins
                               [--overconf-threshold 0.8]   # "high confidence"
                               [--underconf-threshold 0.4]  # "low confidence"
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def _was_correct(score: dict) -> bool:
    return bool(score and score.get("max", 0) > 0 and score["earned"] == score["max"])


def _bin_index(conf: float, n_bins: int) -> int:
    if conf >= 1.0:
        return n_bins - 1
    if conf < 0.0:
        return 0
    return int(conf * n_bins)


def compute_calibration(details: list[dict], n_bins: int = 5) -> dict:
    """Return per-model bin tables and aggregate calibration metrics."""
    by_model_bins: dict[str, list[dict]] = defaultdict(
        lambda: [{"n": 0, "n_correct": 0, "sum_conf": 0.0} for _ in range(n_bins)]
    )
    by_model_total: dict[str, dict] = defaultdict(
        lambda: {"n_with_conf": 0, "n_correct": 0, "n_overconf": 0, "n_underconf": 0}
    )
    by_model_task: dict[tuple, dict] = defaultdict(
        lambda: {"n": 0, "sum_conf": 0.0, "n_correct": 0}
    )

    for d in details:
        conf = d.get("predicted_confidence")
        if conf is None:
            continue  # skip rows without confidence (older runs)
        if d.get("error"):
            # Failed call — confidence undefined; skip.
            continue

        model = d["model"]
        task = d.get("task_type", "?")
        correct = _was_correct(d.get("scores", {}))

        bi = _bin_index(conf, n_bins)
        b = by_model_bins[model][bi]
        b["n"] += 1
        b["sum_conf"] += conf
        if correct:
            b["n_correct"] += 1

        m = by_model_total[model]
        m["n_with_conf"] += 1
        if correct:
            m["n_correct"] += 1

        # Per-task breakdown
        t = by_model_task[(model, task)]
        t["n"] += 1
        t["sum_conf"] += conf
        if correct:
            t["n_correct"] += 1

    # ----- Derived metrics -----
    report: dict = {"n_bins": n_bins, "models": {}, "per_task": {}}

    for model, bins in by_model_bins.items():
        m_tot = by_model_total[model]
        n_total = m_tot["n_with_conf"]
        if n_total == 0:
            continue

        # ECE = sum over bins of |conf_bin_mean - acc_bin_mean| * (bin_n / total_n)
        ece = 0.0
        bin_rows = []
        for i, b in enumerate(bins):
            if b["n"] == 0:
                bin_rows.append({"bin": i, "n": 0, "mean_conf": None, "accuracy": None})
                continue
            mean_conf = b["sum_conf"] / b["n"]
            acc = b["n_correct"] / b["n"]
            ece += abs(mean_conf - acc) * (b["n"] / n_total)
            bin_rows.append({
                "bin": i,
                "range_low":  i / n_bins,
                "range_high": (i + 1) / n_bins,
                "n": b["n"],
                "mean_conf": round(mean_conf, 4),
                "accuracy":  round(acc, 4),
            })

        report["models"][model] = {
            "n_with_confidence": n_total,
            "overall_accuracy": round(m_tot["n_correct"] / n_total, 4),
            "ece": round(ece, 4),
            "bins": bin_rows,
        }

    # Per-task ECE-lite (just mean conf vs accuracy)
    for (model, task), t in by_model_task.items():
        if t["n"] == 0:
            continue
        mc = t["sum_conf"] / t["n"]
        ac = t["n_correct"] / t["n"]
        report["per_task"][f"{model}::{task}"] = {
            "model": model,
            "task_type": task,
            "n": t["n"],
            "mean_confidence": round(mc, 4),
            "accuracy": round(ac, 4),
            "gap": round(mc - ac, 4),  # positive = overconfident, negative = under
        }

    return report


# ---------- Writers ----------

def write_csv(report: dict, path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "bin", "range_low", "range_high",
                    "n", "mean_confidence", "accuracy"])
        for model, m in sorted(report["models"].items()):
            for b in m["bins"]:
                if b["n"] == 0:
                    continue
                w.writerow([model, b["bin"], b["range_low"], b["range_high"],
                            b["n"], b["mean_conf"], b["accuracy"]])


def write_markdown(report: dict, path: Path) -> None:
    lines = ["# Confidence Calibration", ""]

    if not report["models"]:
        lines.append("⚠ No confidence data in details.json yet.")
        lines.append("")
        lines.append("Run `python -m eval.run_eval` first — the prompt now asks for "
                     "a `confidence` field. Older runs will be missing it.")
        path.write_text("\n".join(lines))
        return

    # Overall calibration table
    lines.append("## Overall calibration (lower ECE = better)")
    lines.append("")
    lines.append("| Model | n | Accuracy | ECE | Verdict |")
    lines.append("|-------|--:|---------:|----:|---------|")
    for model, m in sorted(report["models"].items()):
        ece = m["ece"]
        # Thresholds match the headline-finding logic below: well < 0.10,
        # noisy < 0.15, miscalibrated >= 0.15.
        verdict = "well-calibrated" if ece < 0.10 else ("noisy" if ece < 0.15 else "miscalibrated")
        lines.append(
            f"| {model} | {m['n_with_confidence']} | {m['overall_accuracy']*100:.1f}% | {ece:.3f} | {verdict} |"
        )
    lines.append("")

    # Calibration curve per model
    lines.append("## Calibration curve (per bin: mean confidence → actual accuracy)")
    lines.append("")
    for model, m in sorted(report["models"].items()):
        lines.append(f"### {model}")
        lines.append("")
        lines.append("| Bin range | n | Mean confidence | Actual accuracy | Gap |")
        lines.append("|-----------|--:|----------------:|----------------:|----:|")
        for b in m["bins"]:
            if b["n"] == 0:
                continue
            gap = b["mean_conf"] - b["accuracy"]
            lines.append(
                f"| [{b['range_low']:.2f}, {b['range_high']:.2f}) | {b['n']} | "
                f"{b['mean_conf']:.3f} | {b['accuracy']:.3f} | {gap:+.3f} |"
            )
        lines.append("")

    # Per-task breakdown — surface the worst miscalibrations
    lines.append("## Per-task calibration gaps")
    lines.append("(positive gap = overconfident, negative = underconfident)")
    lines.append("")
    lines.append("| Model | Task | n | Mean conf | Accuracy | Gap |")
    lines.append("|-------|------|--:|----------:|---------:|----:|")
    rows = sorted(report["per_task"].values(),
                  key=lambda r: (-abs(r["gap"]), r["model"], r["task_type"]))
    for r in rows[:20]:
        lines.append(
            f"| {r['model']} | {r['task_type']} | {r['n']} | "
            f"{r['mean_confidence']:.3f} | {r['accuracy']:.3f} | {r['gap']:+.3f} |"
        )
    lines.append("")

    # Headline findings
    lines.append("## Headline findings")
    findings: list[str] = []
    for model, m in sorted(report["models"].items()):
        if m["ece"] > 0.15:
            findings.append(
                f"- **{model}** is miscalibrated (ECE={m['ece']:.3f}) — "
                f"confidence and accuracy diverge across bins."
            )
    # Find worst per-task gap
    if rows:
        worst = rows[0]
        if abs(worst["gap"]) > 0.15:
            dir_word = "overconfident" if worst["gap"] > 0 else "underconfident"
            findings.append(
                f"- **{worst['model']}** is most {dir_word} on **{worst['task_type']}** "
                f"(gap = {worst['gap']:+.3f}, n={worst['n']})."
            )
    if not findings:
        findings.append("- All models are reasonably well-calibrated (ECE < 0.15).")
    lines.extend(findings)
    lines.append("")

    path.write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser(description="Confidence-calibration analysis.")
    ap.add_argument("--details", type=Path, default=Path("eval_outputs/details.json"))
    ap.add_argument("--out", type=Path, default=Path("eval_outputs"))
    ap.add_argument("--bins", type=int, default=5)
    args = ap.parse_args()

    if not args.details.exists():
        raise SystemExit(f"details file not found: {args.details}")

    details = json.loads(args.details.read_text())
    report = compute_calibration(details, n_bins=args.bins)

    args.out.mkdir(parents=True, exist_ok=True)
    csv_path = args.out / "calibration.csv"
    md_path  = args.out / "calibration.md"
    json_path = args.out / "calibration.json"

    write_csv(report, csv_path)
    write_markdown(report, md_path)
    json_path.write_text(json.dumps(report, indent=2))

    print(f"Wrote: {csv_path}")
    print(f"Wrote: {md_path}")
    print(f"Wrote: {json_path}")

    # Console summary
    print()
    print("=" * 60)
    print("CONFIDENCE CALIBRATION")
    print("=" * 60)
    if not report["models"]:
        print("⚠ No confidence data found in details.json.")
        print("  Re-run `python -m eval.run_eval` (the prompt now asks for confidence).")
        return 0
    for model, m in sorted(report["models"].items()):
        print(f"\n{model}:  n={m['n_with_confidence']}  "
              f"accuracy={m['overall_accuracy']*100:.1f}%  "
              f"ECE={m['ece']:.3f}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
