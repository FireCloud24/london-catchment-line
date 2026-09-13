"""EXPLORATORY, not pre-registered: why does one boundary differ?

Written after the main results were seen, to diagnose the Coombe Girls'
School boundary (+28% alone; pooled estimate falls from +1.8% to -0.4%
without it). Nothing here changes the headline. It runs the pre-registered
balance outcomes boundary by boundary, and describes what sits either side.

Writes outputs/exploratory/boundary_balance.csv
Usage:  python -m pipeline.x01_boundary_diagnostics [--octants]
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from line54 import config, rdd, robustness
from pipeline.p07_estimate import load_sample

OUT = config.ROOT / "outputs" / "exploratory"


def main() -> None:
    df, _ = load_sample()
    names = pd.read_parquet(config.INTERIM / "schools.parquet").set_index("urn")["name"]
    rows = []
    for b, part in df.groupby("boundary_id"):
        w = part[part["d_signed_m"].abs() < config.MAIN_BANDWIDTH_M]
        row = {"boundary_id": b, "school": names.get(b, b), "n": len(w)}
        for col in ["log_price", *robustness.BALANCE_OUTCOMES]:
            fe = ("year_quarter",) if col in robustness.PROPERTY_TYPE_OUTCOMES or col != "log_price" else ("property_type", "year_quarter")
            try:
                r = rdd.fit(part, config.MAIN_BANDWIDTH_M, outcome=col, fe=fe, cluster="postcode")
                row[f"{col}_jump"], row[f"{col}_p"] = r.tau, r.p_value
            except ValueError:
                row[f"{col}_jump"], row[f"{col}_p"] = np.nan, np.nan
            row[f"{col}_mean_in"] = w.loc[w["inside"], col].mean()
            row[f"{col}_mean_out"] = w.loc[~w["inside"], col].mean()
        rows.append(row)
    out = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT / "boundary_balance.csv", index=False)
    cols = ["school", "n", "log_price_jump", "is_flat_jump", "is_flat_p", "is_detached_jump", "is_detached_p",
            "imd19_rank_jump", "imd19_rank_p", "dist_station_m_jump", "dist_station_m_p"]
    with pd.option_context("display.width", 250, "display.float_format", "{:.3f}".format):
        print(out[cols].sort_values("log_price_jump").to_string(index=False))


if __name__ == "__main__" and "--octants" not in sys.argv:
    sys.exit(main())


def octant_check() -> pd.DataFrame:
    """EXPLORATORY: compare within the same 45-degree arc of each circle.

    A circle a few km across can pass through very different neighbourhoods
    on different sides. Boundary-by-octant fixed effects make each comparison
    local in direction as well as distance.
    """
    df, _ = load_sample()
    centres = pd.read_csv(config.TABLES / "boundary_summary.csv", dtype={"urn": str}).set_index("urn")
    e0 = df["boundary_id"].map(centres["easting"])
    n0 = df["boundary_id"].map(centres["northing"])
    octant = (np.degrees(np.arctan2(df["easting"] - e0, df["northing"] - n0)) % 360 // 45).astype(int)
    df = df.assign(arc=df["boundary_id"] + "_" + octant.astype(str))
    rows = []
    specs = {
        "main (pre-registered)": dict(),
        "boundary x octant FE": dict(fe=("property_type", "year_quarter", "arc")),
        "main, without Coombe Girls'": dict(data=df[df["boundary_id"] != "137848"]),
        "boundary x octant FE, without Coombe Girls'": dict(fe=("property_type", "year_quarter", "arc"), data=df[df["boundary_id"] != "137848"]),
    }
    for label, kw in specs.items():
        data = kw.pop("data", df)
        r = rdd.fit(data, config.MAIN_BANDWIDTH_M, label=label, **kw)
        rows.append({"spec": label, "pct": r.pct[0], "pct_low": r.pct[1], "pct_high": r.pct[2], "p": r.p_value, "n": r.n_obs})
    coombe = df[df["boundary_id"] == "137848"]
    for label, fe in (("Coombe Girls' alone", ("property_type", "year_quarter")), ("Coombe Girls' alone, octant FE", ("property_type", "year_quarter", "arc"))):
        r = rdd.fit(coombe, config.MAIN_BANDWIDTH_M, fe=fe, cluster="postcode", label=label)
        rows.append({"spec": label, "pct": r.pct[0], "pct_low": r.pct[1], "pct_high": r.pct[2], "p": r.p_value, "n": r.n_obs})
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "octant_check.csv", index=False)
    return out


if __name__ == "__main__" and "--octants" in sys.argv:
    print(octant_check().to_string(index=False))
