"""Phase D1: the pre-registered main specification, bandwidth sweep, per boundary.

Writes to outputs/results/:
  main.json                  the headline number and everything needed to trace it
  bandwidth_sensitivity.csv
  per_boundary.csv

Usage:  python -m pipeline.p07_estimate
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

import pandas as pd

from line54 import config, lock, rdd, robustness, sample

RESULTS = config.ROOT / "outputs" / "results"


def load_sample() -> tuple[pd.DataFrame, dict]:
    """The stored sample, refused if it no longer matches its recorded hash."""
    lock.require_lock()
    df = pd.read_parquet(config.PROCESSED / "rdd_sample.parquet")
    meta = json.loads((config.PROCESSED / "rdd_sample.sha256").read_text())
    actual = sample.frame_sha256(df)
    if actual != meta["sha256"]:
        raise SystemExit(f"rdd_sample.parquet changed since it was built ({meta['sha256'][:12]} -> {actual[:12]}); re-run phase 06")
    return df, meta


def estimate(df: pd.DataFrame, draws: int = config.BOOTSTRAP_DRAWS) -> tuple[rdd.RDResult, pd.DataFrame, pd.DataFrame]:
    main = rdd.fit(df, config.MAIN_BANDWIDTH_M, bootstrap_draws=draws, label="main")
    sweep = rdd.bandwidth_sweep(df)
    per = robustness.per_boundary(df)
    return main, sweep, per


def main() -> None:
    df, meta = load_sample()
    main_result, sweep, per = estimate(df)
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = main_result.to_dict()
    out.update(sample_sha256=meta["sha256"], provenance_sha256=meta["provenance_sha256"], git_head=lock._git_head(),
               computed_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    (RESULTS / "main.json").write_text(json.dumps(out, indent=2, default=float))
    sweep.to_csv(RESULTS / "bandwidth_sensitivity.csv", index=False)
    per.to_csv(RESULTS / "per_boundary.csv", index=False)
    pct, lo, hi = main_result.pct
    print(f"tau = {main_result.tau:.4f} (SE {main_result.se:.4f}, t({main_result.df_inference}) CI {main_result.ci_low:.4f} to {main_result.ci_high:.4f})")
    print(f"premium {pct:+.2f}% [{lo:+.2f}%, {hi:+.2f}%]; wild cluster bootstrap p = {main_result.p_wild_bootstrap:.4f}")
    if main_result.pounds:
        print(f"pounds at median outside price: £{main_result.pounds[0]:,.0f} [£{main_result.pounds[1]:,.0f}, £{main_result.pounds[2]:,.0f}]")


if __name__ == "__main__":
    sys.exit(main())
