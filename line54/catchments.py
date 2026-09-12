"""Catchment provenance: from one row per school-year to one boundary per school.

provenance.csv is the hand-built dataset this project exists to create, so it
is validated strictly: a figure without a source URL, or a radius that does not
reproduce from the number as published, is an error rather than a warning.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import shapely

from . import config, geo

PROVENANCE_COLUMNS = [
    "urn",
    "school_name",
    "la_name",
    "entry_year",
    "route",  # published_polygon | reconstructed_radius | digitised
    "cutoff_as_published",  # verbatim, e.g. "0.842 miles", "1,254m", "1.25km"
    "cutoff_m",
    "cutoff_basis",  # offer_day | final
    "distance_method",  # straight_line | walking | other
    "priority_order",  # the oversubscription criteria in order, as summarised
    "excludes_checked",  # which C2 exclusions were checked against the policy
    "aptitude_share",
    "policy_url",
    "source_title",
    "source_url",
    "source_accessed",
    "polygon_file",
    "status",  # draft | verified | rejected
    "verified_by",
    "verified_on",
    "notes",
]

ROUTES = {"published_polygon", "reconstructed_radius", "digitised"}
STATUSES = {"draft", "verified", "rejected"}

_UNITS_TO_M = {"m": 1.0, "metres": 1.0, "meters": 1.0, "km": 1000.0, "miles": 1609.344, "mile": 1609.344}
_PUBLISHED = re.compile(r"^\s*([\d,]*\.?\d+)\s*(m|metres|meters|km|miles|mile)\s*$", re.IGNORECASE)


def parse_published_distance(text: str) -> float:
    """Convert a council's figure to metres. Councils mix miles, km and metres."""
    m = _PUBLISHED.match(str(text))
    if not m:
        raise ValueError(f"unrecognised distance {text!r}; write it as e.g. '0.842 miles' or '1254m'")
    return float(m.group(1).replace(",", "")) * _UNITS_TO_M[m.group(2).lower()]


def read_provenance(path: Path = config.PROVENANCE_FILE) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = [c for c in PROVENANCE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name} missing columns: {missing}")
    df["entry_year"] = df["entry_year"].astype(int)
    df["cutoff_m"] = pd.to_numeric(df["cutoff_m"].replace("", np.nan))
    df["aptitude_share"] = pd.to_numeric(df["aptitude_share"].replace("", "0"))
    return df


def validate(df: pd.DataFrame) -> list[str]:
    """Every problem, not just the first, so one pass fixes the whole file."""
    errors: list[str] = []
    for i, r in df.iterrows():
        where = f"row {i + 2} (URN {r['urn']}, {r['entry_year']})"
        if r["route"] not in ROUTES:
            errors.append(f"{where}: route {r['route']!r} not in {sorted(ROUTES)}")
        if r["status"] not in STATUSES:
            errors.append(f"{where}: status {r['status']!r} not in {sorted(STATUSES)}")
        if not r["source_url"].startswith("http"):
            errors.append(f"{where}: no source URL")
        if r["route"] == "reconstructed_radius":
            try:
                parsed = parse_published_distance(r["cutoff_as_published"])
                if not np.isclose(parsed, r["cutoff_m"], atol=1.0):
                    errors.append(f"{where}: cutoff_m {r['cutoff_m']} != {r['cutoff_as_published']} = {parsed:.0f} m")
            except ValueError as e:
                errors.append(f"{where}: {e}")
        elif not r["polygon_file"]:
            errors.append(f"{where}: {r['route']} needs a polygon_file")
        if r["status"] == "verified" and not (r["verified_by"] and r["verified_on"]):
            errors.append(f"{where}: verified rows need verified_by and verified_on")
        if r["entry_year"] not in config.ENTRY_YEARS:
            errors.append(f"{where}: entry year outside the pre-registered window")
    dup = df.duplicated(subset=["urn", "entry_year"], keep=False)
    for _, r in df[dup].iterrows():
        errors.append(f"URN {r['urn']} entry {r['entry_year']}: duplicated school-year")
    return errors


@dataclass
class Boundary:
    urn: str
    route: str
    easting: float
    northing: float
    radius_m: float | None  # median across years, Route 2
    radius_by_year: dict[int, float]
    polygon: shapely.Polygon | None
    n_years: int
    cv: float | None

    @property
    def boundary_id(self) -> str:
        return self.urn

    def signed_distance(self, e: np.ndarray, n: np.ndarray) -> np.ndarray:
        if self.radius_m is not None:
            return geo.signed_distance_circle(e, n, self.easting, self.northing, self.radius_m)
        return geo.signed_distance_polygon(e, n, self.polygon)

    def geometry(self) -> shapely.Polygon:
        if self.polygon is not None:
            return self.polygon
        # For display and GeoPackage export only; distances never use this.
        return shapely.Point(self.easting, self.northing).buffer(self.radius_m, quad_segs=64)

    def radius_for_sale(self, sale_date: date) -> float | None:
        """R7: the cut-off from the latest offer day on or before the sale.

        National offer day for secondary places is 1 March of the entry year;
        a sale before any published cut-off gets None and drops out of R7.
        """
        known = [y for y in self.radius_by_year if date(y, 3, 1) <= sale_date]
        return self.radius_by_year[max(known)] if known else None


def stability(radii: list[float]) -> tuple[int, float | None, float | None]:
    """(years, median, coefficient of variation). CV uses the sample SD."""
    arr = np.asarray(radii, dtype=float)
    if len(arr) == 0:
        return 0, None, None
    med = float(np.median(arr))
    cv = float(np.std(arr, ddof=1) / np.mean(arr)) if len(arr) > 1 else None
    return len(arr), med, cv


def build_boundaries(prov: pd.DataFrame, schools: pd.DataFrame, statuses: set[str]) -> dict[str, Boundary]:
    """One Boundary per school from rows with an accepted status."""
    rows = prov[prov["status"].isin(statuses)]
    loc = schools.set_index("urn")[["easting", "northing"]]
    out: dict[str, Boundary] = {}
    for urn, g in rows.groupby("urn"):
        if urn not in loc.index:
            raise KeyError(f"URN {urn} in provenance but not in schools table")
        e, n = (float(v) for v in loc.loc[urn])
        routes = set(g["route"])
        if len(routes) > 1:
            raise ValueError(f"URN {urn} mixes routes {routes}; one route per school")
        route = routes.pop()
        if route == "reconstructed_radius":
            by_year = dict(zip(g["entry_year"].astype(int), g["cutoff_m"].astype(float)))
            k, med, cv = stability(list(by_year.values()))
            out[urn] = Boundary(urn, route, e, n, med, by_year, None, k, cv)
        else:
            import geopandas as gpd

            files = g["polygon_file"].unique()
            gdf = gpd.read_file(config.CATCHMENTS / files[-1])
            if gdf.crs is None:
                raise ValueError(f"{files[-1]} has no CRS")
            gdf = gdf.to_crs(config.CRS)
            geo.require_projected(gdf.crs)
            out[urn] = Boundary(urn, route, e, n, None, {}, shapely.union_all(gdf.geometry.values), len(g), None)
    return out
