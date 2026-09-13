# Deviations from the pre-registration

Append-only. Each entry gives the date, what changed, why, and whether any
price data had been examined when the decision was made.

---

### 2026-09-12: ONSPD column name for grid-reference quality

**Change.** Section 5 step 4 names the ONSPD field `osgrdind`. The August 2026
ONSPD calls the same field `gridind` (value 9 = no grid reference). The code
uses `gridind`. The rule is unchanged.

**Prices examined?** No. Price Paid files were downloaded but not yet read.

### 2026-09-12: IMD balance covariate is the rank, not the score

**Change.** R2 pre-registered "LSOA IMD 2019 score". ONSPD already carries the
IMD 2019 **rank** for every English postcode (`imd20ind`, checked against the
bundled "IMD lookup EN as at 12_19" file, which is keyed on 2011 LSOAs). The
balance test uses that rank and needs no extra download. Rank is a monotone
transform of score, so a discontinuity in one is a discontinuity in the other.
In the rank, 1 is the most deprived LSOA.

**Prices examined?** No.

### 2026-09-12: Opposite-sex schools do not contaminate each other (section 5, step 6)

**Change.** Section 5 step 6 drops a pair (sale, boundary A) when the sale is
outside A but inside any other selected catchment. The rule now applies only
when the other school could be an alternative for the same child. A girls'
school and a boys' school are not alternatives for each other; mixed schools
are alternatives for everyone. Implemented as
`config.SEX_AWARE_CONTAMINATION = True`, via `sample.compatibility`.

**Why.** Ricards Lodge (girls) and Rutlish (boys) in Merton have overlapping
catchments. Under the original rule, a house outside Ricards Lodge's line but
inside Rutlish's would be dropped as "not ineligible", yet a Rutlish place
gives a girl nothing. The original rule would throw away valid comparisons
and would not be more conservative in any meaningful way.

**Prices examined?** No. Phase A1 has read the Price Paid files to filter and
geolocate sales, but no price has been related to any school or boundary. The
selection is not locked, and no estimation phase has run on real data.

### 2026-09-12: Clarifications to C2 and C5 made during catchment research

These make the pre-registered criteria precise for cases the document did not
anticipate. Each was decided by the author after seeing the admissions
documents but before any price was related to a boundary.

1. **C5, undersubscribed years.** If a council reports that every applicant
   was offered a place ("all applicants offered", "N/A", "undersubscribed")
   for any admissions round in the window, the school fails C5. In that year no
   boundary existed, so the line is not a stable treatment. The screen reads
   these years from `years_not_applied` in `catchments/research_log.csv`.
2. **C2, priority-area hybrids.** A school that offers places to everyone
   inside a priority or catchment area first, and then by distance outside it,
   fails C2. Its boundary is neither a published polygon (Route 1) nor a
   distance circle (Route 2). Affects Redbridge (Seven Kings, Loxford,
   Chadwell Heath, Beal), Harris Academy Merton and Kensington Aldridge Academy.
3. **C2, areas with separate distance quotas.** A school that splits places
   into areas, each with its own distance cut-off, fails C2 for the same
   reason. Affects Waldegrave (Area A 85%, Area B 15%) and Cheam High
   (Worcester Park places).
4. **C5, minimum years unchanged.** The minimum of three admissions rounds
   stands. Schools with two years online (Heathland, Lampton, Cranford, Ark
   Academy) stay out unless a third year is found.

**Prices examined?** No, as above.

### 2026-09-13: How the boundary set was verified (section 9)

**Change.** Section 9 says a person writes the lock after verifying every
provenance row against its source. The author approved the selection in chat
("everything is verified") and asked for the project to continue, saying
there was no time to read the source files one by one. So the 80 rows for
the 12 selected schools were **not** individually re-read by the author.
Instead:

1. A script re-read each source document (PDF text, council spreadsheet or web
   page) and confirmed that the recorded figure sits on the school's own row
   *and* belongs to the recorded entry year, from the document title, section
   heading or column position. **73 of 80 rows matched.** The result is in
   `catchments/recheck.csv`.
2. The other 7 were checked by hand:
   - **Four Hillingdon figures** (Vyners and Queensmead, 2024 and 2025) come
     from image-only PDFs. They were re-read from enlarged crops and all match.
   - **Hall Mead and Harris Rainham 2018:** Havering's PDF splits into column
     blocks. Row alignment was confirmed across all 18 schools: every school
     marked "N/A" is one that was undersubscribed or had allocated places, and
     every school with a figure was fully offered. Allocation counts also add
     up to places offered for both schools.
   - **Whitmore 2016:** the file has no title. The entry year is inferred from
     the council's file-name series, whose other three members state their
     years.

`verified_by` in `provenance.csv` and in the lock records this method, not
a claim that the author read every row. The writeup states the same.

**Prices examined?** No. The lock is committed before phase 06 first reads a price.

### 2026-09-13: Harris Academy Rainham boundary starts 1 January 2018

**Change.** In the 2017 admissions round, 91 of Harris Academy Rainham's 195
places went to partner-school applicants, a C2 exclusion. No partner places
appear in 2018-2025. The school stays in the study, but its boundary is
treated as not in force for sales before 2018-01-01
(`config.BOUNDARY_ACTIVE_FROM`). Those sales form no pairs with it and do
not count as contaminating other boundaries. The 2017 cut-off row is `rejected`.

**Why.** C2 excludes such priority "in any admissions year used". From 2018
the rule is a clean distance rule. Dropping the earlier sales keeps eight
clean years without letting a period with a different rule into the sample.
This was the recommended option; the author asked for the project to continue
without choosing.

**Prices examined?** No.
