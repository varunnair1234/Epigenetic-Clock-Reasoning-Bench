"""Claude-generated plain-English explainers for each dashboard section.

Pattern: for each section, we (1) gather the actual data the section is
displaying, (2) feed it to Claude with a tight prompt template, (3) cache
the response keyed by (section, hash(data)) so a refresh costs nothing
and a data change re-generates automatically.

Falls back to a static explainer if ANTHROPIC_API_KEY isn't configured.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from eval.clients import ClaudeClient, ClientError  # noqa: E402

EVAL_OUT = _REPO_ROOT / "eval_outputs"
BENCHMARK_JSON = _REPO_ROOT / "benchmark" / "benchmark.json"


# ---------- Data fetchers (one per section) ----------

def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open() as f:
        return list(csv.DictReader(f))


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _data_tissue_simulation() -> dict:
    # We don't fetch a sim trajectory here — the explanation is about the
    # general mechanics of what the visualization shows, not a specific run.
    return {"section": "tissue_simulation"}


def _data_leaderboard() -> dict:
    rows = _read_csv(EVAL_OUT / "leaderboard.csv")
    baselines = _read_csv(EVAL_OUT / "baseline_leaderboard.csv")
    # Keep it compact: just the ALL-task rows
    return {
        "models":    [r for r in rows if r.get("task_type") == "ALL"],
        "per_task":  [r for r in rows if r.get("task_type") != "ALL"],
        "baselines": [r for r in baselines if r.get("task_type") == "ALL"],
    }


def _data_scenario_browser() -> dict:
    bench = _read_json(BENCHMARK_JSON) or []
    if not isinstance(bench, list):
        bench = []
    # Sample a few scenarios + count by task type
    from collections import Counter
    task_counts = Counter(s.get("task_type") for s in bench)
    return {
        "n_total": len(bench),
        "task_counts": dict(task_counts),
        "sample_scenarios": bench[:3],  # show shape
    }


def _data_score_breakdown() -> dict:
    rows = _read_csv(EVAL_OUT / "leaderboard.csv")
    return {"rows": [r for r in rows if r.get("task_type") != "ALL"]}


def _data_error_analysis() -> dict:
    rows = _read_csv(EVAL_OUT / "error_breakdown.csv")
    return {"rows": rows}


def _data_class_distribution() -> dict:
    data = _read_json(EVAL_OUT / "class_distribution.json")
    return data or {}


def _data_per_label_metrics() -> dict:
    rows = _read_csv(EVAL_OUT / "per_label_metrics.csv")
    return {"rows": rows}


# ---------- Prompts (one per section) ----------

_SYSTEM_PREAMBLE = (
    "You are writing a short 'In Plain English' explainer for a dashboard "
    "section in an epigenetic-clock LLM-reasoning benchmark, aimed at a "
    "smart non-biologist reader (think: a hackathon judge or a software "
    "engineer outside biology). Be concrete with the actual numbers from the "
    "data, avoid jargon (or define it inline), and keep it to 3-5 sentences "
    "max. Don't restate the section title. Don't be salesy. Don't use the "
    "word 'leveraging'. Plain prose only — no markdown, no bullet lists.\n"
)

_PROMPTS: dict[str, str] = {
    "tissue_simulation": (
        "Section: Tissue Simulation. The dashboard shows a 30x30 grid where "
        "each square is a virtual cell that ages over ~16 simulated years. "
        "Cells transition through normal -> stressed -> senescent (the cells "
        "that stop dividing but secrete inflammation) -> dead. Three "
        "'epigenetic clocks' (Horvath, GrimAge, DunedinPACE) read out from "
        "the population to estimate biological age, mortality risk, and pace "
        "of aging. Explain what the user is watching and why these clocks "
        "matter."
    ),
    "leaderboard": (
        "Section: Leaderboard. Each row is one AI model answering the same "
        "200 epigenetic-clock reasoning questions. 'Overall' is the total "
        "score; Type A-D are four task categories. The italic 'baseline' rows "
        "are dumb predictors (always_true, always_false, majority_class) that "
        "show the score floor a model has to beat to demonstrate real "
        "reasoning. Explain what the user is looking at, who's winning, and "
        "why the gap between the top model and the best baseline is the "
        "interesting number.\n\nDATA:\n{data}"
    ),
    "scenario_browser": (
        "Section: Scenario Browser. The benchmark contains 200 scenarios "
        "split across four task types: A (interpret clocks), B (evaluate an "
        "intervention), C (compare tissues), D (detect a confounder). Each "
        "scenario has a patient profile + clock values + a ground-truth label. "
        "Explain what this section shows, what kinds of questions are being "
        "asked, and what 'ground truth' means here.\n\nDATA:\n{data}"
    ),
    "score_breakdown": (
        "Section: Score Breakdown. A bar chart of accuracy per model per "
        "task type (A, B, C, D). Each task type tests a different reasoning "
        "skill: A=read clocks, B=evaluate intervention efficacy, C=multi-"
        "tissue discordance, D=spot confounders. Explain to a non-biologist "
        "what these four skills are and what the chart reveals about the "
        "models' relative strengths.\n\nDATA:\n{data}"
    ),
    "error_analysis": (
        "Section: Error Analysis. When models get questions wrong, the "
        "harness categorizes the failure into named modes: clock_confusion "
        "(mixed up which clock means what), direction_over/under (predicted "
        "wrong aging direction), missed_discordance (didn't notice clocks "
        "disagreed), confounder_blind (treated a medication artifact as real "
        "aging), hallucinated_intervention (claimed treatment worked when it "
        "didn't), and a few others. Explain why grouping failures into modes "
        "matters and what the numbers reveal about each model's typical "
        "failure pattern.\n\nDATA:\n{data}"
    ),
    "class_distribution": (
        "Section: Class Distribution. Shows the True/False ratio in the "
        "ground-truth labels for the 200 benchmark scenarios. Severely "
        "imbalanced labels (where one answer is way more common) are a "
        "scoring trap: a dumb model could always predict the common answer "
        "and look smart. Explain to a non-statistician why imbalance "
        "matters and what these specific numbers say about the benchmark "
        "design.\n\nDATA:\n{data}"
    ),
    "per_label_metrics": (
        "Section: Per-Label F1 + Balanced Accuracy. A confusion-matrix-based "
        "view per (model, label). Balanced accuracy treats both classes "
        "equally so models can't game imbalance. F1 = harmonic mean of "
        "precision and recall. TP/FP/TN/FN = the confusion-matrix counts. "
        "Explain the difference between raw accuracy and balanced accuracy "
        "in plain English, and call out one or two specific model-label "
        "cells where the model is clearly reasoning vs. clearly "
        "guessing.\n\nDATA:\n{data}"
    ),
}


_DATA_FETCHERS: dict[str, Callable[[], Any]] = {
    "tissue_simulation":   _data_tissue_simulation,
    "leaderboard":         _data_leaderboard,
    "scenario_browser":    _data_scenario_browser,
    "score_breakdown":     _data_score_breakdown,
    "error_analysis":      _data_error_analysis,
    "class_distribution":  _data_class_distribution,
    "per_label_metrics":   _data_per_label_metrics,
}


_FALLBACK: dict[str, str] = {
    "tissue_simulation": (
        "You're watching a virtual patch of tissue age over 16 simulated years. Each square is a cell; cells start healthy (green), accumulate damage (stressed, yellow), become senescent (orange — they stop working right and damage their neighbors), or die (dark red). The four numbers on the right are different ways scientists measure biological age — they often disagree, and that disagreement is exactly what we test the AIs on."
    ),
    "leaderboard": (
        "Each row is one AI model answering 200 questions about biological aging. The italic baseline rows at the bottom are dumb predictors — if a real model isn't clearly beating them, it isn't reasoning, just pattern-matching. The signal above baseline is the real measure of reasoning."
    ),
    "scenario_browser": (
        "Sample scenarios from the benchmark. Each has a fake patient's profile, their clock values, and a question. The tags are the correct answers the model is expected to identify."
    ),
    "score_breakdown": (
        "Four task types test four different reasoning skills: reading clocks (A), evaluating treatments (B), comparing tissues (C), and spotting confounders like medications (D). A trophy on a bar means that model is the only one that won that category."
    ),
    "error_analysis": (
        "When models get answers wrong, we group the failures into named modes so you can see how a model is wrong, not just that it is. The patterns reveal each model's typical blind spots."
    ),
    "class_distribution": (
        "Shows how often each label is True vs False in the benchmark. Severely imbalanced labels let dumb models look smart by always predicting the common answer — we surface this so the leaderboard numbers can be interpreted honestly."
    ),
    "per_label_metrics": (
        "Per-(model, label) breakdown. Balanced accuracy treats both classes equally so models can't game imbalance. The confusion-matrix counts (TP/FP/TN/FN) show exactly which kinds of mistakes each model makes."
    ),
}


# ---------- Cache ----------

_CACHE: dict[tuple[str, str], dict] = {}


def _data_hash(data: Any) -> str:
    payload = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


# ---------- Public API ----------

def explain(section: str, *, force_refresh: bool = False) -> dict:
    """Return an in-plain-English explanation for ``section``.

    Tries Claude first (cached), falls back to a static string if Claude
    is unavailable or errors out.
    """
    if section not in _PROMPTS:
        return {
            "section": section,
            "text": f"(no explanation configured for section: {section})",
            "source": "missing",
        }

    fetcher = _DATA_FETCHERS[section]
    data = fetcher()
    key = (section, _data_hash(data))

    if not force_refresh and key in _CACHE:
        return {**_CACHE[key], "cached": True}

    # Try Claude
    try:
        client = ClaudeClient()
    except ClientError as e:
        return {
            "section": section,
            "text": _FALLBACK[section],
            "source": "fallback",
            "note": f"Claude unavailable: {e}",
        }

    prompt = _SYSTEM_PREAMBLE + "\n" + _PROMPTS[section].format(
        data=json.dumps(data, indent=2, default=str)[:3500]  # cap context
    )
    try:
        text = client.complete(prompt, max_tokens=300, temperature=0.2).strip()
    except ClientError as e:
        return {
            "section": section,
            "text": _FALLBACK[section],
            "source": "fallback",
            "note": f"Claude call failed: {e}",
        }

    result = {
        "section": section,
        "text": text,
        "source": "claude",
        "model": ClaudeClient.model,
        "data_hash": key[1],
    }
    _CACHE[key] = result
    return {**result, "cached": False}


def clear_cache() -> int:
    n = len(_CACHE)
    _CACHE.clear()
    return n
