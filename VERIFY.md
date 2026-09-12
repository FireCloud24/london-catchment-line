# Verifying the catchment research

Everything in `catchments/provenance.csv` is a **draft** transcribed from
council and school documents on 2026-09-12. Nothing is used for estimation
until you verify it and run `pipeline.lock_selection`. That lock is what lets
the writeup say the boundary set was fixed before any price was examined.

## Where things stand

- 88 London secondaries passed C1 (phase, type, open) and C3 (quality gradient)
  from GIAS and Ofsted data (`outputs/tables/school_screen_c1_c3.csv`).
- Each one has an outcome in `catchments/research_log.csv`.
- On draft figures, **10 schools pass C2, C4 and C5** (`outputs/tables/school_screen.csv`):

| School | Borough | Years | Median radius | CV |
|---|---|---|---|---|
| Alexandra Park School | Haringey | 2022-25 | 816 m | 0.06 |
| Whitmore High School | Harrow | 2023-25 | 1,196 m | 0.05 |
| Walthamstow School for Girls | Waltham Forest | 2022-24 | 1,199 m | 0.05 |
| Vyners School | Hillingdon | 2021-23 | 1,662 m | 0.08 |
| Thomas Tallis School | Greenwich | 2022, 23, 25 | 1,870 m | 0.10 |
| Coombe Girls' School | Kingston | 2021-25 | 1,952 m | 0.23 |
| Harris Academy Rainham | Havering | 2020-25 | 2,557 m | 0.12 |
| Rutlish School (boys) | Merton | 2019-24 | 2,550 m | 0.06 |
| Ricards Lodge High School (girls) | Merton | 2019-24 | 2,902 m | 0.06 |
| Tolworth Girls' School | Kingston | 2021-25 | 2,931 m | 0.16 |

- Two more would pass once their admissions policy is read (C2 pending):
  Hall Mead School (Havering, 8 years) and Queensmead School (Hillingdon, 3 years).
- Every one of these has hundreds to thousands of sales within 400 m on each
  side, so C4 is not binding.

## How to verify a row

For each row of `provenance.csv` belonging to a school you intend to keep:

1. Open `source_url`. Find the school and year.
2. Check that `cutoff_as_published` matches the document exactly, and that the
   year is the **entry** year. Several councils label files by application
   cycle: Harrow's `How_places_were_allocated_22_23` holds September 2023 entry.
3. Check the figure is the **national offer day** cut-off, not the end-of-August
   figure. `notes` says where the basis is uncertain.
4. Open `policy_url`. Confirm the oversubscription criteria contain nothing on
   the C2 exclusion list (banding, faith criteria, feeder schools, ballot,
   walking distance, nodal point away from the school). If you can, check a
   policy from an earlier year in the window as well.
5. Set `status` to `verified`, and fill `verified_by` and `verified_on`. If a
   figure is wrong, correct it and say so in `notes`. If a row can't be
   trusted, set `status` to `rejected`.

Then open `outputs/boundary_check_map.html` in a browser and look at every
circle. Is the school's dot actually on the school? Does a circle cross a
reservoir, a railway yard or a park that would leave one side empty?

## Specific things I flagged

- **Merton 2025 figures rejected.** Ricards Lodge and Rutlish show 2025
  offer-day distances identical to 2024 to two decimal places (2597.37 and
  2391.40). That is almost certainly a copy error in Merton's table. Both are
  `rejected`; check the 2026 update of the same document.
- **Coombe Girls'** measures distance to two named entrances (Clarence Avenue
  and Darley Drive), not one point. Its CV of 0.23 is close to the 0.25 limit
  and the cut-off has risen since 2023.
- **Thomas Tallis** figures come from Greenwich's booklets and are not
  explicitly labelled as offer-day. Entry 2024 is missing: the 2025/26 booklet
  was not located.
- **Hillingdon** tables are not dated to offer day. The 2021 file was
  published in October 2021.
- **Harris Academy Rainham**: the 2025 policy has no banding, but other
  Harris academies band. Check an older Rainham policy.
- **A search-tool summary was wrong once** (Kingston: it reported 2.628/3.236 km
  for years that are 1.915/1.952 km in the PDF). Every figure here was read
  from the source document text, not from summaries. That is also why it's
  worth checking them.

## Decisions (made 2026-09-12, before any price was related to a boundary)

All four are recorded in `DEVIATIONS.md`.

1. **Opposite-sex schools do not contaminate each other.**
   `SEX_AWARE_CONTAMINATION = True`.
2. **Any undersubscribed year in the window excludes a school.** This makes
   the **missing years** of the 10 passing schools worth checking: if, say,
   Thomas Tallis was undersubscribed in 2024 or Whitmore in 2021, that school
   fails C5.
3. **Priority-area hybrids are excluded.** So are schools with separate
   distance quotas by area (Waldegrave, Cheam High).
4. **The minimum stays at three years.** Heathland, Lampton, Cranford and
   Ark Academy stay out unless a third year is found.

Still open, and not blocking:

5. **Entrance coordinates.** Several policies measure to a named gate or
   entrance rather than the GIAS point. The main specification uses GIAS
   points, and the error attenuates toward zero. A robustness run using
   entrance coordinates you digitise is possible later. Otherwise it goes in
   the writeup as a stated limitation.

## Sites I did not read (bot protection or 403, not bypassed)

- **Barnet** (Ashmole, Hendon, Archer, Compton): allocation tables for 2019,
  2023, 2024 and 2025. URLs are in `research_log.csv`.
- **Enfield** (Enfield County Girls, Highlands, Ark John Keats): 2024 and 2025
  allocation information. URLs are in `research_log.csv`.
- **Bromley** (Bullers Wood, Chislehurst Girls, Hayes, Harris Girls): no
  published cut-offs found.
- **Barking & Dagenham** (Robert Clack, Sydney Russell): the booklet is an
  encrypted PDF.

The Internet Archive was offline on 2026-09-12. When it is back, older
council files (2015-2020) could add years for several schools.

## After verifying

```
python -m pipeline.p04_build_catchments --statuses verified
python -m pipeline.p05_screen --statuses verified
python -m pipeline.lock_selection --verified-by "Your Name"
git add catchments outputs/tables && git commit -m "Lock verified boundary set"
```
