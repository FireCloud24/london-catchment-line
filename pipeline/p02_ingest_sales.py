"""Phase A1: Price Paid + ONSPD -> geolocated category-A sales around London.

Writes:
  data/interim/sales.parquet            every column the analysis needs
  data/interim/sale_locations.parquet   the same sales with NO price column;
                                        school screening (criterion C4) reads
                                        only this file, so it cannot see prices
  outputs/tables/sample_construction_ingest.csv
  outputs/tables/postcode_join_failures.csv

Usage:  python -m pipeline.p02_ingest_sales
"""
from __future__ import annotations

import sys

import duckdb

from line54 import config, geo
from line54.sample import StepLog

PP_COLUMNS = {
    "txn_id": "VARCHAR", "price": "BIGINT", "date": "TIMESTAMP", "postcode": "VARCHAR",
    "property_type": "VARCHAR", "new_build": "VARCHAR", "tenure": "VARCHAR", "paon": "VARCHAR",
    "saon": "VARCHAR", "street": "VARCHAR", "locality": "VARCHAR", "town": "VARCHAR",
    "district": "VARCHAR", "county": "VARCHAR", "ppd_category": "VARCHAR", "record_status": "VARCHAR",
}

# Sales are kept anywhere near London, not only inside it: an outer-borough
# school's catchment can cross into Surrey or Essex. 5 km beyond the extent of
# London postcodes covers a large radius plus the widest bandwidth.
REGION_BUFFER_M = 5000


