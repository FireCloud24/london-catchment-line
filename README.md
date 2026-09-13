# What a London catchment line is worth

What a secondary-school catchment boundary is worth, measured where the map
changes and the neighbourhood does not. This is a regression discontinuity
study of London house prices at school admission boundaries.

**Result.** Across twelve oversubscribed London secondaries, a home just
inside the admissions line sold for an estimated **+1.8%** more than one just
outside (**+£8,821** at the median outside price of £480,000). The 95%
interval runs from −3.5% to +7.4% (−£16,656 to +£35,698), so the premium
cannot be told apart from zero. Large premiums are ruled out; a small one is
possible but not established. Read the full writeup in `writeup/index.html`.

The working title was "The £54,000 Line". The number was left blank until the
pre-registered specification produced it.

## The design in one paragraph

Regressing price on school quality mostly measures where wealthy families
already live. This project compares sales a few metres either side of a
catchment boundary. Those houses share streets, transport and neighbours;
only admission eligibility jumps. The boundaries aren't published anywhere,
so they are reconstructed from each council's "last distance offered" figures,
only for schools that admit on straight-line distance. For those schools the
assignment rule is mechanical and the discontinuity is sharp.

## Status

| Phase | State |
|---|---|
| Pre-registration (`PREREGISTRATION.md`) | Committed before any data was downloaded |
| A. Ingestion: Price Paid, ONSPD, GIAS, Ofsted, NaPTAN | Done: 1.31M geolocated sales near London |
| C1–C3 screen from GIAS/Ofsted | Done: 88 candidate schools |
| B. Catchment research | Done: 12 schools, 80 cut-off figures re-checked against sources |
| Selection lock | Committed 2026-09-13, before any price was read (`f123bcc`) |
| C–E. Sample, estimation, robustness, figures, writeup | Done: 114,635 sales in sample; all 12 robustness checks reported |

## Reproduce

Python 3.12, from the repository root:

```
pip install -r requirements.txt
python -m unittest discover -s tests -t .     # 45 tests, synthetic data only
python -m pipeline.run                        # downloads (~2.4 GB) through to the writeup
```

`pipeline.run` stops at phase 06 until `catchments/selection_lock.json`
exists. That is deliberate (pre-registration section 9). After verifying:

```
python -m pipeline.lock_selection --verified-by "Your Name"
python -m pipeline.run --from 06
```

Every phase writes an artefact to disk. Nothing depends on notebook state.

| Phase | Module | Writes |
|---|---|---|
| 01 | `p01_download` | `data/raw/*`, `MANIFEST.json` with SHA-256 per file |
| 02 | `p02_ingest_sales` | `sales.parquet`, price-free `sale_locations.parquet`, ingest step table |
| 03 | `p03_ingest_schools` | schools, Ofsted grade history, C1–C3 screen |
| 04 | `p04_build_catchments` | `catchments.gpkg` (EPSG:27700), boundary and provenance tables |
| 05 | `p05_screen` | C2/C4/C5 selection table, `boundary_check_map.html` |
| 06 | `p06_assemble_sample` | `rdd_sample.parquet` + hash, full sample construction table |
| 07 | `p07_estimate` | `outputs/results/main.json`, bandwidth sweep, per-boundary estimates |
| 08 | `p08_robustness` | `outputs/results/robustness.csv` (R1–R12) |
| 09 | `p09_figures` | headline chart, bandwidth plot, forest plot, density histogram (PNG) |
| 10 | `p10_writeup` | `writeup/index.html`, charts as inline SVG generated from the stored results |

## Repository map

```
PREREGISTRATION.md   selection rules and analysis plan, committed first
DEVIATIONS.md        every change to the plan, dated, with whether prices had been seen
VERIFY.md            how the catchment research was checked before locking
writeup/             the deliverable: one page, one number, full appendix
catchments/          provenance.csv (school-year cut-offs), research_log.csv (all 88 candidates)
line54/              library: geometry, RD estimator, density test, grades, robustness, figures
pipeline/            one script per phase
tests/               unittest suite; synthetic data with a planted discontinuity
outputs/             tables, figures, results (data/ is not committed)
```

## Things this project is careful about

- **Coordinate system.** Distances are computed in British National Grid
  metres. Code that receives degrees raises an error.
- **Blinding.** School screening reads a file with no price column, and
  estimation refuses to run until a person locks the verified boundary set.
- **Few clusters.** 10–25 boundaries is too few for conventional
  cluster-robust p-values. A wild cluster restricted bootstrap (Webb weights)
  is reported alongside them.
- **Ofsted.** The grade in force follows a school across academy
  conversions. It uses publication dates, and stays in force through the
  September 2024 end of single-word judgements and the November 2025 report
  cards.
- **Source errors.** Two Ofsted records, one duplicated council table and one
  wrong search summary were caught and are documented in code or `VERIFY.md`.

## Data and licences

- Contains HM Land Registry data © Crown copyright and database right 2021.
  This data is licensed under the Open Government Licence v3.0.
- ONS Postcode Directory (August 2026): Source: Office for National Statistics
  licensed under the Open Government Licence v3.0. Contains OS data © Crown
  copyright and database right. Contains Royal Mail data © Royal Mail copyright
  and database right.
- Get Information About Schools, Ofsted management information and NaPTAN:
  Open Government Licence v3.0.
- Council admissions documents are cited row by row in
  `catchments/provenance.csv`.
