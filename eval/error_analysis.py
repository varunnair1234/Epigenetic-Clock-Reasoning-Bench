"""Categorize every wrong model answer into named failure modes.

Reads ``eval_outputs/details.json`` (produced by run_eval.py) and classifies
each (scenario, model) where the model lost any points into one or more of:

    clock_confusion           : predicted accelerated_aging=True only because GrimAge
                                was elevated (model conflated mortality risk with
                                cumulative aging acceleration)
    direction_over            : predicted accelerated when truth is normal/decelerated
    direction_under           : predicted normal/decelerated when truth is accelerated
    missed_discordance        : truth says clocks disagree, model said they agreed
    hallucinated_discordance  : truth says clocks agreed, model said they disagreed
    confounder_blind          : Type D task — model declared real aging on what is
                                a known confounder/artifact
    hallucinated_intervention : claimed intervention worked when truth says it didn't
    missed_intervention       : said intervention didn't work when truth says it did
    other                     : score < max but doesn't fit a labelled bucket

Outputs (under --out, default eval_outputs/):
    error_breakdown.csv   — per (model, error_type) counts + % of model's failures
    error_breakdown.md    — human-readable markdown table
    error_details.json    — per (scenario, model) categorization for debugging

Usage:
    python -m eval.error_analysis [--details eval_outputs/details.json] [--out DIR]
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


def _norm_task(t: str) -> str:
    return (t or "").strip()[0].upper() if t else ""


def categorize_failure(predicted: dict, ground_truth: dict, task_type: str) -> list[str]:
    """Return one or more failure-mode labels for a wrong answer.

    Returns an empty list when the answer matches ground truth (no failure).
    """
    cats: list[str] = []
    p = predicted or {}
    g = ground_truth or {}
    task = _norm_task(task_type)

    p_accel = p.get("accelerated_aging")
    g_accel = g.get("accelerated_aging")
    p_disc  = p.get("clock_discordance")
    g_disc  = g.get("clock_discordance")
    p_int   = p.get("intervention_effective")
    g_int   = g.get("intervention_effective")
    g_grim  = g.get("high_mortality_risk")

    # Direction error (overall aging-status mismatch)
    if p_accel is not None and g_accel is not None and p_accel != g_accel:
        if g_accel is False and p_accel is True:
            cats.append("direction_over")
        elif g_accel is True and p_accel is False:
            cats.append("direction_under")

    # Clock confusion: declared acceleration only because GrimAge was high.
    # Heuristic — Horvath isn't actually accelerated, but the model said it was;
    # at the same time GrimAge IS elevated. The model conflated the clocks.
    if (p_accel is True and g_accel is False and g_grim is True):
        cats.append("clock_confusion")

    # Discordance label mismatch (both directions)
    if g_disc is True and p_disc is not True:
        cats.append("missed_discordance")
    elif g_disc is False and p_disc is True:
        cats.append("hallucinated_discordance")

    # Confounder blindness — Type D specific
    if task == "D" and p_accel is True and g_accel is False:
        cats.append("confounder_blind")

    # Intervention misjudgment
    if p_int is True and (g_int is False or g_int is None):
        cats.append("hallucinated_intervention")
    elif p_int is False and g_int is True:
        cats.append("missed_intervention")

    return cats


def analyze(details: list[dict]) -> dict:
    """Walk per-(scenario, model) details and produce a structured report."""
    per_model_failures: dict[str, list[dict]] = defaultdict(list)
    per_model_categories: dict[str, Counter] = defaultdict(Counter)
    per_model_total: Counter = Counter()
    per_model_wrong: Counter = Counter()

    for d in details:
        model = d["model"]
        per_model_total[model] += 1

        sc = d.get("scores", {})
        was_correct = (sc.get("earned", 0) == sc.get("max", 0)) and sc.get("max", 0) > 0
        if d.get("error") or not d.get("parse_ok"):
            # API error or parse failure — count as a separate bucket so we
            # don't false-positive other categories with empty predictions.
            per_model_wrong[model] += 1
            per_model_categories[model]["error_or_parse_fail"] += 1
            per_model_failures[model].append({
                "scenario_id": d["scenario_id"],
                "task_type": d["task_type"],
                "categories": ["error_or_parse_fail"],
                "error": d.get("error"),
            })
            continue

        if was_correct:
            continue

        per_model_wrong[model] += 1
        cats = categorize_failure(
            d.get("predicted_labels") or {},
            d.get("ground_truth") or {},
            d.get("task_type", ""),
        )
        if not cats:
            cats = ["other"]
        for c in cats:
            per_model_categories[model][c] += 1
        per_model_failures[model].append({
            "scenario_id": d["scenario_id"],
            "task_type": d["task_type"],
            "categories": cats,
            "predicted_labels": d.get("predicted_labels"),
            "ground_truth": d.get("ground_truth"),
        })

    return {
        "per_model_total":      dict(per_model_total),
        "per_model_wrong":      dict(per_model_wrong),
        "per_model_categories": {m: dict(c) for m, c in per_model_categories.items()},
        "per_model_failures":   dict(per_model_failures),
    }


# ---------- Writers ----------

CATEGORY_ORDER = [
    "clock_confusion",
    "direction_over",
    "direction_under",
    "missed_discordance",
    "hallucinated_discordance",
    "confounder_blind",
    "hallucinated_intervention",
    "missed_intervention",
    "error_or_parse_fail",
    "other",
]


def write_csv(report: dict, path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "category", "count", "pct_of_wrong"])
        for model in sorted(report["per_model_categories"]):
            cats = report["per_model_categories"][model]
            n_wrong = report["per_model_wrong"].get(model, 0)
            for c in CATEGORY_ORDER:
                cnt = cats.get(c, 0)
                pct = (cnt / n_wrong * 100) if n_wrong else 0
                if cnt > 0:
                    w.writerow([model, c, cnt, f"{pct:.1f}"])


def write_markdown(report: dict, path: Path) -> None:
    lines = ["# Error Analysis", ""]
    for model in sorted(report["per_model_categories"]):
        total = report["per_model_total"].get(model, 0)
        wrong = report["per_model_wrong"].get(model, 0)
        acc = (1 - wrong / total) * 100 if total else 0
        cats = report["per_model_categories"][model]
        lines.append(f"## {model}")
        lines.append(f"- Scenarios attempted: {total}")
        lines.append(f"- Wrong / incomplete:  {wrong}  ({100 - acc:.1f}%)")
        lines.append("")
        lines.append("| Failure mode | Count | % of failures |")
        lines.append("|--------------|------:|--------------:|")
        for c in CATEGORY_ORDER:
            cnt = cats.get(c, 0)
            if cnt == 0:
                continue
            pct = (cnt / wrong * 100) if wrong else 0
            lines.append(f"| {c} | {cnt} | {pct:.1f}% |")
        lines.append("")
    path.write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser(description="Categorize model failures by mode.")
    ap.add_argument("--details", type=Path, default=Path("eval_outputs/details.json"))
    ap.add_argument("--out", type=Path, default=Path("eval_outputs"))
    args = ap.parse_args()

    if not args.details.exists():
        raise SystemExit(f"details file not found: {args.details}")

    details = json.loads(args.details.read_text())
    report = analyze(details)

    args.out.mkdir(parents=True, exist_ok=True)
    csv_path = args.out / "error_breakdown.csv"
    md_path  = args.out / "error_breakdown.md"
    json_path = args.out / "error_details.json"

    write_csv(report, csv_path)
    write_markdown(report, md_path)
    json_path.write_text(json.dumps(report["per_model_failures"], indent=2))

    print(f"Wrote: {csv_path}")
    print(f"Wrote: {md_path}")
    print(f"Wrote: {json_path}")

    # Console summary
    print()
    print("=" * 60)
    print("ERROR BREAKDOWN")
    print("=" * 60)
    for model in sorted(report["per_model_categories"]):
        total = report["per_model_total"][model]
        wrong = report["per_model_wrong"][model]
        print(f"\n{model}  ({wrong}/{total} wrong, {100*wrong/total:.1f}%)")
        for c in CATEGORY_ORDER:
            cnt = report["per_model_categories"][model].get(c, 0)
            if cnt:
                pct = cnt / wrong * 100
                print(f"  {c:<28}  {cnt:>3}  ({pct:>5.1f}%)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
