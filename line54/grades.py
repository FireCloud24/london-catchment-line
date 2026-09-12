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

import numpy as np
import pandas as pd

GRADES = {"1": 1, "2": 2, "3": 3, "4": 4}
GRADE_NAMES = {1: "Outstanding", 2: "Good", 3: "Requires improvement", 4: "Inadequate"}

# (role, URN, publication date, grade, inspection number, inspection start)
# 'current' rows describe the file's own inspection. 'previous' rows are
# back-references, and their dates are less reliable: the 2021/22 file gives
# URN 141499's March 2020 inspection the publication date of the 2022 one.
_EVENT_COLUMNS = [
    ("current", "URN", "Publication date", "Overall effectiveness", "Inspection number", "Inspection start date"),
    ("previous", "URN at time of previous inspection", "Previous publication date", "Previous overall effectiveness",
     "Previous inspection number", "Previous inspection start date"),
    ("previous", "URN at time of previous full inspection", "Previous publication date",
     "Previous full inspection overall effectiveness", "Previous full inspection number", "Previous inspection start date"),
    ("current", "URN at time of latest full inspection", "Publication date", "Overall effectiveness",
     "Inspection number of latest full inspection", "Inspection start date"),
    ("current", "URN at time of latest OEIF graded inspection", "Publication date of latest OEIF graded inspection",
     "Latest OEIF overall effectiveness", "Inspection number of latest OEIF graded inspection",
     "Inspection start date of latest OEIF graded inspection"),
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
    for role, urn_col, pub_col, grade_col, num_col, start_col in _EVENT_COLUMNS:
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
                "inspection_start": pd.to_datetime(df[start_col], format="%d/%m/%Y", errors="coerce")
                if start_col in df.columns else pd.NaT,
                "role": role,
                "source": source,
            }
        )
        out.append(part.dropna(subset=["urn", "publication_date", "grade"]))
    out = [p for p in out if len(p)]
    if not out:
        return pd.DataFrame(columns=["urn", "publication_date", "grade", "inspection_number", "inspection_start", "role", "source"])
    ev = pd.concat(out, ignore_index=True)
    ev["grade"] = ev["grade"].astype(int)
    return ev


def dedupe_events(ev: pd.DataFrame) -> pd.DataFrame:
    """One row per inspection, trusting a file's own inspection over back-references.

    The same inspection appears as 'current' in one file and 'previous' in
    later ones. When they disagree on the date, the 'current' row wins. What
    is left after that must agree, or the function raises rather than guess.
    """
    ev = ev.assign(_rank=(ev["role"] != "current").astype(int)).sort_values(["_rank", "source"])
    numbered = ev[ev["inspection_number"].notna() & (ev["inspection_number"] != "")]
    unnumbered = ev.drop(numbered.index)
    ev = pd.concat([numbered.drop_duplicates(subset=["inspection_number"]), unnumbered])
    ev = ev.sort_values(["urn", "publication_date", "_rank", "source"])

    # Same URN and date, different inspections: keep 'current' rows if any.
    has_current = ev.groupby(["urn", "publication_date"])["_rank"].transform("min")
    ev = ev[ev["_rank"] == has_current]
    # Two reports can be published on the same day. Chislehurst School for
    # Girls' May 2017 inspection (Inadequate) and December 2017 inspection
    # (Good) were both published on 28 Feb 2018; the later inspection is the
    # one in force. Only a tie on start date as well is unresolvable.
    ev = ev.sort_values(["urn", "publication_date", "inspection_start"])
    last = ev.groupby(["urn", "publication_date"])["inspection_start"].transform("max")
    tied = ev[(ev["inspection_start"] == last) | last.isna()]
    conflicts = tied.groupby(["urn", "publication_date"])["grade"].nunique()
    if (conflicts > 1).any():
        bad = conflicts[conflicts > 1].index[:5].tolist()
        raise ValueError(f"conflicting grades for the same URN, publication date and inspection start: {bad}")
    return ev.drop_duplicates(subset=["urn", "publication_date"], keep="last").drop(columns="_rank").reset_index(drop=True)


def predecessor_map(links: pd.DataFrame) -> dict[str, list[str]]:
    pred = links[links["LinkType"].str.startswith("Predecessor", na=False)]
    return pred.groupby("URN")["LinkURN"].apply(list).to_dict()


def predecessors(urn: str, links: pd.DataFrame | dict[str, list[str]]) -> list[str]:
    """This URN plus every predecessor, nearest first, following chains.

    Pass a prebuilt `predecessor_map` when calling this in a loop.
    """
    by_urn = links if isinstance(links, dict) else predecessor_map(links)
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


EventIndex = dict[str, tuple[np.ndarray, np.ndarray]]


def index_events(events: pd.DataFrame) -> EventIndex:
    """URN -> (sorted publication dates, grades), for repeated lookups."""
    ev = events.sort_values("publication_date")
    return {
        urn: (g["publication_date"].to_numpy("datetime64[ns]"), g["grade"].to_numpy())
        for urn, g in ev.groupby("urn")
    }


def grade_in_force(
    events: pd.DataFrame | EventIndex, lineage: list[str], on: date
) -> tuple[int | None, pd.Timestamp | None, str | None]:
    """Latest graded judgement published on or before `on`, across the lineage.

    Returns (grade, publication date, URN it was issued to). Publication date,
    not inspection date: a grade nobody has read yet cannot move a price.
    Pass an `index_events` result when calling this in a loop.
    """
    idx = events if isinstance(events, dict) else index_events(events)
    t = np.datetime64(pd.Timestamp(on), "ns")
    best = None
    for urn in lineage:
        if urn not in idx:
            continue
        dates, grades_ = idx[urn]
        k = np.searchsorted(dates, t, side="right") - 1
        if k >= 0 and (best is None or dates[k] > best[1]):
            best = (int(grades_[k]), dates[k], urn)
    if best is None:
        return None, None, None
    return best[0], pd.Timestamp(best[1]), best[2]


def grade_history(events: pd.DataFrame, lineage: list[str]) -> pd.DataFrame:
    """Every change in grade in force, for the timing falsification test."""
    ev = events[events["urn"].isin(lineage)].sort_values("publication_date")
    changed = ev["grade"].ne(ev["grade"].shift())
    return ev.loc[changed, ["publication_date", "grade", "urn"]].reset_index(drop=True)
