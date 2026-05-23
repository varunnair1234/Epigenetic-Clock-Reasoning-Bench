"""CLI entry point: run the eval harness over a benchmark.json.

Usage (from repo root):
    python -m eval.run_eval [--benchmark benchmark/benchmark.json]
                            [--out eval_outputs/]
                            [--models claude,gemini,biollm]
                            [--limit N]

Produces in --out:
    leaderboard.csv   — one row per (model, task_type), aggregate scores
    details.json      — full per-(scenario, model) breakdown for debugging
    raw_responses/    — one .txt per (scenario, model) with the model's raw output
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

# Make this runnable as a script even without `-m`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval import clients, scorer  # noqa: E402


def load_env(path: Path) -> None:
    """Manual .env loader (no python-dotenv dependency)."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        # Overwrite if missing or empty; preserve non-empty existing values
        # so CI / shell exports still take precedence.
        if not os.environ.get(k):
            os.environ[k] = v


def build_clients(names: list[str]) -> dict[str, clients.Client]:
    out: dict[str, clients.Client] = {}
    factory = {
        "claude": clients.ClaudeClient,
        "gemini": clients.GeminiClient,
        "biollm": clients.BioLLMClient,
    }
    for n in names:
        if n not in factory:
            raise SystemExit(f"unknown model: {n!r} (known: {list(factory)})")
        out[n] = factory[n]()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the epigenetic-clock benchmark eval harness.")
    ap.add_argument("--benchmark", type=Path, default=Path("benchmark/benchmark.json"))
    ap.add_argument("--out", type=Path, default=Path("eval_outputs"))
    ap.add_argument("--models", default="claude,gemini,biollm",
                    help="Comma-separated model names (default: claude,gemini,biollm)")
    ap.add_argument("--limit", type=int, default=0,
                    help="If > 0, evaluate only the first N scenarios (debug)")
    args = ap.parse_args()

    load_env(Path(".env"))

    if not args.benchmark.exists():
        raise SystemExit(f"benchmark file not found: {args.benchmark}")

    bench = json.loads(args.benchmark.read_text())
    scenarios = bench["scenarios"]
    if args.limit:
        scenarios = scenarios[: args.limit]

    model_names = [m.strip() for m in args.models.split(",") if m.strip()]
    model_clients = build_clients(model_names)

    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "raw_responses").mkdir(exist_ok=True)

    print(f"Benchmark: {args.benchmark} ({len(scenarios)} scenarios)")
    print(f"Models:    {', '.join(model_clients)}")
    print(f"Output:    {out_dir}")
    print()

    details: list[dict] = []
    t_start = time.time()

    for i, scenario in enumerate(scenarios, 1):
        sid = scenario["scenario_id"]
        task = scenario["task_type"]
        prompt = scorer.build_prompt(scenario)

        print(f"[{i:>3}/{len(scenarios)}] {sid}  ({task})")
        for model_name, client in model_clients.items():
            t0 = time.time()
            error = None
            raw = ""
            try:
                raw = client.complete(prompt, max_tokens=600, temperature=0.0)
            except clients.ClientError as e:
                error = str(e)
            dt = time.time() - t0

            # Save raw response
            (out_dir / "raw_responses" / f"{sid}__{model_name}.txt").write_text(
                raw if not error else f"<ERROR: {error}>"
            )

            parsed = scorer.parse_response(raw) if not error else {}
            sc = scorer.score(parsed, scenario["ground_truth"], scenario["scoring_weights"])

            details.append({
                "scenario_id": sid,
                "task_type": task,
                "model": model_name,
                "latency_s": round(dt, 2),
                "error": error,
                "parse_ok": sc["parse_ok"],
                "predicted_labels": parsed.get("labels") if parsed else None,
                "ground_truth_labels": scenario["ground_truth"]["labels"],
                "scores": sc,
            })

            marker = "✗" if error else ("?" if not sc["parse_ok"] else "✓")
            print(f"     {marker} {model_name:>6}  {dt:>5.1f}s  "
                  f"{sc['earned']:>3}/{sc['max']:<3} pts  "
                  f"({sc['pct']:>5.1f}%)" + (f"  ERROR: {error[:80]}" if error else ""))

    elapsed = time.time() - t_start

    # ----- Aggregate to leaderboard -----
    # By model: total earned / total max across all scenarios
    # By (model, task_type): same but grouped
    agg = defaultdict(lambda: {"earned": 0, "max": 0, "n": 0, "errors": 0, "parse_fails": 0})
    for d in details:
        for key in (
            ("ALL", d["model"]),
            (d["task_type"], d["model"]),
        ):
            row = agg[key]
            row["earned"] += d["scores"]["earned"]
            row["max"] += d["scores"]["max"]
            row["n"] += 1
            if d["error"]:
                row["errors"] += 1
            elif not d["parse_ok"]:
                row["parse_fails"] += 1

    leaderboard_path = out_dir / "leaderboard.csv"
    with leaderboard_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["task_type", "model", "n_scenarios", "earned", "max",
                    "pct", "errors", "parse_fails"])
        for (task, model), row in sorted(agg.items()):
            pct = (row["earned"] / row["max"] * 100) if row["max"] else 0
            w.writerow([task, model, row["n"], row["earned"], row["max"],
                        f"{pct:.1f}", row["errors"], row["parse_fails"]])

    (out_dir / "details.json").write_text(json.dumps(details, indent=2))

    # ----- Print summary -----
    print()
    print("=" * 70)
    print(f"LEADERBOARD  (n={len(scenarios)} scenarios, {elapsed:.1f}s total)")
    print("=" * 70)
    print(f"{'task_type':<32} {'model':<8} {'pts':>10}  {'pct':>6}  {'err':>4}  {'?':>3}")
    for (task, model), row in sorted(agg.items()):
        pct = (row["earned"] / row["max"] * 100) if row["max"] else 0
        print(f"{task:<32} {model:<8} {row['earned']:>4}/{row['max']:<4}  "
              f"{pct:>5.1f}%  {row['errors']:>4}  {row['parse_fails']:>3}")
    print("=" * 70)
    print(f"\nWrote: {leaderboard_path}")
    print(f"Wrote: {out_dir / 'details.json'}")
    print(f"Wrote: {out_dir / 'raw_responses'}/ (per-call .txt files)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
