# Pre-registration: selection rules and analysis plan

**Status:** committed before any Price Paid data was downloaded, and before any
catchment cut-off figure was collected. The commit date on this file is the
evidence. Every number below is mirrored in `line54/config.py`; if the two ever
disagree, this document wins and the discrepancy is a bug.

Changes after this commit are allowed, but only by appending a dated entry to
`DEVIATIONS.md` that says what changed, why, and whether prices had been looked
at by then. Any analysis not described here is labelled *exploratory* in the
writeup.

---

## 1. Question and estimand

**Question.** What is the price effect of being inside a secondary school's
admissions catchment, measured at the catchment boundary?

**Estimand.** The discontinuity in expected log transaction price at the
boundary of a school's *practical catchment*: the circle whose radius is the
median last distance offered, taken across the admissions rounds in the study
window.

This is an **intent-to-treat** effect, the price of *advertised eligibility*.
It is not the effect of getting a place. A house just inside the line can still
miss out, because the cut-off moves each year and siblings and looked-after
children get priority first. The design is sharp in eligibility and fuzzy in
admission. The writeup states this, and makes no claim about school quality or
about effects on children.

## 2. Study window and geography

| Item | Rule |
|---|---|
| Sales | Date of transfer from 2015-01-01 to 2025-12-31 inclusive |
| Admissions rounds | Entry in September 2015 to September 2025 |
| Schools | Located in a London local authority (E09000001 to E09000033) |
| Sales | Any location, including outside Greater London, if it falls within a selected boundary's bandwidth |

Late-registered 2025 sales may still be missing from the files. That gap
varies only with time, and year-quarter fixed effects absorb it.

## 3. School inclusion criteria

A school enters the study only if it meets **all** of C1–C5. Criteria are
checked in order, and the screening table records the first one each school
fails.

**C1. Phase and type.** The school is a mainstream, state-funded secondary or
all-through school: community, foundation, voluntary controlled, academy or
free school. Special, independent, UTC, studio and alternative-provision
schools are out. It must be open for the whole window, counting a
predecessor URN across an academy conversion: opened on or before
2014-09-01 and not closed before 2025-12-31.

**C2. Assignment rule.** Within its general places, the school admits by
**straight-line distance** from home to school once the standard priority
groups are used up. Those groups are looked-after and previously looked-after
children, siblings, medical or social need, and children of staff. Up to 10%
aptitude places are allowed and recorded. The school is **excluded** if any of
the following apply in any admissions year used:

- it is selective, or GIAS lists it as selective
- it has faith-based oversubscription criteria, whatever GIAS says
- it uses banding (fair banding, ability bands)
- it gives feeder-school or partner-school priority
- it allocates by random ballot
- it measures distance by walking route
- it measures distance from a nodal point rather than the school

A school whose policy is a published **priority admission area polygon** can
still qualify through Route 1 (see section 4).

Evidence for C2 is the admissions policy or council booklet, with URL and
year, recorded in `catchments/provenance.csv`.

**C3. Quality gradient.** On 2020-01-01, the window midpoint, the school's
overall effectiveness grade is strictly better than the median grade of the
three nearest other mainstream, non-selective, state-funded secondary schools.
Distance is straight-line from the school's GIAS coordinate. Grades are
Outstanding = 1, Good = 2, Requires Improvement = 3, Inadequate = 4 (lower is
better). The grade in force is defined in section 6.

**C4. Transactions.** There are at least **150** qualifying sales with
postcode centroids within **400 m** of the boundary on *each* side, over the
whole window. This is a count of locations only. The screening code does not
read the price column, and that is enforced in code, not by good intentions.

**C5. Stability and size.**
- At least **3** admissions rounds in the window have a published
  national-offer-day last distance offered.
- The coefficient of variation of those figures is **≤ 0.25**.
- The median radius is **≥ 400 m**, the main bandwidth, so the inside of the
  boundary always spans the full main bandwidth.
- The school's site (GIAS coordinate) did not move during the window.

**Fallback ladder, fixed now.** If fewer than **10** schools meet all
criteria, relax one step at a time and stop as soon as 10 pass:

1. C5 coefficient of variation ≤ 0.35
2. C4 minimum 100 sales per side

The writeup reports which step was used. There is no upper cap: every school
that passes is included. Ten solid boundaries beat twenty-five shaky ones.

## 4. Boundary construction

Every school-year boundary is recorded with its route, source URL, admissions
year and cut-off. Routes, in order of preference:

1. **Published polygon.** A priority admission area published as GIS or
   digitisable map.
2. **Reconstructed circle.** A circle of the published last distance offered
   around the school's GIAS coordinate. Use the national offer day figure, not
   post-waiting-list figures, because that is the figure published
   consistently.
3. **Manual digitisation.** A published map traced in QGIS.

For Route 2, the study boundary is the circle with the **median** radius across
available years. The year-matched radius is a robustness check (R7).

All geometry is in **EPSG:27700**. Code that receives geographic coordinates
raises an error rather than computing distances in degrees.

Every boundary is inspected over a basemap before selection is locked.

## 5. Sample construction

In order, with the count of rows dropped logged at each step:

1. Price Paid rows with PPD category **A**, record status not **D**, property
   type in {D, S, T, F}. Type O is dropped as not a standard residential
   dwelling.
