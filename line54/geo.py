"""Spatial primitives: postcode keys, CRS guard, signed distance to a boundary.

Sign convention everywhere: positive inside the catchment, negative outside.
Treatment is d > 0.
"""
from __future__ import annotations

import re

import numpy as np
import shapely
from pyproj import CRS

from . import config

_WS = re.compile(r"\s+")


def normalise_postcode(pc: str | None) -> str | None:
    """Uppercase, single space before the inward code.

    Price Paid and ONSPD mostly agree already, but a few Price Paid rows carry
    double spaces or no space; an exact-string join silently drops them.
    """
    if pc is None:
        return None
    compact = _WS.sub("", pc).upper()
    if len(compact) < 5:
        return None
    return f"{compact[:-3]} {compact[-3:]}"


def normalise_postcode_sql(col: str) -> str:
    """The same rule as a DuckDB expression, so ingestion can join in SQL.

    Kept next to the Python version and tested against it, because two
    normalisations that disagree on one edge case are a silent join loss.
    """
    compact = f"upper(regexp_replace(coalesce({col}, ''), '\\s+', '', 'g'))"
    return (
        f"CASE WHEN length({compact}) < 5 THEN NULL "
        f"ELSE substr({compact}, 1, length({compact}) - 3) || ' ' || "
        f"substr({compact}, length({compact}) - 2) END"
    )


def require_projected(crs: object) -> None:
    """Refuse to compute distances in anything but British National Grid."""
    parsed = CRS.from_user_input(crs)
    if parsed.is_geographic:
        raise ValueError(
            f"{parsed.name} is geographic; distances would be in degrees. "
            f"Reproject to {config.CRS} first."
        )
    if parsed != CRS.from_user_input(config.CRS):
        raise ValueError(f"expected {config.CRS}, got {parsed.to_string()}")


def signed_distance_circle(
    easting: np.ndarray, northing: np.ndarray, centre_e: float, centre_n: float, radius_m: float
) -> np.ndarray:
    """Route 2 boundary: radius minus distance to the school.

    Computed analytically rather than against a buffered polygon, because a
    buffer is a many-sided approximation and the error lands exactly at the
    boundary, which is the only place this design looks.
    """
    e = np.asarray(easting, dtype=float)
    n = np.asarray(northing, dtype=float)
    return radius_m - np.hypot(e - centre_e, n - centre_n)


def signed_distance_polygon(
    easting: np.ndarray, northing: np.ndarray, polygon: shapely.Polygon | shapely.MultiPolygon
) -> np.ndarray:
    """Routes 1 and 3: distance to the polygon's boundary, signed by containment."""
    e = np.asarray(easting, dtype=float)
    n = np.asarray(northing, dtype=float)
    points = shapely.points(e, n)
    unsigned = shapely.distance(points, polygon.boundary)
    inside = shapely.contains_xy(polygon, e, n)
    return np.where(inside, unsigned, -unsigned)
