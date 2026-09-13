"""Phase C: the stored, hashed RD sample. First phase that reads prices.

Refuses to run until the boundary selection is locked (section 9 of the
pre-registration). Writes:
  data/processed/rdd_sample.parquet
  data/processed/rdd_sample.sha256
  outputs/tables/sample_construction.csv   ingest steps + assembly steps

Usage:  python -m pipeline.p06_assemble_sample
"""
from __future__ import annotations

import json
import sys
from datetime import date

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from line54 import catchments, config, lock, sample

SALE_COLUMNS = ["txn_id", "price", "date", "year_quarter", "postcode", "property_type", "tenure", "new_build",
                "laua", "lsoa11", "imd19_rank", "easting", "northing"]


def load_stations() -> np.ndarray | None:
    frames = []
    for area, types in (("910", {"RLY"}), ("940", {"MET"})):
        path = config.RAW / "naptan" / f"naptan_{area}.csv"
        if not path.exists():
            return None
        d = pd.read_csv(path, dtype=str, usecols=["StopType", "Status", "Easting", "Northing"])
        d = d[d["StopType"].isin(types) & (d["Status"] == "active")]
        frames.append(d[["Easting", "Northing"]].astype(float).to_numpy())
    return np.vstack(frames)


def assemble(sales: pd.DataFrame, boundaries: list[catchments.Boundary], genders: list[str],
             stations: np.ndarray | None, sex_aware: bool = config.SEX_AWARE_CONTAMINATION,
             active_from: dict | None = None) -> tuple[pd.DataFrame, sample.StepLog]:
    active_from = config.BOUNDARY_ACTIVE_FROM if active_from is None else active_from
    log = sample.StepLog()
    log.record("geolocated sales", len(sales), "from phase A1 (see sample_construction_ingest)", n_before=len(sales))

    e, n = sales["easting"].to_numpy(float), sales["northing"].to_numpy(float)
    near = np.zeros(len(sales), dtype=bool)
    for b in boundaries:
        reach = (b.radius_m or 0) + config.MAX_BANDWIDTH_M
        near |= (np.abs(e - b.easting) <= reach) & (np.abs(n - b.northing) <= reach)
    sales = sales.loc[near].reset_index(drop=True)
    log.record("near a selected boundary", len(sales), f"outside every boundary's box of radius + {config.MAX_BANDWIDTH_M:g} m")

    D = sample.distance_matrix(sales["easting"].to_numpy(float), sales["northing"].to_numpy(float), boundaries)
    ids = [b.boundary_id for b in boundaries]
    sale_dates = pd.to_datetime(sales["date"]).to_numpy()
    for j, bid in enumerate(ids):
        start = active_from.get(bid)
        if start is not None:
            # NaN distances are neither inside, outside nor within any bandwidth.
            D[sale_dates < np.datetime64(start), j] = np.nan
            log.record(f"boundary {bid} not in force", len(sales),
                       f"sales before {start} ignore this boundary (0 rows dropped here; pairs removed below)")
    pairs = sample.assign(sales["txn_id"].to_numpy(), D, ids, log=log, compatible=sample.compatibility(genders, sex_aware))

    df = pairs.merge(sales, on="txn_id", how="left", validate="one_to_one")
    df["log_price"] = np.log(df["price"].astype(float))
    df["is_flat"] = (df["property_type"] == "F").astype(float)
    df["is_detached"] = (df["property_type"] == "D").astype(float)
    df["is_leasehold"] = (df["tenure"] == "L").astype(float)
    df["is_new_build"] = (df["new_build"] == "Y").astype(float)

    # R7: the same pair, re-measured against the cut-off known at the date of sale.
    by_id = {b.boundary_id: b for b in boundaries}
    yearly = np.full(len(df), np.nan)
    for i, (bid, e_, n_, dt) in enumerate(zip(df["boundary_id"], df["easting"], df["northing"], pd.to_datetime(df["date"]))):
        b = by_id[bid]
        r = b.radius_for_sale(dt.date()) if b.radius_m is not None else None
        if r is not None:
            yearly[i] = r - np.hypot(e_ - b.easting, n_ - b.northing)
    df["d_signed_yearly_m"] = yearly

    if stations is not None:
        dist, _ = cKDTree(stations).query(df[["easting", "northing"]].to_numpy(float))
        df["dist_station_m"] = dist
    return df.sort_values(["boundary_id", "txn_id"]).reset_index(drop=True), log


def main() -> None:
    payload = lock.require_lock()
    selected = payload["selected_urns"]
    prov = catchments.read_provenance()
    schools = pd.read_parquet(config.INTERIM / "schools.parquet")
    built = catchments.build_boundaries(prov[prov["urn"].isin(selected)], schools, {"verified"})
    missing = set(selected) - set(built)
    if missing:
        raise SystemExit(f"locked schools without verified boundaries: {sorted(missing)}")
    boundaries = [built[u] for u in selected]
    genders = schools.set_index("urn").loc[selected, "gender"].tolist()

    sales = pd.read_parquet(config.INTERIM / "sales.parquet", columns=SALE_COLUMNS)
    df, log = assemble(sales, boundaries, genders, load_stations())

    config.PROCESSED.mkdir(parents=True, exist_ok=True)
    out = config.PROCESSED / "rdd_sample.parquet"
    df.to_parquet(out, index=False)
    digest = sample.frame_sha256(df)
    (config.PROCESSED / "rdd_sample.sha256").write_text(json.dumps({
        "sha256": digest, "rows": len(df), "built": str(date.today()),
        "provenance_sha256": payload["provenance_sha256"], "sex_aware_contamination": config.SEX_AWARE_CONTAMINATION,
    }, indent=2))

    ingest = pd.read_csv(config.TABLES / "sample_construction_ingest.csv")
    ingest.insert(0, "phase", "A1 ingest")
    assembly = log.frame()
    assembly.insert(0, "phase", "C assembly")
    pd.concat([ingest, assembly], ignore_index=True).to_csv(config.TABLES / "sample_construction.csv", index=False)
    print(log.frame().to_string(index=False))
    print(f"{len(df):,} sale-boundary rows -> {out} (sha256 {digest[:16]})")


if __name__ == "__main__":
    sys.exit(main())
