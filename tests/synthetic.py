"""Synthetic sales around circular catchments with a known, planted premium.

The point is not realism. It is to know the true answer, so a test can say
whether the estimator recovers it and whether the robustness checks stay
quiet when there is nothing to find.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def make_sample(
    tau: float = 0.08,
    n_boundaries: int = 20,
    sales_per_boundary: int = 3000,
    radius_m: tuple[float, float] = (700.0, 1400.0),
    slope_per_km: float = 0.10,
    cluster_sd: float = 0.02,
    noise_sd: float = 0.25,
    bunching: float = 0.0,
    seed: int = 0,
) -> pd.DataFrame:
    """One row per sale, already in rdd_sample shape.

    Sales are uniform by area in a ring of +/-1 km around each circle, so the
    density of d rises smoothly outward (as real circle geometry does) with no
    jump at zero, unless `bunching` moves a share of outside sales to just inside.
    """
    rng = np.random.default_rng(seed)
    frames = []
    for b in range(n_boundaries):
        r = rng.uniform(*radius_m)
        inner, outer = max(r - 1000.0, 0.0), r + 1000.0
        rho = np.sqrt(rng.uniform(inner**2, outer**2, sales_per_boundary))
        d = r - rho
        if bunching:
            movers = (d < 0) & (d > -100) & (rng.random(len(d)) < bunching)
            d[movers] = -d[movers]
        year = rng.integers(2015, 2026, len(d))
        quarter = rng.integers(1, 5, len(d))
        ptype = rng.choice(list("DSTF"), len(d), p=[0.1, 0.25, 0.35, 0.3])
        # Covariates are smooth in d with no jump, so balance tests should pass.
        tenure = np.where((ptype == "F") | (rng.random(len(d)) < 0.05), "L", "F")
        new_build = np.where(rng.random(len(d)) < 0.08, "Y", "N")
        imd_rank = np.clip(15000 + 3.0 * d + rng.normal(0, 4000, len(d)), 1, 32844)
        dist_station = np.abs(900 + 0.2 * d + rng.normal(0, 300, len(d)))
        # R7: yearly radius wobbles around the median, so d shifts by a year-specific amount.
        wobble = {y: rng.normal(0, 60) for y in range(2015, 2026)}
        d_yearly = d + np.array([wobble[y] for y in year])
        inside = d > 0
        log_price = (
            12.5
            + rng.normal(0, 0.3)  # boundary level
            + 0.03 * (year - 2015)
            + pd.Series(ptype).map({"D": 0.4, "S": 0.2, "T": 0.0, "F": -0.3}).to_numpy()
            + slope_per_km * d / 1000.0
            + tau * inside
            + rng.normal(0, cluster_sd)  # boundary-specific shock to the jump
            * inside
            + rng.normal(0, noise_sd, len(d))
        )
        frames.append(
            pd.DataFrame(
                {
                    "txn_id": [f"b{b}-{i}" for i in range(len(d))],
                    "boundary_id": f"B{b:02d}",
                    "d_signed_m": d,
                    "inside": inside,
                    "log_price": log_price,
                    "price": np.exp(log_price),
                    "property_type": ptype,
                    "tenure": tenure,
                    "new_build": new_build,
                    "year_quarter": [f"{y}Q{q}" for y, q in zip(year, quarter)],
                    "date": [pd.Timestamp(year=y, month=3 * q - 1, day=15).date() for y, q in zip(year, quarter)],
                    "postcode": [f"P{b}-{int(x // 40)}" for x in d],  # ~40 m postcode units
                    "imd19_rank": imd_rank,
                    "dist_station_m": dist_station,
                    "is_flat": (ptype == "F").astype(float),
                    "is_detached": (ptype == "D").astype(float),
                    "is_leasehold": (tenure == "L").astype(float),
                    "is_new_build": (new_build == "Y").astype(float),
                    "d_signed_yearly_m": d_yearly,
                    "n_boundaries_within_main_h": 1,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)
