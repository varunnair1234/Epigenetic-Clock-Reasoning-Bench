# Data

Real-cohort methylation data used to calibrate per-CpG drift rates for the MESA cell simulation. All values are sourced from published GEO data — nothing synthetic.

## Source

- **GEO accession:** [GSE40279](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE40279)
- **Paper:** Hannum et al. 2013, *Genome-wide Methylation Profiles Reveal Quantitative Views of Human Aging Rates* (PMID: 23177740)
- **Cohort:** 656 whole-blood samples, ages 19–101, profiled on Illumina Infinium HumanMethylation450 BeadChip
- **Fetched:** 2026-05-23

## Files

### `sample_metadata.csv` (52 KB, 656 rows)

Per-sample metadata for the full GSE40279 cohort.

| Column | Description |
|--------|-------------|
| `subject_id` | Subject ID used in the Hannum supplementary files (e.g. `1001`) |
| `gsm_accession` | GEO sample accession (e.g. `GSM989827`) |
| `array_barcode` | Illumina chip barcode + position (e.g. `5815284001_R01C01`) |
| `age` | Chronological age in years (range 19–101) |
| `gender` | `F` or `M` |
| `ethnicity` | Self-reported ethnicity |
| `tissue` | Always `whole blood` for this dataset |
| `source` | Collection site (`UCSD` or `JHU`) |
| `plate` | Plate batch number |

Parsed from the GEO series matrix metadata header (no beta data downloaded).

### `horvath_betas.csv` (583 KB, 164 rows × 354 columns)

Beta values at the 353 Horvath (2013) clock CpGs, for the **first 164-sample chunk** of the GSE40279 supplementary beta matrix (subjects 1001–1166, files `GSE40279_average_beta_GSM989827-GSM989990.txt.gz`).

| Column | Description |
|--------|-------------|
| `subject_id` | Joins to `sample_metadata.csv` |
| `cg00075967`, `cg00091693`, … | One column per Horvath CpG, beta value in [0, 1] |

All 353 Horvath CpGs were located in the GEO matrix — no missing sites in this chunk. Beta values are the GEO-provided averaged betas (no recomputation from raw IDATs).

## Coverage notes

- `sample_metadata.csv` covers all 656 samples in the cohort
- `horvath_betas.csv` covers only the first 164 (one supplementary chunk) — sufficient for fitting per-CpG age slopes for simulation calibration
- To extend to the full 656 samples, download the remaining three chunks from GEO and re-run the subset step

## Provenance

The Horvath 353 CpG list was fetched from the [biolearn](https://github.com/bio-learn/biolearn) project (`biolearn/data/Horvath1.csv`), which mirrors the original Horvath 2013 supplementary coefficients. Age annotations and sample metadata were pulled from the GEO series matrix metadata header (no large download required).

## Intended use

- Per-CpG linear regression of `beta ~ age` → empirical drift rate per year
- Divide by 12 to get monthly drift rates for the MESA cell agents
- Pick 5 representative CpGs from this set for the agent methylation state
