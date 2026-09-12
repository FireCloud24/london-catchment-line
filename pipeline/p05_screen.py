"""Phase B2: apply C2, C4 and C5 and write the selection table and check map.

C2 is a human judgement recorded in catchments/research_log.csv. C5 is
computed from provenance. C4 counts sales near each boundary from
sale_locations.parquet, which has no price column: the check below makes that
structural rather than a promise.

Writes:
  outputs/tables/school_screen.csv      every candidate, first failing criterion
  outputs/boundary_check_map.html       Leaflet map of candidate boundaries over OSM

Usage:  python -m pipeline.p05_screen [--statuses draft,verified]
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from pyproj import Transformer

from line54 import catchments, config

LOCATION_COLUMNS = ["txn_id", "date", "easting", "northing"]


def load_locations() -> pd.DataFrame:
    path = config.INTERIM / "sale_locations.parquet"
    available = pq.read_schema(path).names
    if "price" in available:
        raise RuntimeError("sale_locations.parquet contains a price column; screening must be price-blind")
    return pd.read_parquet(path, columns=LOCATION_COLUMNS)


def count_sides(locs: pd.DataFrame, b: catchments.Boundary, h: float) -> tuple[int, int]:
    e, n = locs["easting"].to_numpy(float), locs["northing"].to_numpy(float)
    reach = (b.radius_m or 0) + h + 10
    near = (np.abs(e - b.easting) < reach) & (np.abs(n - b.northing) < reach)
    d = b.signed_distance(e[near], n[near])
    return int(((d > 0) & (d < h)).sum()), int(((d <= 0) & (d > -h)).sum())


def screen(summary: pd.DataFrame, log: pd.DataFrame, counts: dict, rules: dict) -> pd.DataFrame:
    out = []
    for r in log.itertuples():
        row = {"urn": r.urn, "school_name": r.school_name, "la_name": r.la_name, "research_decision": r.decision, "c2": r.c2}
        s = summary[summary["urn"] == r.urn]
        fails = []
        if not str(r.c2).startswith("pass"):
            fails.append(f"C2: {r.c2 or 'not established'} ({r.decision})")
        # DEVIATIONS 2026-09-12: any round in which everyone was offered means
        # no boundary existed that year, so the school fails C5 outright.
        not_applied = str(getattr(r, "years_not_applied", "") or "").strip()
        if not_applied:
            fails.append(f"C5: undersubscribed in {not_applied} (no boundary that year)")
        if s.empty:
            fails.append("C5: no usable cut-off figures")
        else:
            s = s.iloc[0]
            row.update(n_years=s["n_years"], radius_median_m=s["radius_median_m"], cv=s["cv"])
            if s["n_years"] < config.MIN_CUTOFF_YEARS:
                fails.append(f"C5: {s['n_years']} year(s) < {config.MIN_CUTOFF_YEARS}")
            elif s["cv"] is not None and not pd.isna(s["cv"]) and s["cv"] > rules["MAX_CUTOFF_CV"]:
                fails.append(f"C5: CV {s['cv']:.3f} > {rules['MAX_CUTOFF_CV']}")
            if s["radius_median_m"] is not None and s["radius_median_m"] < config.MIN_MEDIAN_RADIUS_M:
                fails.append(f"C5: median radius {s['radius_median_m']:.0f} m < {config.MIN_MEDIAN_RADIUS_M:.0f}")
            n_in, n_out = counts.get(r.urn, (0, 0))
            row.update(sales_inside_400m=n_in, sales_outside_400m=n_out)
            if min(n_in, n_out) < rules["MIN_SALES_PER_SIDE"]:
                fails.append(f"C4: {n_in} inside / {n_out} outside < {rules['MIN_SALES_PER_SIDE']}")
        row["first_fail"] = fails[0] if fails else ""
        row["all_fails"] = " | ".join(fails)
        row["passes"] = not fails
        out.append(row)
    return pd.DataFrame(out)


def write_map(summary: pd.DataFrame, table: pd.DataFrame, path) -> None:
    """Circles over OpenStreetMap, for the plan's 'inspect every boundary' step.

    A local HTML file rather than a published page: it pulls map tiles from
    OpenStreetMap, and it shows draft figures nobody has verified yet.
    """
    to_wgs = Transformer.from_crs(config.CRS, "EPSG:4326", always_xy=True)
    feats = []
    for s in summary.itertuples():
        lon, lat = to_wgs.transform(s.easting, s.northing)
        t = table[table["urn"] == s.urn]
        passes = bool(t["passes"].iloc[0]) if len(t) else False
        feats.append({
            "urn": s.urn, "name": s.name, "lat": lat, "lon": lon, "r": s.radius_median_m,
            "rmin": s.radius_min_m, "rmax": s.radius_max_m, "years": s.years, "cv": s.cv, "passes": passes,
            "why": t["first_fail"].iloc[0] if len(t) else "",
        })
    html = """<!doctype html><html><head><meta charset="utf-8"><title>Boundary check map</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>html,body,#m{height:100%;margin:0;font:13px system-ui,sans-serif}.k{position:absolute;z-index:999;top:10px;right:10px;background:#fff;padding:8px 10px;border-radius:6px;box-shadow:0 1px 4px #0003;max-width:280px}</style>
