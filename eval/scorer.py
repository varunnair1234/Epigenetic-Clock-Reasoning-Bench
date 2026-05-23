"""Prompt construction, response parsing, and scoring against ground truth.

The harness sends a single JSON-mode prompt to each model. The model is
expected to return a JSON object with ``labels``, ``primary_signal_clock``,
and ``explanation`` fields. Even if the model wraps the JSON in prose or a
markdown code fence, the parser extracts it.

Scoring per dimension (matching ``benchmark/benchmark.json`` schema):

- ``aging_status`` (25): label ``accelerated_aging`` matches ground truth
- ``clock_discordance`` (20): label ``clock_discordance`` matches
- ``intervention_efficacy`` (20): label ``intervention_effective`` matches
- ``tissue_specificity`` (20): >=50% of ``expected_keywords`` appear in explanation
- ``confounder_awareness`` (15): >=50% of ``expected_keywords`` appear in explanation

A dimension contributes ``scoring_weights[dim]`` points if "correct" else 0.
Max possible per scenario = sum of non-zero weights for that scenario's task.
"""

from __future__ import annotations

import json
import re
from typing import Any


# ---------- Prompt construction ----------

PROMPT_TEMPLATE = """You are an expert evaluator of epigenetic aging clocks (Horvath, GrimAge, DunedinPACE).

Patient profile:
{patient_profile}

Clock values:
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
  "explanation": "<2-3 sentence rationale>"
}}

Use these binary-label rules:
  - accelerated_aging:   Horvath_age > chronological_age + 5
  - fast_pacer:          DunedinPACE > 1.1
  - high_mortality_risk: GrimAge > chronological_age + 7
  - clock_discordance:   |Horvath_accel - GrimAge_accel| > 5
  - intervention_effective: only if post-intervention clock values are provided AND
    DunedinPACE dropped meaningfully (>= 0.05) or sen-fraction dropped >= 20%.
    Use null when no intervention is described.
"""


def build_prompt(scenario: dict) -> str:
    return PROMPT_TEMPLATE.format(
        patient_profile=json.dumps(scenario["patient_profile"], indent=2),
        clock_values=json.dumps(scenario["clock_values"], indent=2),
        question=scenario["question"],
    )


# ---------- Response parsing ----------

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_BARE_JSON = re.compile(r"(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})", re.DOTALL)


def parse_response(text: str) -> dict[str, Any]:
    """Best-effort JSON extraction. Returns {} if nothing usable found."""
    if not text:
        return {}
    # 1) Try fenced ```json ... ``` block (most common)
    m = _JSON_FENCE.search(text)
    candidates = [m.group(1)] if m else []
    # 2) Fall back to bare braces
    if not candidates:
        candidates = [m.group(1) for m in _BARE_JSON.finditer(text)]
    # 3) Try each candidate, prefer the longest parseable one
    parsed_options = []
    for c in candidates:
        try:
            parsed_options.append(json.loads(c))
        except json.JSONDecodeError:
            continue
    if not parsed_options:
        return {}
    # Prefer one with a 'labels' key
    for p in parsed_options:
        if isinstance(p, dict) and "labels" in p:
            return p
    return parsed_options[0] if isinstance(parsed_options[0], dict) else {}


# ---------- Scoring ----------

LABEL_KEYS = (
    "accelerated_aging",
    "fast_pacer",
    "high_mortality_risk",
    "clock_discordance",
    "intervention_effective",
)


def _label_matches(predicted: Any, expected: Any) -> bool:
    """Strict equality with None == None handling."""
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
    scoring_weights: dict,
    *,
    keyword_threshold: float = 0.5,
) -> dict:
    """Return per-dimension breakdown + scenario total.

    Each dimension is all-or-nothing: full points if correct, 0 if wrong.
    Dimensions with weight 0 contribute 0/0 (not applicable).
    """
    pred_labels = (response or {}).get("labels") or {}
    explanation = (response or {}).get("explanation") or ""
    gt_labels = ground_truth.get("labels", {})
    expected_keywords = ground_truth.get("expected_keywords", [])

    kw_ratio = _keyword_hit_ratio(explanation, expected_keywords)
    kw_passes = kw_ratio >= keyword_threshold

    def dim(dim_name: str, correct: bool) -> dict:
        max_pts = int(scoring_weights.get(dim_name, 0))
        return {"max": max_pts, "earned": max_pts if (correct and max_pts > 0) else 0}

    dims = {
        "aging_status":           dim("aging_status",
                                       _label_matches(pred_labels.get("accelerated_aging"),
                                                      gt_labels.get("accelerated_aging"))),
        "clock_discordance":      dim("clock_discordance",
                                       _label_matches(pred_labels.get("clock_discordance"),
                                                      gt_labels.get("clock_discordance"))),
        "intervention_efficacy":  dim("intervention_efficacy",
                                       _label_matches(pred_labels.get("intervention_effective"),
                                                      gt_labels.get("intervention_effective"))),
        "tissue_specificity":     dim("tissue_specificity", kw_passes),
        "confounder_awareness":   dim("confounder_awareness", kw_passes),
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
        "parse_ok": bool(pred_labels),  # quick proxy: did we extract anything usable
    }