def main() -> None:
    config.INTERIM.mkdir(parents=True, exist_ok=True)
    config.TABLES.mkdir(parents=True, exist_ok=True)
    onspd_csv = next((config.RAW / "onspd").glob("ONSPD_*_UK.csv"))
    pp_glob = (config.RAW / "price_paid" / "pp-*.csv").as_posix()
    scratch = config.INTERIM / "ingest_scratch.duckdb"
    # A file-backed scratch database rather than in-memory, so ~10M rows do not
    # need to fit in RAM. Nothing in it is an artefact; it is deleted at the end.
    con = duckdb.connect(str(scratch))
    log = StepLog()

    print("loading ONSPD", flush=True)
    con.execute(f"""
        CREATE OR REPLACE TABLE onspd AS
        SELECT pcds AS postcode_key, doterm, lad26cd AS laua,
               TRY_CAST(east1m AS INTEGER) AS easting, TRY_CAST(north1m AS INTEGER) AS northing,
               TRY_CAST(gridind AS INTEGER) AS gridind, lsoa11cd AS lsoa11, lsoa21cd AS lsoa21,
               TRY_CAST(imd20ind AS INTEGER) AS imd19_rank
        FROM read_csv('{onspd_csv.as_posix()}', all_varchar = true, header = true)
    """)
    dupes = con.execute("SELECT count(*) - count(DISTINCT postcode_key) FROM onspd").fetchone()[0]
    if dupes:
        raise ValueError(f"ONSPD has {dupes} duplicate postcodes; the join would multiply sales")

    # Price Paid stays a view over the CSVs. The cheap filters are counted in a
    # single pass, cumulatively, rather than by materialising a copy per step.
    cols = ", ".join(f"'{k}': '{v}'" for k, v in PP_COLUMNS.items())
    con.execute(f"CREATE OR REPLACE VIEW pp_raw AS SELECT * FROM read_csv('{pp_glob}', header = false, columns = {{{cols}}})")
    types = ", ".join(f"'{t}'" for t in config.PROPERTY_TYPES)
    cheap_steps = [
        ("category A", f"ppd_category = '{config.PPD_CATEGORY}'",
         "category B: repossessions, portfolio and court-ordered transfers, non-private buyers"),
        ("record status", f"record_status IS DISTINCT FROM '{config.DROP_RECORD_STATUS}'", "deleted records"),
        ("property type", f"property_type IN ({types})", "type O (other) is not a standard dwelling"),
        ("window", f"date >= DATE '{config.SALES_START}' AND date < DATE '{config.SALES_END}' + INTERVAL 1 DAY",
         f"transfer date outside {config.SALES_START}..{config.SALES_END}"),
        ("price floor", f"price >= {config.MIN_PRICE}", f"price below GBP {config.MIN_PRICE:,}: data error or not a market sale"),
    ]

    print("counting Price Paid filters", flush=True)
    cumulative, filters = [], []
    for _, where, _ in cheap_steps:
        cumulative.append(f"({where})")
        filters.append(f"count(*) FILTER (WHERE {' AND '.join(cumulative)})")
    counts = con.execute(f"SELECT count(*), count(DISTINCT txn_id), {', '.join(filters)} FROM pp_raw").fetchone()
    if counts[0] != counts[1]:
        raise ValueError(f"{counts[0] - counts[1]} duplicate transaction IDs across yearly files")
    log.record("raw", counts[0], f"all rows in yearly files {config.SALES_START.year}-{config.SALES_END.year}, England and Wales",
               n_before=counts[0])
    for (name, _, reason), n in zip(cheap_steps, counts[2:]):
        log.record(name, n, reason)

    print("joining ONSPD", flush=True)
    key = geo.normalise_postcode_sql("p.postcode")
    con.execute(f"""
        CREATE OR REPLACE TABLE pp_geo AS
        SELECT p.txn_id, p.price, p.date, p.postcode, p.property_type, p.new_build, p.tenure, p.paon, p.saon,
               p.street, p.district, p.county, {key} AS postcode_norm,
               o.laua, o.easting, o.northing, o.gridind, o.lsoa11, o.lsoa21, o.imd19_rank, o.doterm,
               o.postcode_key IS NOT NULL AS matched
        FROM pp_raw p LEFT JOIN onspd o ON o.postcode_key = {key}
        WHERE {' AND '.join(cumulative)}
    """)

    # Join failures are reported by year and district before they are dropped,
    # because a drop that is not random across areas is a bias, not noise.
    con.execute(f"""
        COPY (
            SELECT year(date) AS year, county = 'GREATER LONDON' AS london_county, district,
                   count(*) AS sales,
                   count(*) FILTER (WHERE postcode IS NULL OR trim(postcode) = '') AS no_postcode,
                   count(*) FILTER (WHERE NOT matched AND postcode IS NOT NULL AND trim(postcode) <> '') AS unmatched,
                   count(*) FILTER (WHERE matched AND gridind = {config.ONSPD_NO_GRID_REF}) AS no_grid_ref,
                   count(*) FILTER (WHERE matched AND doterm IS NOT NULL AND doterm <> '') AS matched_terminated
            FROM pp_geo GROUP BY ALL ORDER BY london_county DESC, district, year
        ) TO '{(config.TABLES / "postcode_join_failures.csv").as_posix()}' (HEADER)
    """)

    bbox = con.execute(f"""
        SELECT min(easting) - {REGION_BUFFER_M}, max(easting) + {REGION_BUFFER_M},
               min(northing) - {REGION_BUFFER_M}, max(northing) + {REGION_BUFFER_M}
        FROM onspd WHERE laua IN ({", ".join(f"'{c}'" for c in sorted(config.LONDON_LA_CODES))})
          AND gridind IS DISTINCT FROM {config.ONSPD_NO_GRID_REF}
    """).fetchone()
    geo_steps = [
        ("postcode present", "postcode IS NOT NULL AND trim(postcode) <> ''", "no postcode on the Land Registry record"),
        ("ONSPD match", "matched", "postcode not in ONSPD (live or terminated)"),
        ("grid reference", f"gridind IS DISTINCT FROM {config.ONSPD_NO_GRID_REF} AND easting IS NOT NULL",
         "ONSPD has no grid reference for the postcode"),
        ("study region", f"easting BETWEEN {bbox[0]} AND {bbox[1]} AND northing BETWEEN {bbox[2]} AND {bbox[3]}",
         f"outside the extent of London postcodes plus {REGION_BUFFER_M / 1000:g} km "
         f"(E {bbox[0]}-{bbox[1]}, N {bbox[2]}-{bbox[3]})"),
    ]
    geo_cumulative, geo_filters = [], []
    for _, where, _ in geo_steps:
        geo_cumulative.append(f"({where})")
        geo_filters.append(f"count(*) FILTER (WHERE {' AND '.join(geo_cumulative)})")
    for (name, _, reason), n in zip(geo_steps, con.execute(f"SELECT {', '.join(geo_filters)} FROM pp_geo").fetchone()):
        log.record(name, n, reason)
    final_where = " AND ".join(geo_cumulative)

    terminated = con.execute(
        f"SELECT count(*) FROM pp_geo WHERE {final_where} AND doterm IS NOT NULL AND doterm <> ''"
    ).fetchone()[0]
    print(f"  kept {log.rows[-1]['rows_after']:,} sales; {terminated:,} matched only via a terminated postcode", flush=True)

    sales = config.INTERIM / "sales.parquet"
    con.execute(f"""
        COPY (
            SELECT txn_id, price, CAST(date AS DATE) AS date,
                   year(date) || 'Q' || quarter(date) AS year_quarter,
                   postcode_norm AS postcode, property_type, tenure, new_build, paon, saon, street, district,
                   laua, easting, northing, gridind, lsoa11, lsoa21, imd19_rank
            FROM pp_geo WHERE {final_where} ORDER BY txn_id
        ) TO '{sales.as_posix()}' (FORMAT parquet)
    """)
    # Deliberately no price, tenure or property type: C4 is a count of places.
    con.execute(f"""
        COPY (SELECT txn_id, CAST(date AS DATE) AS date, postcode_norm AS postcode, easting, northing
              FROM pp_geo WHERE {final_where} ORDER BY txn_id)
        TO '{(config.INTERIM / "sale_locations.parquet").as_posix()}' (FORMAT parquet)
    """)
    log.write(config.TABLES / "sample_construction_ingest.csv")
    print(log.frame().to_string(index=False))
    con.close()
    scratch.unlink()


if __name__ == "__main__":
    sys.exit(main())
