"""Phase A2: GIAS + Ofsted -> schools table, grade history, C1-C3 screen.

The output of this phase is the research list: London secondaries that pass
C1 (phase/type/open), the part of C2 that GIAS can decide (not selective, no
religious character), and C3 (quality gradient). Only those schools are worth
the manual work of finding admissions cut-offs.

No sales data is read here.

Writes:
  data/interim/schools.parquet
  data/interim/ofsted_events.parquet
  outputs/tables/school_screen_c1_c3.csv

Usage:  python -m pipeline.p03_ingest_schools
"""
from __future__ import annotations

import sys
from datetime import date

import numpy as np
import pandas as pd

from line54 import config, grades

C1_TYPES = {
    "Community school", "Foundation school", "Voluntary controlled school",
    "Academy converter", "Academy sponsor led", "Free schools",
}
# Comparators are the realistic alternatives for a family just outside the
# line: any mainstream state secondary, faith schools included, but not
# special, alternative provision, UTC or studio schools.
COMPARATOR_TYPES = C1_TYPES | {"Voluntary aided school"}
PHASES = {"Secondary", "All-through"}
NO_RELIGION = {"Does not apply", "None", ""}


def _date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, format="%d-%m-%Y", errors="coerce")


def load_gias() -> tuple[pd.DataFrame, pd.DataFrame]:
    gias_dir = config.RAW / "gias"
    est = pd.read_csv(next(gias_dir.glob("edubasealldata*.csv")), encoding="cp1252", dtype=str, keep_default_na=False)
    links = pd.read_csv(next(gias_dir.glob("links_edubasealldata*.csv")), encoding="cp1252", dtype=str, keep_default_na=False)
    schools = pd.DataFrame(
        {
            "urn": est["URN"],
            "name": est["EstablishmentName"],
            "la_code": est["GSSLACode (name)"],
            "la_name": est["LA (name)"],
            "type": est["TypeOfEstablishment (name)"],
            "phase": est["PhaseOfEducation (name)"],
            "status": est["EstablishmentStatus (name)"],
            "open_date": _date(est["OpenDate"]),
            "close_date": _date(est["CloseDate"]),
            "admissions_policy": est["AdmissionsPolicy (name)"],
            "religious_character": est["ReligiousCharacter (name)"],
            "gender": est["Gender (name)"],
            "postcode": est["Postcode"],
            "easting": pd.to_numeric(est["Easting"], errors="coerce"),
            "northing": pd.to_numeric(est["Northing"], errors="coerce"),
        }
    )
    return schools, links


def load_ofsted_events() -> pd.DataFrame:
    frames = []
    for path in sorted((config.RAW / "ofsted").glob("*.csv")):
        frames.append(grades.events_from_frame(grades.read_ofsted_csv(path), path.stem))
    ev = pd.concat(frames, ignore_index=True)
    return grades.dedupe_events(ev)


def lineage_open_date(lineage: list[str], by_urn: pd.DataFrame) -> pd.Timestamp | None:
    """Earliest open date across a school's lineage.

    GIAS leaves OpenDate blank for many long-established schools; a blank on
    the oldest record in the chain means 'before records', which counts as open.
    """
    rows = by_urn.reindex(lineage)
    oldest = rows.iloc[-1]
    if pd.isna(oldest["open_date"]):
        return pd.Timestamp.min
    return rows["open_date"].min()


def open_on(schools: pd.DataFrame, on: date) -> pd.Series:
    t = pd.Timestamp(on)
    return (schools["open_date"].isna() | (schools["open_date"] <= t)) & (
        schools["close_date"].isna() | (schools["close_date"] > t)
    )


