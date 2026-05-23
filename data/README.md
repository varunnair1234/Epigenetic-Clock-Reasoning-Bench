# Data

Real GEO cohort data used to calibrate per-CpG drift rates for the MESA cell simulation. All values are sourced from published datasets — nothing synthetic.

## Layout

```
data/
├── GSE40279/         Hannum 2013, 656 blood samples, ages 19–101
│   ├── metadata.csv          (656 samples × 9 fields)
│   ├── horvath_betas.csv     (164 samples × 353 Horvath CpGs)
│   └── drift_rates.csv       (353 CpGs, regression of β ~ age)
│
├── GSE51057/         NOWAC women, 329 samples, ages 34.7–70.4
│   ├── metadata.csv          (329 samples × 5 fields)
│   ├── horvath_cpgs.csv      (41 CpGs × 329 samples)  ⚠ misnamed
│   └── drift_rates.csv       (105,972 CpGs)
│
└── GSE55763/         Lehne 2015, 2,711 blood samples
    └── metadata.csv          (2,711 samples × 5 fields)
```

Each per-dataset folder uses `sample_id` (GSM accession) as the primary key. Files within a folder join on that column.

## Shared schema (metadata.csv)

| Column | Type | Notes |
|--------|------|-------|
| `sample_id` | string | GEO sample accession (`GSM...`) — primary key |
| `age` | float | Chronological age in years |
| `sex` | string | `F` or `M` |
| `tissue` | string | Tissue type (may be empty for GSE51057, see below) |

Dataset-specific extra columns are allowed; common columns must use these names.

## Per-dataset details

### GSE40279 — Hannum 2013

- **Source:** [GSE40279](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE40279), PMID 23177740
- **Cohort:** 656 whole-blood samples, ages 19–101, mean 64; F=338 / M=318; sites UCSD/Utah/Boston/USC
- **Metadata extras:** `subject_id`, `array_barcode`, `ethnicity`, `source`, `plate`
- **Beta data:** 164-sample chunk (subjects 1001–1166, files `GSE40279_average_beta_GSM989827-GSM989990`)
- **Coverage of canonical Horvath 353:** 353/353 ✓
- **Drift rates:** computed locally from this 164-sample slice (real regression). Median r² = 0.015, max r² = 0.357 across 353 CpGs. Slopes are noisy but real — bigger sample pool (e.g. GSE55763 betas) would tighten them.
- **Status:** ✅ Clean, ready for use in simulation calibration.

### GSE51057 — NOWAC women (added by teammate)

- **Source:** [GSE51057](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE51057) — Norwegian Women and Cancer Study, buccal/blood/saliva methylation
- **Cohort:** 329 of 845 possible samples downloaded; ages 34.7–70.4, mean 53; **all female**; tissue not labeled
- **Metadata extras:** `disease_status` (column present but 100% empty across all rows)
- **Known issues:**
  - 🚨 **`horvath_cpgs.csv` is misnamed.** Only 10 of its 41 CpGs are in the canonical Horvath 353 set; the other 31 are unrelated probes. The intended naming is unclear — recommend renaming to `cpg_subset.csv` or filtering to actual Horvath sites.
  - ⚠ `tissue` column is empty across all 329 rows. This dataset's value lies in being multi-tissue — without the tissue label, it can't support the multi-tissue discordance task (Task Type C). Needs to be backfilled from GEO series matrix metadata.
  - ⚠ Single-sex (F only) cohort. Fine to use, but downstream code must not assume sex balance.
- **Drift rates:** 105,972 CpGs from the local regression. Median r² = 0.032, max 0.94. Plausible per-CpG slopes (range ±0.20 per year). Of canonical Horvath 353, 145 CpGs are present in this file (208 missing because the supplementary data is filtered).
- **Status:** ⚠ Usable for general drift exploration; **not recommended** as the primary calibration source given narrow age range, single sex, and unknown tissue.

### GSE55763 — Lehne 2015 (added by teammate)

- **Source:** [GSE55763](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE55763), PMID 25888029
- **Cohort:** 2,711 peripheral-blood samples, ages 23.7–75.0, mean 51.0; M=1,840 / F=871 (~2:1 skew)
- **Files present:** metadata only
- **Files needed:** beta matrix subset to Horvath CpGs (same processing as GSE40279). With 2,711 samples this would produce the tightest drift-rate estimates of any of the three datasets.
- **Known issues:**
  - ⚠ `disease_status` column 100% empty — can drop unless it will be backfilled.
- **Status:** Metadata clean; waiting on beta values.

## Drift-rate computation

The drift rate for a CpG is the slope of `β ~ age` across samples, fit by ordinary least squares.

```
drift_per_year  = OLS slope of beta on age (years)
drift_per_month = drift_per_year / 12      # for MESA monthly timesteps
r_squared       = goodness of fit; low values mean weak per-CpG age signal
```

Per-CpG r² values being low is normal — the Horvath clock works because it weights 353 individually-weak CpGs into an ensemble. Don't filter CpGs by r²; use all of them.

## Recommended next steps

1. **Backfill `tissue` in `GSE51057/metadata.csv`** from the GEO series matrix `!Sample_characteristics_ch1` lines.
2. **Rename `GSE51057/horvath_cpgs.csv`** to `cpg_subset.csv` (or filter to the 10 canonical Horvath CpGs and keep the name).
3. **Drop `disease_status`** column from both `GSE51057/metadata.csv` and `GSE55763/metadata.csv` (always empty).
4. **Add `GSE55763/horvath_betas.csv`** by downloading and stream-subsetting the GSE55763 beta matrix — biggest unlock for calibration quality.
5. **Decide on a primary drift_rates source** — recommend pooling GSE40279 + GSE55763 once the latter's betas are in.
