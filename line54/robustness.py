"""Section 8 of the pre-registration: every test, run and reported regardless.

Each function takes the stored rdd_sample and returns rows for one table, so
the robustness table in the writeup is a direct dump of `run_all`.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from . import config, density, grades, rdd

BALANCE_OUTCOMES = {
    "is_flat": "share flat",
    "is_detached": "share detached",
    "is_leasehold": "share leasehold",
    "is_new_build": "share new build",
    "imd19_rank": "LSOA IMD 2019 rank (1 = most deprived)",
    "dist_station_m": "distance to nearest rail/Underground/DLR/tram station (m)",
}
PROPERTY_TYPE_OUTCOMES = {"is_flat", "is_detached"}


def _row(test: str, spec: str, result: rdd.RDResult | None, expect: str, note: str = "") -> dict:
    if result is None:
        return {"test": test, "spec": spec, "expectation": expect, "note": note}
    return {
        "test": test, "spec": spec, "expectation": expect, "tau": result.tau, "se": result.se,
        "ci_low": result.ci_low, "ci_high": result.ci_high, "p_value": result.p_value,
        "p_wild_bootstrap": result.p_wild_bootstrap, "n_obs": result.n_obs, "n_clusters": result.n_clusters,
        "bandwidth_m": result.bandwidth_m, "note": note or "; ".join(result.notes),
    }


def _safe(test: str, spec: str, expect: str, fn) -> dict:
    """A test that cannot run is reported as not run, never silently skipped."""
    try:
        return _row(test, spec, fn(), expect)
    except ValueError as e:
        return _row(test, spec, None, expect, note=f"not run: {e}")


def r1_placebo(df: pd.DataFrame, h: float = config.MAIN_BANDWIDTH_M) -> list[dict]:
    rows = []
    for c in config.PLACEBO_CUTOFFS_M:
        side = "inside" if c > 0 else "outside"
        rows.append(_safe("R1 placebo cut-off", f"d = {c:+.0f} m, {side} data only", "~0",
                          lambda c=c, side=side: rdd.fit(df, h, cutoff=c, side=side, label=f"placebo {c:+.0f}")))
    return rows


def r2_balance(df: pd.DataFrame, h: float = config.MAIN_BANDWIDTH_M) -> list[dict]:
    rows = []
    for col, label in BALANCE_OUTCOMES.items():
        if col not in df or df[col].notna().sum() == 0:
            rows.append(_row("R2 covariate balance", label, None, "~0", note=f"not run: {col} not in sample"))
            continue
        fe = tuple(f for f in rdd.MAIN_FE if not (f == "property_type" and col in PROPERTY_TYPE_OUTCOMES))
        rows.append(_safe("R2 covariate balance", label, "~0", lambda col=col, fe=fe: rdd.fit(df, h, outcome=col, fe=fe, label=col)))
    return rows


def r3_density(df: pd.DataFrame) -> list[dict]:
    rows = []
    sales = df["d_signed_m"].to_numpy()
    units = df.drop_duplicates(subset=["boundary_id", "postcode"])["d_signed_m"].to_numpy()
    for spec, d in (("sales", sales), ("postcode units", units)):
        r = density.mccrary(d, config.DENSITY_BIN_M, config.DENSITY_BANDWIDTH_M)
        rows.append({
            "test": "R3 density (McCrary)", "spec": spec, "expectation": "no discontinuity",
            "tau": r.theta, "se": r.se, "ci_low": r.theta - 1.96 * r.se, "ci_high": r.theta + 1.96 * r.se,
            "p_value": r.p_value, "n_obs": r.n, "bandwidth_m": r.bandwidth_m,
            "note": "tau is log(f_inside) - log(f_outside); a smooth outward rise is expected from circle geometry",
        })
    return rows


def r4_donut(df: pd.DataFrame, h: float = config.MAIN_BANDWIDTH_M) -> list[dict]:
    return [_safe("R4 donut", f"drop |d| < {r:.0f} m", "stable", lambda r=r: rdd.fit(df, h, donut=r, label=f"donut {r:.0f}"))
            for r in config.DONUT_RADII_M]


def r5_timing(df: pd.DataFrame, events: pd.DataFrame, lineages: dict[str, list[str]],
              h: float = config.MAIN_BANDWIDTH_M) -> list[dict]:
    """Premium before and after a change in the grade in force, per school.

    Per-boundary fits (no boundary FE, postcode clusters). Only changes with at
    least TIMING_MIN_YEARS_EACH_SIDE years of sales either side qualify.
    """
    rows = []
    start, end = pd.Timestamp(config.SALES_START), pd.Timestamp(config.SALES_END)
    gap = pd.DateOffset(years=config.TIMING_MIN_YEARS_EACH_SIDE)
    idx = grades.index_events(events)
    for urn, lineage in lineages.items():
        hist = grades.grade_history(events, lineage)
        hist = hist[(hist["publication_date"] >= start + gap) & (hist["publication_date"] <= end - gap)]
        for change in hist.itertuples():
            before = grades.grade_in_force(idx, lineage, (change.publication_date - pd.Timedelta(days=1)).date())[0]
            if before is None or abs(before - change.grade) < 1:
                continue
            sub = df[df["boundary_id"] == urn]
            t = pd.Timestamp(change.publication_date)
            for label, part in (("before", sub[pd.to_datetime(sub["date"]) < t]), ("after", sub[pd.to_datetime(sub["date"]) >= t])):
                spec = f"URN {urn}: grade {before} -> {change.grade} published {t.date()}, {label}"
                rows.append(_safe("R5 timing", spec, "premium moves with the grade",
                                  lambda part=part: rdd.fit(part, h, fe=("property_type", "year_quarter"), cluster="postcode")))
    if not rows:
        rows.append(_row("R5 timing", "all selected schools", None, "premium moves with the grade",
                         note="not run: no qualifying change in grade in force (>= 1 grade, >= 2 years of sales either side)"))
    return rows


def r6_measurement(df: pd.DataFrame) -> list[dict]:
    rows = []
    for band in config.MEASUREMENT_ERROR_BANDS_M:
        share = float((df["d_signed_m"].abs() < band).mean())
        rows.append({"test": "R6 measurement error", "spec": f"share of sample with |d| < {band:.0f} m", "tau": share,
                     "expectation": "small; misclassification attenuates toward zero",
                     "note": "postcode centroids place ~15 addresses at one point; the estimate is a conservative floor"})
    return rows


def run_all(df: pd.DataFrame, events: pd.DataFrame | None = None, lineages: dict | None = None,
            h: float = config.MAIN_BANDWIDTH_M) -> pd.DataFrame:
    rows: list[dict] = []
    rows += r1_placebo(df, h)
    rows += r2_balance(df, h)
    rows += r3_density(df)
    rows += r4_donut(df, h)
    rows += r5_timing(df, events, lineages, h) if events is not None and lineages else [
        _row("R5 timing", "all selected schools", None, "premium moves with the grade", note="not run: no grade history supplied")]
    rows += r6_measurement(df)
    if "d_signed_yearly_m" in df:
        yearly = df.dropna(subset=["d_signed_yearly_m"])
        rows.append(_safe("R7 year-matched radius", "running variable from latest offer-day cut-off before sale", "same sign, similar size",
                          lambda: rdd.fit(yearly, h, running="d_signed_yearly_m")))
    rows.append(_safe("R8 single-boundary sales", "drop sales within h of 2+ boundaries", "stable",
                      lambda: rdd.fit(df[df["n_boundaries_within_main_h"] <= 1], h)))
    rows.append(_safe("R9 boundary-specific slopes", "slopes vary by boundary", "stable", lambda: rdd.fit(df, h, boundary_slopes=True)))
    rows.append(_safe("R10 extra controls", "add tenure and new-build FE", "stable",
                      lambda: rdd.fit(df, h, fe=rdd.MAIN_FE + ("tenure", "new_build"))))
    rows.append(_safe("R11 local quadratic", "poly = 2", "stable", lambda: rdd.fit(df, h, poly=2)))
    for b in sorted(df["boundary_id"].unique()):
        rows.append(_safe("R12 leave one boundary out", f"without {b}", "no single boundary drives the result",
                          lambda b=b: rdd.fit(df[df["boundary_id"] != b], h)))
    return pd.DataFrame(rows)


def per_boundary(df: pd.DataFrame, h: float = config.MAIN_BANDWIDTH_M) -> pd.DataFrame:
    """Forest-plot rows: each boundary alone, postcode-clustered."""
    rows = []
    for b, part in df.groupby("boundary_id"):
        try:
            r = rdd.fit(part, h, fe=("property_type", "year_quarter"), cluster="postcode", label=str(b))
            rows.append({"boundary_id": b, **{k: v for k, v in r.to_dict().items() if k not in ("notes", "pct", "pounds")},
                         "pct": r.pct[0], "pct_low": r.pct[1], "pct_high": r.pct[2]})
        except ValueError as e:
            rows.append({"boundary_id": b, "label": str(b), "notes": str(e)})
    return pd.DataFrame(rows)
