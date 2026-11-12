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

### 2026-11-12: Commit messages rewritten; recorded commit hashes updated

**Change.** Every commit message in this repository ended with a
`Co-Authored-By` trailer added by an AI coding assistant. On 2026-11-12 the
history was rewritten to remove that line. A commit's hash depends on its
message, so every hash changed. Three recorded hashes were updated by hand to
their rewritten equivalents:

| Where | Old | New |
|---|---|---|
| `README.md`, selection lock row | `f123bcc` | `e02187a` |
| `outputs/results/main.json`, `git_head` | `f123bcc` | `e02187a` |
| `catchments/selection_lock.json`, `git_head_at_lock` | `6cc4cbc` | `3bb7929` |

Nothing else in those files was touched, and no phase of the pipeline was
re-run. File contents, author, commit dates and commit order are unchanged:
the tree at the last rewritten commit (`dcdb800`, "P3: Run the tests on
every push") and at its rewritten equivalent (`93aa617`) is the same object
(`0ab3554`).

This is the second rewrite. The first, on 2026-09-13 before publishing,
changed the author name and email (`2f24764` became `f123bcc`, `0526a65`
became `6cc4cbc`); the commit "Update commit hash references after author
rewrite" records it, and its message still shows the hashes of that time.

Old to new, oldest first:

| Old | New | Commit |
|---|---|---|
| `f78ce5c` | `612bcbd` | Pre-register selection rules and analysis plan |
| `c56ed54` | `546d946` | Add analysis library, download script and synthetic-data tests |
| `5adfab5` | `5339402` | Ingest sales and schools; screen London secondaries on C1-C3 |
| `f89f55a` | `1cb9f20` | Test grade dedupe against the two real Ofsted cases |
| `5ac93aa` | `1ebd8c3` | Draft catchment research and price-blind screen |
| `824657e` | `9b1cfb7` | Build sample assembly, estimation, robustness and figures behind the lock |
| `127c1de` | `572fc1d` | Apply author decisions on contamination, undersubscription and hybrids |
| `6cc4cbc` | `3bb7929` | Fill missing cut-off years from the Internet Archive |
| `f123bcc` | `e02187a` | Lock the verified boundary set (12 schools) before any price is used |
| `ec089fa` | `411c6df` | Run the pre-registered analysis on the locked sample |
| `5c3c2e2` | `8990a6f` | Add the writeup, generated from stored results |
| `cdefa94` | `0bc8fb0` | Update commit hash references after author rewrite |
| `7d1b307` | `c4be90c` | Add MIT licence and serve the writeup with GitHub Pages |
| `648d99f` | `22d24f3` | Fix the writeup's interval labels and sign wrapping |
| `3864aaf` | `870bc17` | P1: Add a skills box to the README |
| `170321e` | `5fbb125` | P2: Show the headline figure in the README |
| `dcdb800` | `93aa617` | P3: Run the tests on every push |

**Why.** The author's decision about how the repository presents authorship.
It has a cost, stated here so a reader can weigh it: the hashes that tie the
selection lock to a point before any price was examined are now ones the author
edited after the fact, twice. The ordering evidence that remains is the
commit dates and the order of the commits, which a rewrite could also have
changed. Anyone holding a clone made before 2026-11-12 can compare.

**Prices examined?** Not applicable. No analysis was run or changed.

### 2026-11-12: Wording: "before any price was examined"

**Change.** The README and the writeup said the boundary set was locked
"before any price was read". They now say "examined". The sentence in the
writeup was edited by hand in `docs/index.html` and in its generator
(`pipeline/p10_writeup.py`); the writeup was not regenerated.

**Why.** Ingestion (phase 02) ran before the lock and applied a mechanical
price floor: sales below GBP 10,000 are dropped as data errors
(`config.MIN_PRICE`). So prices were read by code before the lock. What the
lock guarantees is that no price was looked at or related to a boundary
before the boundary set was fixed. Earlier entries in this file are left as
written.

**Prices examined?** Not applicable. No analysis was run or changed.
