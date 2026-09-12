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
