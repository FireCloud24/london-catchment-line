"""Ofsted grade in force at a date, following a school across URN changes.

Two traps. First, an academy conversion issues a new URN, and the grade that
parents see belongs to the predecessor URN until the academy is inspected, so
a join on the current URN alone makes converted schools look ungraded.
Second, Outstanding schools were exempt from routine inspection from 2011 to
2021, so a school's grade in 2020 can come from an inspection in 2008.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

GRADES = {"1": 1, "2": 2, "3": 3, "4": 4}
GRADE_NAMES = {1: "Outstanding", 2: "Good", 3: "Requires improvement", 4: "Inadequate"}

# (URN column, publication date column, grade column, inspection number column)
_EVENT_COLUMNS = [
    ("URN", "Publication date", "Overall effectiveness", "Inspection number"),
    ("URN at time of previous inspection", "Previous publication date", "Previous overall effectiveness", "Previous inspection number"),
    ("URN at time of previous full inspection", "Previous publication date", "Previous full inspection overall effectiveness", "Previous full inspection number"),
    ("URN at time of latest full inspection", "Publication date", "Overall effectiveness", "Inspection number of latest full inspection"),
    ("URN at time of latest OEIF graded inspection", "Publication date of latest OEIF graded inspection", "Latest OEIF overall effectiveness", "Inspection number of latest OEIF graded inspection"),
]


def read_ofsted_csv(path: Path) -> pd.DataFrame:
    """Ofsted files are cp1252, and some open with a title line above the header."""
    with path.open(encoding="cp1252") as f:
        first = f.readline()
    return pd.read_csv(path, dtype=str, encoding="cp1252", skiprows=0 if "URN" in first else 1)


def events_from_frame(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """Every graded judgement a file mentions, whether current or 'previous'."""
    out = []
    latest_snapshot = "URN at time of latest full inspection" in df.columns
    for urn_col, pub_col, grade_col, num_col in _EVENT_COLUMNS:
        # In a latest-inspections snapshot, 'URN' is the current school, not
        # the URN at the time; the explicit column is the right one there.
        if urn_col == "URN" and latest_snapshot:
            continue
        if not {urn_col, pub_col, grade_col} <= set(df.columns):
            continue
        part = pd.DataFrame(
            {
                "urn": df[urn_col].str.strip(),
                "publication_date": pd.to_datetime(df[pub_col], format="%d/%m/%Y", errors="coerce"),
                "grade": df[grade_col].str.strip().map(GRADES),
                "inspection_number": df[num_col].str.strip() if num_col in df.columns else pd.NA,
                "source": source,
            }
        )
        out.append(part.dropna(subset=["urn", "publication_date", "grade"]))
    if not out:
        return pd.DataFrame(columns=["urn", "publication_date", "grade", "inspection_number", "source"])
    ev = pd.concat(out, ignore_index=True)
    ev["grade"] = ev["grade"].astype(int)
    return ev


def dedupe_events(ev: pd.DataFrame) -> pd.DataFrame:
    """The same inspection appears as 'current' in one file and 'previous' in the next."""
    ev = ev.sort_values(["urn", "publication_date", "source"])
    dup = ev.duplicated(subset=["urn", "publication_date"], keep=False)
    conflicts = ev[dup].groupby(["urn", "publication_date"])["grade"].nunique()
    if (conflicts > 1).any():
        bad = conflicts[conflicts > 1].index[:5].tolist()
        raise ValueError(f"conflicting grades for the same URN and publication date: {bad}")
    return ev.drop_duplicates(subset=["urn", "publication_date"]).reset_index(drop=True)


def predecessors(urn: str, links: pd.DataFrame) -> list[str]:
    """This URN plus every predecessor, nearest first, following chains."""
    pred = links[links["LinkType"].str.startswith("Predecessor", na=False)]
    by_urn = pred.groupby("URN")["LinkURN"].apply(list).to_dict()
    seen, order, frontier = {urn}, [urn], [urn]
    while frontier:
        nxt = []
        for u in frontier:
            for p in by_urn.get(u, []):
                if p not in seen:
                    seen.add(p)
                    order.append(p)
                    nxt.append(p)
        frontier = nxt
    return order


def grade_in_force(events: pd.DataFrame, lineage: list[str], on: date) -> tuple[int | None, pd.Timestamp | None, str | None]:
    """Latest graded judgement published on or before `on`, across the lineage.

    Returns (grade, publication date, URN it was issued to). Publication date,
    not inspection date: a grade nobody has read yet cannot move a price.
    """
    ev = events[events["urn"].isin(lineage) & (events["publication_date"] <= pd.Timestamp(on))]
    if ev.empty:
        return None, None, None
    row = ev.sort_values("publication_date").iloc[-1]
    return int(row["grade"]), row["publication_date"], str(row["urn"])


def grade_history(events: pd.DataFrame, lineage: list[str]) -> pd.DataFrame:
    """Every change in grade in force, for the timing falsification test."""
    ev = events[events["urn"].isin(lineage)].sort_values("publication_date")
    changed = ev["grade"].ne(ev["grade"].shift())
    return ev.loc[changed, ["publication_date", "grade", "urn"]].reset_index(drop=True)
