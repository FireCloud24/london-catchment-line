"""Every researcher choice in one place, mirroring PREREGISTRATION.md.

If a number here disagrees with the pre-registration, the document wins and
this file has a bug. Nothing in the pipeline should hard-code any of these.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"
CATCHMENTS = ROOT / "catchments"
FIGURES = ROOT / "outputs" / "figures"
TABLES = ROOT / "outputs" / "tables"

# British National Grid. Distances in EPSG:4326 are degrees, and a degree of
# longitude in London is ~0.62 of a degree of latitude.
CRS = "EPSG:27700"

# --- Section 2: window and geography --------------------------------------
SALES_START = date(2015, 1, 1)
SALES_END = date(2025, 12, 31)
ENTRY_YEARS = range(2015, 2026)  # September entry 2015..2025 inclusive
LONDON_LA_CODES = frozenset(f"E0900{n:04d}" for n in range(1, 34))

# --- Section 3: inclusion criteria ----------------------------------------
OPEN_BY = date(2014, 9, 1)
NOT_CLOSED_BEFORE = date(2025, 12, 31)
MAX_APTITUDE_SHARE = 0.10
GRADE_REFERENCE_DATE = date(2020, 1, 1)
N_COMPARATOR_SCHOOLS = 3
MIN_SALES_PER_SIDE = 150
SCREEN_BANDWIDTH_M = 400.0
MIN_CUTOFF_YEARS = 3
MAX_CUTOFF_CV = 0.25
MIN_MEDIAN_RADIUS_M = 400.0
MIN_BOUNDARIES = 10
# Applied one step at a time, only if fewer than MIN_BOUNDARIES pass.
FALLBACK_LADDER = (
    {"MAX_CUTOFF_CV": 0.35},
    {"MAX_CUTOFF_CV": 0.35, "MIN_SALES_PER_SIDE": 100},
)

# --- Section 5: sample construction ---------------------------------------
PPD_CATEGORY = "A"
DROP_RECORD_STATUS = "D"
PROPERTY_TYPES = ("D", "S", "T", "F")
MIN_PRICE = 10_000
ONSPD_NO_GRID_REF = 9
MAX_BANDWIDTH_M = 750.0

# --- Section 7: estimation ------------------------------------------------
MAIN_BANDWIDTH_M = 400.0
BANDWIDTH_GRID_M = tuple(float(h) for h in range(100, 751, 50))
BOOTSTRAP_DRAWS = 9_999
BOOTSTRAP_SEED = 20150101

# --- Section 8: robustness ------------------------------------------------
PLACEBO_CUTOFFS_M = (-500.0, -250.0, 250.0, 500.0)
DENSITY_BIN_M = 10.0
DENSITY_BANDWIDTH_M = 400.0
DONUT_RADII_M = (25.0, 50.0)
TIMING_MIN_YEARS_EACH_SIDE = 2
MEASUREMENT_ERROR_BANDS_M = (25.0, 50.0)

# --- Section 9: blinding --------------------------------------------------
PROVENANCE_FILE = CATCHMENTS / "provenance.csv"
SELECTION_LOCK = CATCHMENTS / "selection_lock.json"
