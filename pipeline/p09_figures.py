"""Phase E1: the headline chart and the three appendix figures.

Usage:  python -m pipeline.p09_figures
"""
from __future__ import annotations

import sys

import pandas as pd

from line54 import config, figures, rdd
from pipeline.p07_estimate import RESULTS, load_sample


def main() -> None:
    df, _ = load_sample()
    main_result = rdd.fit(df, config.MAIN_BANDWIDTH_M, label="main")
    sweep = pd.read_csv(RESULTS / "bandwidth_sensitivity.csv")
    per = pd.read_csv(RESULTS / "per_boundary.csv", dtype={"boundary_id": str})
    names = pd.read_parquet(config.INTERIM / "schools.parquet").set_index("urn")["name"].to_dict()

    config.FIGURES.mkdir(parents=True, exist_ok=True)
    figures.headline(df, main_result, config.FIGURES / "headline.png")
    figures.bandwidth(sweep, config.FIGURES / "bandwidth_sensitivity.png")
    figures.forest(per, main_result, names, config.FIGURES / "per_boundary_forest.png")
    figures.density_hist(df, config.FIGURES / "running_variable_density.png")
    print(f"figures -> {config.FIGURES}")


if __name__ == "__main__":
    sys.exit(main())
