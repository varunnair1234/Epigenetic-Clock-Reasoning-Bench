"""Prompt construction, response parsing, and scoring against ground truth.

Targets the generator's schema (top-level list of scenarios) where each entry has:

    {
      "scenario_id":    int,
      "task_type":      "A" | "B" | "C" | "D",
      "patient_age":    int,
      "patient_context": "<NL clinical vignette>",
      "clock_values":   {<flat dict; structure varies by task type>},
      "question":       "<the question to answer>",
      "ground_truth":   {
        "accelerated_aging": bool, "fast_pacer": bool, "high_mortality_risk": bool,
        "clock_discordance": bool, "high_senescence": bool,
        "intervention_effective": bool|null, "overall_status": string
      },
      ...
    }

The harness asks the model to return a JSON object with ``labels``,
``primary_signal_clock``, and ``explanation``. Scoring weights and keyword
sets are derived from the task_type letter (the generator doesn't emit them).
"""

from __future__ import annotations

import json
import re
from typing import Any


# ---------- Task-type → scoring rubric ----------
#
# (Per benchmark/README.md.) Dimensions not in this map score 0 for that task.

WEIGHTS_BY_TASK: dict[str, dict[str, int]] = {
    "A": {"aging_status": 25, "clock_discordance": 20},
    "B": {"clock_discordance": 20, "intervention_efficacy": 20},
    "C": {"aging_status": 25, "tissue_specificity": 20},
    "D": {"aging_status": 25, "confounder_awareness": 15},
}

# Keywords the explanation should mention for the keyword-based dimensions.
# Used for tissue_specificity (Task C) and confounder_awareness (Task D).
KEYWORDS_BY_TASK: dict[str, list[str]] = {
    "C": ["tissue", "drift", "saliva", "blood", "brain", "buccal",
          "compartment", "tissue-specific", "specific"],
    "D": ["confounder", "medication", "drug", "artifact", "comorbid",
          "inflammatory", "depression", "ssri", "antidepressant",
          "cell composition"],
}

TASK_FULL_NAMES = {
    "A": "A_clock_interpretation",
    "B": "B_intervention_reasoning",
    "C": "C_multi_tissue_discordance",
    "D": "D_confounders_artifacts",
}


def normalize_task_type(t: str) -> str:
    """Accept both 'A' and 'A_clock_interpretation' forms."""
    if not t:
        return ""
    return t.strip()[0].upper()


def task_full_name(t: str) -> str:
    return TASK_FULL_NAMES.get(normalize_task_type(t), t)


def weights_for(task_type: str) -> dict[str, int]:
    return WEIGHTS_BY_TASK.get(normalize_task_type(task_type), {})


def keywords_for(task_type: str) -> list[str]:
    return KEYWORDS_BY_TASK.get(normalize_task_type(task_type), [])


# ---------- Prompt construction ----------

PROMPT_TEMPLATE = """You are an expert evaluator of epigenetic aging clocks (Horvath, GrimAge, DunedinPACE).

Patient context:
{patient_context}

Patient chronological age: {patient_age} years

Clock measurements:
{clock_values}

Question:
{question}

Respond with a single JSON object inside a ```json fenced block, with EXACTLY these fields:
{{
  "labels": {{
    "accelerated_aging":     <true|false>,
    "fast_pacer":            <true|false>,
    "high_mortality_risk":   <true|false>,
    "clock_discordance":     <true|false>,
    "intervention_effective": <true|false|null>
  }},
  "primary_signal_clock": <"horvath"|"grimage"|"dunedinpace"|null>,
  "explanation": "<2-4 sentence rationale>"
}}

Binary-label rules:
  - accelerated_aging:   Horvath > chronological_age + 5
  - fast_pacer:          DunedinPACE > 1.1
  - high_mortality_risk: GrimAge > chronological_age + 7
  - clock_discordance:   |Horvath_acceleration - GrimAge_acceleration| > 5
  - intervention_effective: only when post-intervention values are provided AND
    DunedinPACE dropped >= 0.05 (or senescent fraction dropped >= 20%). Use null
    when no intervention is described.
"""


