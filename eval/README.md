# eval/

Eval harness for the Epigenetic Clock Reasoning Bench. Reads `benchmark/benchmark.json`, sends every scenario to Claude / Gemini / BioLLM, scores responses against ground truth, and writes `eval_outputs/leaderboard.csv`.

## Quick start

```bash
# 1. Paste real keys into .env (gitignored)
# 2. Verify keys work:
python scripts/test_api_keys.py

# 3. Run the harness:
python -m eval.run_eval
```

## CLI options

```
python -m eval.run_eval [--benchmark PATH]   # default: benchmark/benchmark.json
                        [--out DIR]          # default: eval_outputs/
                        [--models LIST]      # default: claude,gemini,biollm
                        [--limit N]          # only evaluate first N scenarios (debug)
```

## Outputs (under `--out`)

| File | Content |
|------|---------|
| `leaderboard.csv` | One row per `(task_type, model)`, with earned/max/pct and error counts. Row `task_type=ALL` is the model-level total. |
| `details.json` | Per-`(scenario, model)` breakdown: predicted labels, ground truth labels, per-dimension points, latency, errors. |
| `raw_responses/SMOKE-A1__claude.txt` | One file per call with the model's verbatim text response. |

## Architecture

```
benchmark.json  ──►  run_eval.py  ──►  leaderboard.csv
                         │
        ┌────────────────┼────────────────┐
        │                │                │
     clients.py      scorer.py        scorer.py
   (model adapters) (build_prompt)  (parse + score)
        │                │                │
    Claude API      JSON template    label match
    Gemini API      with rules       + keyword hits
    BioLLM (HF)                      × scoring_weights
```

### `eval/clients.py`

Three classes (`ClaudeClient`, `GeminiClient`, `BioLLMClient`) implement the same contract:

```python
client.complete(prompt: str, *, max_tokens=800, temperature=0.0) -> str
```

Keys come from environment variables (loaded from `.env` by `run_eval.py`). Failures raise `ClientError` with a safe-to-log message.

### `eval/scorer.py`

- `build_prompt(scenario)` — fills a single template with the patient profile, clock values, question, and the label rules. Asks for a JSON response in a fenced block.
- `parse_response(text)` — robust JSON extraction. Tries ` ```json fenced ` block first, then bare-brace fallback. Returns `{}` if nothing parses (counts as a parse failure).
- `score(response, ground_truth, scoring_weights)` — per-dimension all-or-nothing scoring:
  - `aging_status` (25 pts): does the predicted `accelerated_aging` label match?
  - `clock_discordance` (20 pts): does the predicted `clock_discordance` label match?
  - `intervention_efficacy` (20 pts): does the predicted `intervention_effective` label match?
  - `tissue_specificity` (20 pts): does the explanation contain ≥50% of the scenario's `expected_keywords`?
  - `confounder_awareness` (15 pts): same keyword check.

Scoring weights for unrelated dimensions are 0, so they don't count for that scenario.

## Smoke run result (5 scenarios)

After fixing two ground-truth inconsistencies in the smoke benchmark, the first end-to-end run produced:

```
task_type                        model     pts        pct
ALL                              biollm    150/215    69.8%
ALL                              claude    200/215    93.0%
ALL                              gemini    200/215    93.0%

A_clock_interpretation           biollm     65/90     72.2%
A_clock_interpretation           claude     90/90    100.0%
A_clock_interpretation           gemini     90/90    100.0%

B_intervention_reasoning         biollm     40/40    100.0%
B_intervention_reasoning         claude     40/40    100.0%
B_intervention_reasoning         gemini     40/40    100.0%

C_multi_tissue_discordance       biollm     20/45     44.4%
C_multi_tissue_discordance       claude     45/45    100.0%
C_multi_tissue_discordance       gemini     45/45    100.0%

D_confounders_artifacts          biollm     25/40     62.5%
D_confounders_artifacts          claude     25/40     62.5%
D_confounders_artifacts          gemini     25/40     62.5%
```

Headline: the bio-LLM trails Claude/Gemini by ~23pp on the smoke benchmark, with the gap driven by **Task C — multi-tissue discordance**. All three models reason intervention efficacy (Task B) correctly. Task D scores are tied because every model partially hits the confounder keywords but none clear the 50% threshold cleanly — calibration knob for later.

## Operational notes

- **Gemini's "thinking" tokens** count against `max_tokens`. The client sets `thinkingConfig.thinkingBudget=0` to leave the whole budget for the visible response — without this, Gemini truncates at ~65 chars.
- **BioLLM cold-starts** the first request can take 30–60s while the endpoint warms. Subsequent requests are ~5s. Client timeout is 180s.
- **Keys never log.** Both `run_eval.py` and `scripts/test_api_keys.py` mask values when echoing. `.env` is gitignored.
- **Deterministic by default.** `temperature=0.0` so re-runs against the same benchmark produce identical responses (modulo provider drift).

## Extending

- **Add a new model:** add a `FooClient` class to `clients.py` with `complete()`, register it in the factory in `run_eval.py`. No other code changes.
- **Change scoring rules:** edit `scorer.score()`. Currently all-or-nothing per dimension; partial credit would go here.
- **Scale to full benchmark:** point `--benchmark` at the generator's `benchmark.json` once Stage 2 is built. Same schema, no code changes.
