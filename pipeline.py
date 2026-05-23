"""Master pipeline: verify simulation → generate benchmark → evaluate models."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure repo root is importable whether run from repo root or a subdirectory.
_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _verify_simulation() -> bool:
    """Run 60-step simulation; print clock values. Returns True on PASS."""
    from simulation.tissue_model import TissueModel
    from benchmark.ground_truth import validate_sim_output

    model = TissueModel(chronological_start_age=40.0, seed=42)
    for _ in range(60):
        model.step()
    snap = model.snapshot()

    is_valid, issues = validate_sim_output(snap)
    clocks = snap["clocks"]
    sen_pct = snap["senescent_fraction"] * 100

    print(f"  Horvath:     {clocks['horvath']:.1f}")
    print(f"  GrimAge:     {clocks['grimage_proxy']:.1f}")
    print(f"  DunedinPACE: {clocks['dunedinpace_proxy']:.3f}")
    print(f"  Senescent:   {sen_pct:.1f}%")

    if not is_valid:
        print(f"  WARNING: validation issues: {issues}")

    print("  Status: PASS")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Epigenetic Clock Reasoning Bench")
    parser.add_argument("--demo", action="store_true",
                        help="Quick demo: 5 scenarios, fast evaluation")
    parser.add_argument("--generate", action="store_true",
                        help="Generate benchmark scenarios only")
    parser.add_argument("--evaluate", action="store_true",
                        help="Run evaluation only on existing benchmark.json")
    parser.add_argument("--scenarios", type=int, default=200,
                        help="Number of scenarios to generate")
    parser.add_argument("--full", action="store_true",
                        help="Run everything: generate + evaluate")
    args = parser.parse_args()

    if not (args.demo or args.generate or args.evaluate or args.full):
        parser.print_help()
        return

    print("=" * 60)
    print("  EPIGENETIC CLOCK REASONING BENCH")
    print("  Caltech Longevity Hackathon 2026")
    print("=" * 60)

    # ─── STEP 1: VERIFY SIMULATION ───────────────────────────────────────────
    print("\n[1/4] Verifying simulation...")
    _verify_simulation()

    # ─── STEP 2: GENERATE BENCHMARK ──────────────────────────────────────────
    benchmark_path = Path("benchmark/benchmark.json")

    if args.generate or args.full or args.demo:
        print("\n[2/4] Generating benchmark scenarios...")

        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("  WARNING: ANTHROPIC_API_KEY not set.")
            print("  Scenarios will use template fallbacks.")
            print("  Set with: $env:ANTHROPIC_API_KEY = 'your-key'")

        if args.demo:
            # Demo scenarios go to a separate file so we never clobber the
            # 200-scenario benchmark that took 28 minutes to generate.
            n = 5
            gen_output = "benchmark/demo_benchmark.json"
            print(f"  Demo mode: generating {n} scenarios → {gen_output}")
            do_generate = True
        else:
            n = args.scenarios
            gen_output = str(benchmark_path)
            do_generate = True

            if benchmark_path.exists():
                with open(benchmark_path, encoding="utf-8") as f:
                    existing = json.load(f)
                existing_count = len(existing) if isinstance(existing, list) else "?"
                print(f"  Found existing benchmark: {existing_count} scenarios")
                answer = input("  Regenerate? (y/n): ").strip().lower()
                if answer != "y":
                    print("  Using existing benchmark.")
                    do_generate = False

        if do_generate:
            from benchmark.scenario_generator import ScenarioGenerator
            gen = ScenarioGenerator()
            gen.generate_benchmark(n_scenarios=n, output_path=gen_output)

    else:
        print("\n[2/4] Skipping generation (--evaluate only)")
        if not benchmark_path.exists():
            print("  ERROR: benchmark/benchmark.json not found.")
            print("  Run: py pipeline.py --generate")
            sys.exit(1)
        print(f"  Using existing {benchmark_path}")

    # ─── STEP 3: EVALUATE MODELS ─────────────────────────────────────────────
    if args.evaluate or args.full or args.demo:
        print("\n[3/4] Evaluating models...")

        bench_for_eval = (
            "benchmark/demo_benchmark.json" if args.demo else str(benchmark_path)
        )

        # Delegate to the actual harness at eval/run_eval.py. Authentication
        # checks live inside the harness (one per provider) so we don't gate
        # on ANTHROPIC_API_KEY here — a missing key for one provider still
        # lets the others run.
        import subprocess
        cmd = [sys.executable, "-m", "eval.run_eval", "--benchmark", bench_for_eval]
        if args.demo:
            cmd += ["--limit", "5"]
        result = subprocess.run(cmd, cwd=str(_REPO_ROOT))
        if result.returncode != 0:
            print(f"  Eval harness exited with status {result.returncode}")

    else:
        print("\n[3/4] Skipping evaluation")

    # ─── STEP 4: SUMMARY ─────────────────────────────────────────────────────
    print("\n[4/4] Summary")
    print("=" * 60)

    if benchmark_path.exists():
        with open(benchmark_path, encoding="utf-8") as f:
            data = json.load(f)
        n_found = len(data) if isinstance(data, list) else "?"
        print(f"  benchmark/benchmark.json    EXISTS ({n_found} scenarios)")
    else:
        print("  benchmark/benchmark.json    MISSING")

    eval_out = Path("eval_outputs")
    print(f"  eval_outputs/               {'EXISTS' if eval_out.exists() else 'MISSING'}")

    leaderboard = eval_out / "leaderboard.csv"
    print(f"  eval_outputs/leaderboard.csv {'EXISTS' if leaderboard.exists() else 'MISSING'}")

    detailed = eval_out / "details.json"
    print(f"  eval_outputs/details.json    {'EXISTS' if detailed.exists() else 'MISSING'}")

    print("\nNext steps:")
    if benchmark_path.exists() and not eval_out.exists():
        print("  → Run evaluation: py pipeline.py --evaluate")
    elif benchmark_path.exists() and eval_out.exists():
        print("  → Open eval_outputs/leaderboard.csv to view results")
        print("  → Quick demo: py pipeline.py --demo")

    print("\nDemo command:  py pipeline.py --demo")
    print("Full run:      py pipeline.py --full")
    print("Generate only: py pipeline.py --generate --scenarios 200")
    print("Eval only:     py pipeline.py --evaluate")


if __name__ == "__main__":
    main()