def main() -> None:
    config.TABLES.mkdir(parents=True, exist_ok=True)
    schools, links = load_gias()
    events = load_ofsted_events()
    events.to_parquet(config.INTERIM / "ofsted_events.parquet", index=False)
    schools.to_parquet(config.INTERIM / "schools.parquet", index=False)
    print(f"GIAS {len(schools):,} establishments; Ofsted {len(events):,} graded judgements", flush=True)

    by_urn = schools.set_index("urn")
    ref = config.GRADE_REFERENCE_DATE
    pred_map = grades.predecessor_map(links)
    ev_index = grades.index_events(events)

    comparators = schools[
        schools["type"].isin(COMPARATOR_TYPES)
        & schools["phase"].isin(PHASES)
        & (schools["admissions_policy"] != "Selective")
        & open_on(schools, ref)
        & schools["easting"].notna()
    ].copy()
    comparators["lineage"] = comparators["urn"].map(lambda u: grades.predecessors(u, pred_map))
    comparators["grade_ref"] = comparators["lineage"].map(lambda l: grades.grade_in_force(ev_index, l, ref)[0])
    graded = comparators.dropna(subset=["grade_ref"])

    london = schools[schools["la_code"].isin(config.LONDON_LA_CODES) & schools["phase"].isin(PHASES)].copy()
    rows = []
    for s in london.itertuples():
        lineage = grades.predecessors(s.urn, pred_map)
        first_open = lineage_open_date(lineage, by_urn)
        grade, grade_pub, grade_urn = grades.grade_in_force(ev_index, lineage, ref)
        row = {
            "urn": s.urn, "name": s.name, "la_name": s.la_name, "type": s.type, "phase": s.phase, "gender": s.gender,
            "status": s.status, "admissions_policy": s.admissions_policy, "religious_character": s.religious_character,
            "easting": s.easting, "northing": s.northing, "lineage": " < ".join(lineage),
            "lineage_open_date": None if first_open is pd.Timestamp.min else first_open.date(),
            "grade_2020": grade, "grade_2020_published": None if grade_pub is None else grade_pub.date(),
            "grade_2020_urn": grade_urn,
        }
        fails = []
        c1_open = first_open <= pd.Timestamp(config.OPEN_BY)
        c1_not_closed = pd.isna(s.close_date) or s.close_date >= pd.Timestamp(config.NOT_CLOSED_BEFORE)
        if s.type not in C1_TYPES or not c1_open or not c1_not_closed or pd.isna(s.easting):
            why = []
            if s.type not in C1_TYPES:
                why.append(f"type {s.type}")
            if not c1_open:
                why.append(f"opened {first_open.date()}")
            if not c1_not_closed:
                why.append(f"closed {s.close_date.date()}")
            if pd.isna(s.easting):
                why.append("no coordinates")
            fails.append("C1: " + "; ".join(why))
        if s.admissions_policy == "Selective" or s.religious_character not in NO_RELIGION:
            fails.append(f"C2 (GIAS): {s.admissions_policy}, religious character {s.religious_character or 'blank'}")

        # C3: three nearest other graded comparators, by straight-line distance.
        if not pd.isna(s.easting):
            others = graded[~graded["urn"].isin(lineage)]
            dist = np.hypot(others["easting"] - s.easting, others["northing"] - s.northing)
            nearest = others.assign(dist_m=dist).nsmallest(config.N_COMPARATOR_SCHOOLS, "dist_m")
            med = float(np.median(nearest["grade_ref"])) if len(nearest) else None
            row.update(
                comparator_urns=";".join(nearest["urn"]),
                comparator_names=";".join(nearest["name"]),
                comparator_dist_m=";".join(f"{d:.0f}" for d in nearest["dist_m"]),
                comparator_grades=";".join(str(int(g)) for g in nearest["grade_ref"]),
                comparator_median=med,
            )
            if grade is None:
                fails.append("C3: no grade in force on 2020-01-01")
            elif med is None or not grade < med:
                fails.append(f"C3: grade {grade} not better than comparator median {med}")
        row["first_fail"] = fails[0] if fails else ""
        row["all_fails"] = " | ".join(fails)
        row["research_candidate"] = not fails
        rows.append(row)

    screen = pd.DataFrame(rows).sort_values(["research_candidate", "la_name", "name"], ascending=[False, True, True])
    out = config.TABLES / "school_screen_c1_c3.csv"
    screen.to_csv(out, index=False)
    cand = screen[screen["research_candidate"]]
    print(f"London secondary/all-through records: {len(screen):,}")
    print(screen["first_fail"].str.split(":").str[0].replace("", "PASS").value_counts().to_string())
    print(f"\nresearch candidates: {len(cand)}")
    print(cand[["urn", "name", "la_name", "gender", "grade_2020", "comparator_grades"]].to_string(index=False))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    sys.exit(main())
