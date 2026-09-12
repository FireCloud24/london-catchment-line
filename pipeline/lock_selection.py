"""Lock the verified boundary set. Run by a person, after checking sources.

Refuses unless every provenance row for every selected school is marked
verified, with a name and date, and the screen run on verified rows only
selects exactly those schools.

Usage:  python -m pipeline.lock_selection --verified-by "Your Name"
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd

from line54 import catchments, config, lock


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verified-by", required=True)
    args = ap.parse_args(argv)

    prov = catchments.read_provenance()
    errors = catchments.validate(prov)
    if errors:
        raise SystemExit("provenance.csv has errors:\n  " + "\n  ".join(errors))
    screen = pd.read_csv(config.TABLES / "school_screen.csv", dtype={"urn": str})
    selected = screen.loc[screen["passes"], "urn"].tolist()
    if not selected:
        raise SystemExit("no schools pass the screen; nothing to lock")
    rows = prov[prov["urn"].isin(selected) & (prov["status"] != "rejected")]
    unverified = rows[rows["status"] != "verified"]
    if len(unverified):
        listing = unverified[["urn", "school_name", "entry_year", "status"]].to_string(index=False)
        raise SystemExit(f"these rows for selected schools are not verified:\n{listing}\n"
                         "Re-run p04 and p05 with --statuses verified after verifying.")
    payload = lock.write_lock(args.verified_by, selected)
    print(f"locked {len(selected)} schools; provenance sha256 {payload['provenance_sha256'][:16]}")


if __name__ == "__main__":
    sys.exit(main())