</head><body><div id="m"></div><div class="k"><b>Draft catchment boundaries</b><br>
Solid: median radius (study boundary). Dashed: min and max year.<br>
<span style="color:#1b7f5b">&#9679;</span> passes screen &nbsp;<span style="color:#b3261e">&#9679;</span> fails<br>
Check each circle: does it swallow parkland, a reservoir or a railway? Is the school point on the school?</div>
<script>
const F = """ + json.dumps(feats) + """;
const m = L.map('m').setView([51.5, -0.12], 10);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19, attribution: '&copy; OpenStreetMap contributors'}).addTo(m);
for (const f of F) {
  const c = f.passes ? '#1b7f5b' : '#b3261e';
  L.circle([f.lat, f.lon], {radius: f.r, color: c, weight: 2, fill: false}).addTo(m)
   .bindPopup(`<b>${f.name}</b> (URN ${f.urn})<br>median ${Math.round(f.r)} m, years ${f.years}<br>CV ${f.cv === null ? '-' : f.cv.toFixed(3)}<br>${f.why || 'passes'}`);
  for (const r of [f.rmin, f.rmax]) if (r) L.circle([f.lat, f.lon], {radius: r, color: c, weight: 1, dashArray: '4 4', fill: false}).addTo(m);
  L.circleMarker([f.lat, f.lon], {radius: 3, color: c}).addTo(m);
}
</script></body></html>"""
    path.write_text(html, encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--statuses", default="verified")
    args = ap.parse_args(argv)
    statuses = set(args.statuses.split(","))

    prov = catchments.read_provenance()
    schools = pd.read_parquet(config.INTERIM / "schools.parquet")
    boundaries = catchments.build_boundaries(prov, schools, statuses)
    summary = pd.read_csv(config.TABLES / "boundary_summary.csv", dtype={"urn": str})
    summary = summary[summary["urn"].isin(boundaries)]
    log = pd.read_csv(config.CATCHMENTS / "research_log.csv", dtype=str, keep_default_na=False)

    locs = load_locations()
    counts = {urn: count_sides(locs, b, config.SCREEN_BANDWIDTH_M) for urn, b in boundaries.items()}

    # Pre-registered fallback ladder: relax one step at a time, stop at MIN_BOUNDARIES.
    rules = {"MAX_CUTOFF_CV": config.MAX_CUTOFF_CV, "MIN_SALES_PER_SIDE": config.MIN_SALES_PER_SIDE}
    step = 0
    table = screen(summary, log, counts, rules)
    while table["passes"].sum() < config.MIN_BOUNDARIES and step < len(config.FALLBACK_LADDER):
        rules.update(config.FALLBACK_LADDER[step])
        step += 1
        table = screen(summary, log, counts, rules)
    table["fallback_step"] = step
    table = table.sort_values(["passes", "la_name", "school_name"], ascending=[False, True, True])
    table.to_csv(config.TABLES / "school_screen.csv", index=False)
    write_map(summary, table, config.ROOT / "outputs" / "boundary_check_map.html")

    print(f"statuses {sorted(statuses)}; fallback step {step}; rules {rules}")
    print(f"{int(table['passes'].sum())} of {len(table)} candidates pass C2, C4 and C5")
    cols = ["urn", "school_name", "n_years", "radius_median_m", "cv", "sales_inside_400m", "sales_outside_400m", "first_fail"]
    print(table[table["research_decision"].isin(["draft_include", "pending_c2"])][cols].to_string(index=False))


if __name__ == "__main__":
    sys.exit(main())
