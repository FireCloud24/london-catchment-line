"""Phase B: provenance.csv -> one boundary per school, plus the appendix tables.

Writes:
  data/interim/catchments.gpkg                 boundaries, EPSG:27700
  outputs/tables/boundary_summary.csv          C5 inputs: years, median radius, CV
  outputs/tables/boundary_provenance.csv       appendix: every school-year figure and source

Before verification this runs on draft rows (--statuses draft) so the screen
and the map can be produced for checking. Estimation never reads its output
directly: phase 06 rebuilds boundaries from verified rows after the lock.

Usage:  python -m pipeline.p04_build_catchments [--statuses verified|draft,verified]
"""
from __future__ import annotations

import argparse
import sys

import geopandas as gpd
import pandas as pd

from line54 import catchments, config, geo


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--statuses", default="verified", help="comma-separated provenance statuses to include")
    args = ap.parse_args(argv)
    statuses = set(args.statuses.split(","))

    prov = catchments.read_provenance()
    errors = catchments.validate(prov)
    if errors:
        raise SystemExit("provenance.csv has errors:\n  " + "\n  ".join(errors))

    schools = pd.read_parquet(config.INTERIM / "schools.parquet")
    boundaries = catchments.build_boundaries(prov, schools, statuses)
    names = schools.set_index("urn")["name"]

    rows, geoms = [], []
    for b in boundaries.values():
        rows.append(
            {
                "urn": b.urn,
                "name": names.get(b.urn, ""),
                "route": b.route,
                "n_years": b.n_years,
                "radius_median_m": b.radius_m,
                "radius_min_m": min(b.radius_by_year.values()) if b.radius_by_year else None,
                "radius_max_m": max(b.radius_by_year.values()) if b.radius_by_year else None,
                "cv": b.cv,
                "years": ",".join(str(y) for y in sorted(b.radius_by_year)),
                "easting": b.easting,
                "northing": b.northing,
            }
        )
        geoms.append(b.geometry())

    summary = pd.DataFrame(rows).sort_values("urn")
    config.TABLES.mkdir(parents=True, exist_ok=True)
    summary.to_csv(config.TABLES / "boundary_summary.csv", index=False)

    gdf = gpd.GeoDataFrame(pd.DataFrame(rows), geometry=geoms, crs=config.CRS)
    geo.require_projected(gdf.crs)
    out = config.INTERIM / "catchments.gpkg"
    gdf.to_file(out, layer="boundaries", driver="GPKG")

    appendix = prov[prov["status"].isin(statuses)][
        ["urn", "school_name", "la_name", "entry_year", "route", "cutoff_as_published", "cutoff_m",
         "cutoff_basis", "distance_method", "source_title", "source_url", "source_accessed", "status", "notes"]
    ]
    appendix.to_csv(config.TABLES / "boundary_provenance.csv", index=False)
    print(f"{len(boundaries)} boundaries from statuses {sorted(statuses)} -> {out}")
    print(summary[["urn", "name", "n_years", "radius_median_m", "cv"]].to_string(index=False))


if __name__ == "__main__":
    sys.exit(main())