2. Transfer date inside the window.
3. Price ≥ £10,000. Below that it is a data error or not a market sale. No
   upper trim; the log outcome handles skew.
4. Postcode normalised (uppercase, single internal space) and joined to ONSPD,
   **including terminated postcodes**. Rows with no grid reference (ONSPD
   `osgrdind` = 9) are dropped. The join failure rate is reported.
5. Signed distance *d* in metres. Positive inside, negative outside. For
   Route 2, *d* = radius − distance from postcode centroid to school
   coordinate.
6. **Contaminated outside.** A sale outside boundary A that lies inside another
   selected school's catchment is not ineligible, so the pair (sale, A) is
   dropped.
7. **Nearest boundary.** Each sale is assigned to at most one boundary: the
   remaining one with the smallest |*d*|.
8. Kept if |*d*| < 750 m, the widest bandwidth in the sensitivity grid.

The result is written to `data/processed/rdd_sample.parquet` with a SHA-256
hash. Every estimate records the hash of the sample it used.

## 6. Ofsted grade in force

The grade in force at date *t* is the overall effectiveness from the most
recent graded inspection whose **publication date** ≤ *t*. Publication date is
used rather than inspection date because that is when buyers could know the
grade.

- Ungraded inspections leave the grade unchanged.
- After an academy conversion, the predecessor URN's grade carries over until
  the new URN's first graded inspection.
- Inspections from September 2024 carry no overall effectiveness grade, and
  report-card inspections from 10 November 2025 carry none either. Neither
  updates the grade. The last single-word judgement stays in force, and the
  writeup names this as an approximation.

## 7. Estimation

**Main specification**, estimated on |*d*| < *h* with triangular kernel
weights max(0, 1 − |*d*|/*h*):

```
log(price) = a + t*inside + b1*d + b2*(d*inside)
           + FE(property_type) + FE(year_quarter) + FE(boundary) + e
```

- **Main bandwidth *h* = 400 m**, fixed now, not chosen from the data.
- **Inference.** Standard errors clustered by boundary. The t distribution uses
  G − 1 degrees of freedom. With 10–25 clusters, conventional cluster-robust
  inference is unreliable, so a **wild cluster restricted bootstrap** p-value
  (Webb weights, 9,999 draws) is reported next to it.
- **Reported.** *t* with 95% CI; percentage premium exp(*t*) − 1; pounds
  premium evaluated at the median price of **outside** sales within *h*, the
  counterfactual side.
- **Bandwidth sensitivity.** Same specification at *h* = 100, 150, …, 750 m.
  The plot is published whatever it shows.
- **Per-boundary estimates.** Same specification without boundary fixed
  effects, with standard errors clustered by postcode unit, shown as a forest
  plot.

## 8. Robustness: all run, all reported

| ID | Test | Expected if the design is valid |
|---|---|---|
| R1 | Placebo cut-offs at *d* = +250, +500 (inside-only data) and −250, −500 (outside-only data), recentred running variable, main bandwidth truncated at the real boundary | ≈ 0 |
| R2 | Covariate balance: same specification with outcome = flat, detached, leasehold, new build, LSOA IMD 2019 score, distance to nearest rail/Underground/DLR/Overground/tram station. Property-type fixed effects are dropped when property type is the outcome | ≈ 0 |
| R3 | McCrary (2008) density test on *d*: (a) sales, (b) postcode units. Bin width 10 m, bandwidth 400 m | No discontinuity. The density rising smoothly outward is expected from circle geometry and is not a failure |
| R4 | Donut: drop \|*d*\| < 25 m and < 50 m | Estimate stable |
| R5 | Timing: for any selected school whose grade in force changed by ≥ 1 grade with ≥ 2 years of sales both before and after, estimate before and after the publication date | Premium moves in the direction of the grade change. If no school qualifies, report "not run: no qualifying change" |
| R6 | Measurement error: share of the sample within 25 m and 50 m of the boundary, and the direction of bias from postcode-centroid measurement | Attenuation toward zero, so the estimate is a conservative floor |
| R7 | Year-matched radius: the most recent offer-day cut-off published before the sale date | Same sign, similar size |
| R8 | Drop sales within the main bandwidth of two or more boundaries | Estimate stable |
| R9 | Boundary-specific slopes | Estimate stable |
| R10 | Add tenure and new-build fixed effects | Estimate stable |
| R11 | Local quadratic instead of local linear | Estimate stable |
| R12 | Leave one boundary out | No single boundary drives the result |

Floor area and building age from EPC data are **not** used for balance: the
EPC register needs an account, and every other source here is anonymous
public download.

## 9. Blinding

Estimation scripts refuse to run until `catchments/selection_lock.json`
exists. That file records the SHA-256 of `catchments/provenance.csv`, and a
person writes it only after verifying every row of the provenance table
against its source. If the provenance file changes afterwards, estimation
refuses to run until the lock is re-issued, and the change goes into
`DEVIATIONS.md`.

## 10. Reporting commitments

- A precisely estimated null is reported as a finding. There is no
  specification search for a non-zero number.
- The headline is whatever the main specification produces. The project title
  is a placeholder until then.
- Every robustness row is reported, including any that fail.
