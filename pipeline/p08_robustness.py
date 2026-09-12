"""Phase D2: every robustness test in section 8, written to one table.

Usage:  python -m pipeline.p08_robustness
"""
from __future__ import annotations

import sys

import pandas as pd

from line54 import config, grades, lock, robustness
from pipeline.p07_estimate import RESULTS, load_sample


def main() -> None:
    df, meta = load_sample()
    selected = lock.require_lock()["selected_urns"]
    events = pd.read_parquet(config.INTERIM / "ofsted_events.parquet")
    links = pd.read_csv(next((config.RAW / "gias").glob("links_edubasealldata*.csv")), encoding="cp1252", dtype=str,
                        keep_default_na=False)
    pred = grades.predecessor_map(links)
    lineages = {u: grades.predecessors(u, pred) for u in selected}

    table = robustness.run_all(df, events, lineages)
    table.insert(0, "sample_sha256", meta["sha256"][:16])
    RESULTS.mkdir(parents=True, exist_ok=True)
    table.to_csv(RESULTS / "robustness.csv", index=False)
    cols = ["test", "spec", "tau", "ci_low", "ci_high", "p_value", "n_obs", "note"]
    with pd.option_context("display.max_colwidth", 60, "display.width", 200):
        print(table[[c for c in cols if c in table]].to_string(index=False))


if __name__ == "__main__":
    sys.exit(main())
