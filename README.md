# Epigenetic Clock Reasoning Bench

A benchmark suite that tests how well large language models reason about epigenetic aging clocks. Uses agent-based cell simulation (MESA) to generate biologically grounded scenarios with known ground truth, then evaluates LLM responses.

## Why

Most LLMs fail at nuanced epigenetic clock reasoning — they conflate different clocks, ignore tissue-specificity, and miss intervention timing dynamics. No existing benchmark tests multi-clock discordance reasoning, and LongevityBench lacks intervention trajectory tasks. Synthetic simulation lets us produce arbitrarily large datasets with exact ground truth.

## Pipeline

Three stages: **simulate → generate → evaluate**.

1. **Simulation** — MESA cell agents (30×30 grid, 900 cells) age over time. Each agent tracks methylation state (5 representative CpG sites), damage from oxidative stress, telomere length, senescence state, and SASP secretion. One timestep = one month; runs are ~200 steps (~16 years).
2. **Tissue aggregation** — cell-population state is collapsed into tissue-level clock proxies:
   - Bulk methylation → Horvath
   - Senescent fraction + SASP → GrimAge
   - Mean DNA damage + senescent fraction → DunedinPACE
3. **Scenario generation** — each run produces a clinical vignette (patient/tissue profile, pre/post-intervention clock values, NL question, programmatically derived ground-truth labels).
4. **Eval harness** — sends scenarios to each model, parses JSON, scores against ground truth across multiple dimensions.

## Task categories

| Type | Tests |
|------|-------|
| A — Clock Interpretation | What each clock measures and what divergence implies |
| B — Intervention Reasoning | How clocks respond to interventions at different timescales |
| C — Multi-Tissue Discordance | Tissue-specific drift rates and discordance interpretation |
| D — Confounders & Artifacts | Medications, cell-composition shifts, technical artifacts |

## Scoring dimensions

| Dimension | Points |
|-----------|--------|
| Aging status (accelerated / normal / decelerated) | 25 |
| Clock discordance identification & explanation | 20 |
| Intervention efficacy evaluation | 20 |
| Tissue specificity in reasoning | 20 |
| Confounder awareness | 15 |

## Models evaluated

- GPT-4o (OpenAI)
- Claude Sonnet 4 (Anthropic)
- Gemini 1.5 Pro (Google)
- BioMedLM (PubMed-trained)
- MedAlpaca (medical-QA fine-tuned)

The gap between general LLMs and bio-specialized models is the key research finding.

## Data sources

**Open access (hackathon):**
- GEO GSE40279 — Horvath validation cohort, 656 blood samples
- GEO GSE55763 — whole-blood methylation, 2,711 samples
- GEO GSE51057 — multi-tissue Horvath validation, ~50 samples
- `pyaging` built-in example data

**Controlled access (future validation):** MESA (dbGaP phs000209), TwinsUK.

## Stack

- **Simulation:** mesa, numpy, pandas, scipy
- **Methylation/clocks:** pyaging, GEOparse, Biopython, scispaCy
- **LLM eval:** anthropic, openai, transformers, langchain
- **Utilities:** matplotlib/seaborn, tqdm, pydantic, pytest

## Deliverables

1. `benchmark.json` — 500+ scenarios with ground-truth labels
2. Eval harness script — reproducible scoring pipeline
3. `leaderboard.csv` — model comparison across task types
4. LongevityBench-compatible export format

## Status

Project scaffold — no implementation yet.
