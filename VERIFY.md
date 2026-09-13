# Verifying the catchment research

Everything in `catchments/provenance.csv` is a **draft** transcribed from
council and school documents on 2026-09-12 and 2026-09-13. Nothing is used for
estimation until you verify it and run `pipeline.lock_selection`. That lock is
what lets the writeup say the boundary set was fixed before any price was
examined.

## Where things stand

- 88 London secondaries passed C1 (phase, type, open) and C3 (quality gradient)
  from GIAS and Ofsted data (`outputs/tables/school_screen_c1_c3.csv`).
- Each one has an outcome in `catchments/research_log.csv`.
- On draft figures, **12 schools pass C2, C4 and C5**
  (`outputs/tables/school_screen.csv`). There are 99 draft rows to verify.
  Every year listed below reached the distance criterion on offer day, so no
  school was undersubscribed in any year found.

| School | Borough | Years | Median radius | CV |
|---|---|---|---|---|
| Alexandra Park School | Haringey | 2015-25 (11) | 803 m | 0.17 |
| Whitmore High School | Harrow | 2016-25 (10) | 1,234 m | 0.17 |
| Walthamstow School for Girls | Waltham Forest | 2020-25 (6) | 1,235 m | 0.06 |
| Queensmead School | Hillingdon | 2021-25 (5) | 1,552 m | 0.12 |
| Vyners School | Hillingdon | 2021-25 (5) | 1,674 m | 0.06 |
| Thomas Tallis School | Greenwich | 2022-25 (4) | 1,798 m | 0.07 |
| Coombe Girls' School | Kingston | 2021-25 (5) | 1,952 m | 0.23 |
| Hall Mead School | Havering | 2017-25 (9) | 2,411 m | 0.13 |
| Harris Academy Rainham | Havering | 2018-25 (8) | 2,454 m | 0.13 |
| Rutlish School (boys) | Merton | 2019-24 (6) | 2,550 m | 0.06 |
| Ricards Lodge High School (girls) | Merton | 2019-24 (6) | 2,902 m | 0.06 |
| Tolworth Girls' School | Kingston | 2021-25 (5) | 2,931 m | 0.16 |

- Every one of these has hundreds to thousands of sales within 400 m on each
  side, so C4 is not binding.
- Years before those listed were not recoverable. Archived copies of older
  council booklets (Waltham Forest 2019-22, Kingston 2020) are truncated 1 MB
  captures. The pre-registered rules only apply to years that can be seen; the
  writeup should say so.

## Check these first

| School | Year(s) | Why |
|---|---|---|
| Vyners, Queensmead | 2024, 2025 | **Read from an image.** Hillingdon's PDFs are screenshots with no text layer, so every digit was transcribed by eye |
| Hall Mead, Harris Rainham | 2018 | Havering's 2018 PDF extracts as separate column blocks. Values were matched to schools by row order |
| Whitmore | 2016 | The file has no title. The entry year is inferred from the file-name series |
| Thomas Tallis | 2025 | The council spreadsheet (offer day, 1,867 m) disagrees with the 2026/27 booklet (1.97 km). The spreadsheet is used |

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
- **Thomas Tallis** now uses Greenwich's offer-day spreadsheets (2022-2025)
  rather than the booklets. The booklets agree for 2022 and 2023 but not 2025,
  which suggests booklets can print a later, post-waiting-list figure.
- **Hillingdon** tables are not labelled as offer-day. The 2022 and 2024 file
  versions are timestamped on offer day; the 2021 file is dated October 2021;
  the 2023 February and October versions agree.
- **Harris Academy Rainham: decision needed.** In 2017, 91 of its 195 places
  went to "Partner School" applicants, a C2 exclusion. No partner places appear
  from 2018 on, and the 2017 row is `rejected`. Options: exclude the school,
  or keep it and drop 2015-2017 sales for this boundary (a deviation, still
  before prices). The 2025 policy has no banding.
- **Walthamstow School for Girls: corrected.** Its C2 evidence wrongly listed a
  cross-sibling link with Norlington (that belongs to Connaught School for
  Girls) and measurement from the school centre (it is to the designated main
  gate). Neither changes C2.
- **Queensmead and Hall Mead** now pass C2, from archived admissions policies
  (Queensmead 2020-21 and 2022-23; ELAT 2022-23 and 2025-26). Both use looked
  after, sibling, then straight-line distance. Both live sites return 403.
- **A search-tool summary was wrong once** (Kingston: it reported 2.628/3.236 km
  for years that are 1.915/1.952 km in the PDF). Every figure here was read
  from the source document text, not from summaries. That is also why it's
  worth checking them.

## Decisions (made 2026-09-12, before any price was related to a boundary)

All four are recorded in `DEVIATIONS.md`.

1. **Opposite-sex schools do not contaminate each other.**
   `SEX_AWARE_CONTAMINATION = True`.
2. **Any undersubscribed year in the window excludes a school.** On 2026-09-13
   I searched the Internet Archive for the missing years. None of the 12 was
   undersubscribed in any year found.
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

The Internet Archive was back on 2026-09-13 and filled most gaps. Sources
reached through it are cited as `web.archive.org/web/<timestamp>id_/...`
URLs, which serve the file exactly as captured.

## After verifying

```
python -m pipeline.p04_build_catchments --statuses verified
python -m pipeline.p05_screen --statuses verified
python -m pipeline.lock_selection --verified-by "Your Name"
git add catchments outputs/tables && git commit -m "Lock verified boundary set"
```