def build_prompt(scenario: dict) -> str:
    return PROMPT_TEMPLATE.format(
        patient_context=scenario.get("patient_context", "(none provided)"),
        patient_age=scenario.get("patient_age", "?"),
        clock_values=json.dumps(scenario.get("clock_values", {}), indent=2),
        question=scenario.get("question", ""),
    )


# ---------- Response parsing ----------

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_BARE_JSON = re.compile(r"(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})", re.DOTALL)


def parse_response(text: str) -> dict[str, Any]:
    """Best-effort JSON extraction. Returns {} if nothing usable found."""
    if not text:
        return {}
    m = _JSON_FENCE.search(text)
    candidates = [m.group(1)] if m else []
    if not candidates:
        candidates = [m.group(1) for m in _BARE_JSON.finditer(text)]
    parsed = []
    for c in candidates:
        try:
            parsed.append(json.loads(c))
        except json.JSONDecodeError:
            continue
    if not parsed:
        return {}
    for p in parsed:
        if isinstance(p, dict) and "labels" in p:
            return p
    return parsed[0] if isinstance(parsed[0], dict) else {}


# ---------- Scoring ----------

LABEL_KEYS = (
    "accelerated_aging",
    "fast_pacer",
    "high_mortality_risk",
    "clock_discordance",
    "intervention_effective",
)


def _label_matches(predicted: Any, expected: Any) -> bool:
    if expected is None:
        return predicted is None
    return predicted == expected


def _keyword_hit_ratio(explanation: str, keywords: list[str]) -> float:
    if not keywords or not explanation:
        return 0.0
    low = explanation.lower()
    hits = sum(1 for kw in keywords if kw.lower() in low)
    return hits / len(keywords)


def score(
    response: dict,
    ground_truth: dict,
    task_type: str,
    *,
    keyword_threshold: float = 0.3,  # need ≥30% of keywords in explanation
) -> dict:
    """Score a model response against the flat ground-truth schema.

    The new generator schema stores labels directly on ground_truth (not
    nested under a "labels" key) and does not include scoring_weights or
    expected_keywords — both are derived from task_type here.
    """
    pred_labels = (response or {}).get("labels") or {}
    explanation = (response or {}).get("explanation") or ""

    weights = weights_for(task_type)
    keywords = keywords_for(task_type)
    kw_ratio = _keyword_hit_ratio(explanation, keywords)
    kw_passes = kw_ratio >= keyword_threshold

    def dim(dim_name: str, correct: bool) -> dict:
        max_pts = int(weights.get(dim_name, 0))
        return {"max": max_pts, "earned": max_pts if (correct and max_pts > 0) else 0}

    dims = {
        "aging_status":          dim("aging_status",
                                      _label_matches(pred_labels.get("accelerated_aging"),
                                                     ground_truth.get("accelerated_aging"))),
        "clock_discordance":     dim("clock_discordance",
                                      _label_matches(pred_labels.get("clock_discordance"),
                                                     ground_truth.get("clock_discordance"))),
        "intervention_efficacy": dim("intervention_efficacy",
                                      _label_matches(pred_labels.get("intervention_effective"),
                                                     ground_truth.get("intervention_effective"))),
        "tissue_specificity":    dim("tissue_specificity", kw_passes),
        "confounder_awareness":  dim("confounder_awareness", kw_passes),
    }

    earned = sum(d["earned"] for d in dims.values())
    max_pts = sum(d["max"] for d in dims.values())
    return {
        "dims": dims,
        "earned": earned,
        "max": max_pts,
        "pct": (earned / max_pts * 100) if max_pts else 0.0,
        "keyword_ratio": round(kw_ratio, 3),
        "keyword_passed": kw_passes,
        "parse_ok": bool(pred_labels),
    }
